#!/usr/bin/env python3
"""Program one V485 over ST-Link only, including verified EEPROM ID/type.

Uses the real bootloader's EEPROM driver through GDB, then verifies application
startup. Motors must be unpowered. No RS485 adapter or button selection needed.
Original MicroSMT attribution: ../README.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import time
import zlib

from commission import PROJECT, REPO, planned_width
from rs485_upload import inspect_image


def symbols(elf, nm):
    result = {}
    for line in subprocess.check_output([str(nm), '-n', str(elf)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            result[parts[2]] = int(parts[0], 16)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stlink', required=True)
    parser.add_argument('--new-id', type=int, required=True)
    parser.add_argument('--width', type=int, choices=(8,12,16,24))
    parser.add_argument('--count', type=int, help='Default events: 2 for 8 mm type, otherwise 1; override with 1..99')
    parser.add_argument('--log', type=Path, default=REPO / '.local/v485-batch')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-fA-F]+', args.stlink) or not 1 <= args.new_id <= 99 or (args.count is not None and not 1 <= args.count <= 99):
        parser.error('Use a hexadecimal ST-Link serial, ID 1..99 and count 1..99')
    width = args.width if args.width is not None else planned_width(args.new_id)
    args.count = args.count if args.count is not None else (2 if width == 8 else 1)
    motor_options = 1 if width == 8 else 0
    toolchain = Path.home() / '.platformio/packages/toolchain-gccarmnoneeabi/bin'
    nm, gdb = toolchain/'arm-none-eabi-nm', toolchain/'arm-none-eabi-gdb'
    loader_elf = PROJECT/'.pio/build/bootloader/firmware.elf'
    app_elf = PROJECT/'.pio/build/v485/firmware.elf'
    loader = loader_elf.with_suffix('.bin'); application = app_elf.with_suffix('.bin')
    app = application.read_bytes(); variant, size, crc = inspect_image(app)
    if not 8 < loader.stat().st_size <= 8192:
        raise ValueError('Build the universal loader first')
    boot_symbols = symbols(loader_elf, nm); app_symbols = symbols(app_elf, nm)
    read = boot_symbols['EEPROM_ReadChecked'] | 1
    write = boot_symbols['EEPROM_WriteByte'] | 1
    args.log.mkdir(parents=True, exist_ok=True)
    prefix = args.log / f'unit-{args.new_id:02d}-{time.time_ns()}'
    ledger = args.log/'units.json'
    units = json.loads(ledger.read_text()) if ledger.exists() else {}
    base = ['openocd','-f','interface/stlink.cfg','-c',f'adapter serial {args.stlink}',
            '-f','target/stm32f1x.cfg','-c','adapter speed 1000']
    preflight = base + ['-c','init','-c','mdw 0x1ffff7e8 3','-c','flash probe 0',
                        '-c',f'dump_image {{{prefix}-before-flash.bin}} 0x08000000 0x10000',
                        '-c','shutdown']
    check = subprocess.run(preflight, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
    Path(f'{prefix}-probe.log').write_text(check.stdout)
    check.check_returncode()
    found = re.search(r'0x1ffff7e8:\s+([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})', check.stdout)
    if not found or 'flash size = 64 KiB' not in check.stdout:
        raise ValueError('Expected STM32F103C8 / 64 KB target not confirmed')
    uid = ''.join(found.groups()).upper()
    if str(args.new_id) in units and units[str(args.new_id)]['uid'] != uid:
        raise ValueError('Requested ID is already recorded for a different MCU')
    if any(n != str(args.new_id) and row['uid'] == uid for n,row in units.items()):
        raise ValueError('This MCU is already recorded at another ID')
    print(f'ID {args.new_id:02d}: UID {uid}; programming universal image, type {width} mm', flush=True)
    # Use a private localhost debug port; the server is stopped in finally.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); debug_port = sock.getsockname()[1]
    commands = [f'gdb_port {debug_port}','tcl_port disabled','telnet_port disabled','bindto 127.0.0.1',
                'init','reset halt','flash probe 0','flash erase_sector 0 0 last',
                f'flash write_image {{{loader}}} 0x08000000 bin',
                f'flash write_image {{{application}}} 0x08002000 bin',
                f'verify_image {{{loader}}} 0x08000000 bin',
                f'verify_image {{{application}}} 0x08002000 bin']
    invocation = list(base)
    for command in commands: invocation += ['-c',command]
    with Path(f'{prefix}-openocd.log').open('w') as output:
        server = subprocess.Popen(invocation, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+20
            while True:
                if server.poll() is not None: raise RuntimeError('OpenOCD stopped; see log')
                if 'verified' in Path(f'{prefix}-openocd.log').read_text() and Path(f'{prefix}-openocd.log').read_text().count('verified') >= 2: break
                if time.monotonic() >= deadline: raise TimeoutError('Programming did not complete; see log')
                time.sleep(.1)
            print('Both flash images verified; programming EEPROM settings and boot record...', flush=True)
            record = struct.pack('<IIII',0x31423556,variant,size,crc)
            record += struct.pack('<I',zlib.crc32(record))
            header = ['set pagination off','set confirm off','set remotetimeout 10',
                      f'file {loader_elf}',f'target extended-remote 127.0.0.1:{debug_port}',
                      'monitor reset halt',f'thbreak *{read & ~1:#x}','continue']
            def readback(name):
                return ['set $i = 0','while $i < 64',
                        f'  set $ok = ((unsigned char (*)(unsigned char, unsigned char *)){read:#x})($i, (unsigned char *)(0x20001000+$i))',
                        '  if $ok != 1','    quit 1','  end','  set $i = $i + 1','end',
                        f'dump binary memory {prefix}-{name}-eeprom.bin 0x20001000 0x20001040']
            body = header + readback('before')
            # Commit boot validity LAST, after checked ID/count/type and image record.
            updates = [(31,0),(2,0),(3,width ^ 255),(0,args.new_id),(1,args.count),
                       (6,0),(4,motor_options),(5,motor_options ^ 255),(6,0xA1)]
            updates += list(enumerate(record,32)) + [(2,width),(31,165)]
            for address,value in updates:
                body += [f'set $ok = ((unsigned char (*)(unsigned char, unsigned char)){write:#x})({address},{value})',
                         'if $ok != 1',f'  printf "EEPROM write failed at {address}\\n"','  quit 1','end']
            body += readback('after') + ['disconnect','quit']
            provision = Path(f'{prefix}-provision.gdb'); provision.write_text('\n'.join(body)+'\n')
            run = subprocess.run([str(gdb),'-q','-batch','-x',str(provision)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
            Path(f'{prefix}-provision.log').write_text(run.stdout); run.check_returncode()
            expected = bytearray(Path(f'{prefix}-before-eeprom.bin').read_bytes())
            for address,value in updates: expected[address] = value
            if Path(f'{prefix}-after-eeprom.bin').read_bytes() != expected:
                raise ValueError('EEPROM readback mismatch; target left halted')
            # Verify the real application has reached its main loop with exact settings.
            startup = [f'file {app_elf}',f'target extended-remote 127.0.0.1:{debug_port}',
                       'monitor reset halt',f'thbreak *{app_symbols["Feeder_Run"]:#x}','continue']
            for name,value in [('currentAddr',args.new_id),('currentType',width),('currentCount',args.count),('motorOptions',motor_options),
                               ('feedReady',1),('feedState',0),('faultReason',0),('settingsFault',0),('peelRunning',0)]:
                startup += [f'if *(unsigned char *){app_symbols[name]:#x} != {value}',
                            f'  printf "Startup check failed: {name}\\n"','  quit 1','end']
            startup += ['if (*(unsigned int *)0x4001080c & 0x11c0) != 0x11c0',
                        '  printf "Motor outputs not stopped\\n"','  quit 1','end',
                        f'printf "STARTUP VERIFIED ID={args.new_id} TYPE={width} COUNT={args.count}\\n"',
                        'monitor resume','disconnect','quit']
            script = Path(f'{prefix}-startup.gdb'); script.write_text('\n'.join(header[:3]+startup)+'\n')
            run = subprocess.run([str(gdb),'-q','-batch','-x',str(script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
            Path(f'{prefix}-startup.log').write_text(run.stdout); run.check_returncode()
            if 'STARTUP VERIFIED' not in run.stdout: raise ValueError('Application startup not confirmed')
        finally:
            server.terminate()
            try: server.wait(timeout=5)
            except subprocess.TimeoutExpired: server.kill(); server.wait()
    result = dict(id=args.new_id,width_mm=width,uid=uid,default_count=args.count,
                  nominal_step_um=2000 if width==8 else 4000,verified_over='ST-Link SWD; EEPROM readback and application startup',
                  application_sha256=hashlib.sha256(app).hexdigest(),loader_sha256=hashlib.sha256(loader.read_bytes()).hexdigest(),
                  image_crc=f'{crc:08X}',verified_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),evidence=str(prefix))
    units[str(args.new_id)] = result
    temp = ledger.with_suffix('.tmp'); temp.write_text(json.dumps(units,indent=2)+'\n'); temp.replace(ledger)
    Path(f'{prefix}-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified:',json.dumps(result),flush=True)


if __name__ == '__main__':
    try: main()
    except (OSError,ValueError,RuntimeError,TimeoutError,subprocess.SubprocessError) as error:
        raise SystemExit(f'SWD commissioning stopped: {error}')
