#!/usr/bin/env python3
"""Read-only diagnostic client for the MicroSMT Pico USB bridge.

Omitting --port and --host only prints a request; no device or network is opened.
"""
import argparse
import binascii
import secrets
import socket
import struct
import sys
import time

OPS={'ping':1,'status':2,'inputs':3,'uid':4}

def encode(address,operation,transaction,payload=b''):
    if not 1<=address<=247:raise ValueError('address must be 1..247')
    if len(payload)>12:raise ValueError('payload exceeds 12 bytes')
    body=struct.pack('<BBBBBBI12s',0xa5,0x5a,1,address,0,operation,transaction,payload)
    return body+struct.pack('<H',binascii.crc_hqx(body,0xffff))

def decode_reply(frame,request):
    if len(frame)!=24 or frame[:3]!=b'\xa5\x5a\x01':raise ValueError('bad frame/version')
    if binascii.crc_hqx(frame[:22],0xffff)!=int.from_bytes(frame[22:],'little'):raise ValueError('bad CRC')
    if frame[3]!=0 or frame[4]!=request[3] or frame[5]!=(request[5]|0x80) or frame[6:10]!=request[6:10]:
        raise ValueError('response does not match request')
    return frame[10:22]

def describe(operation,payload):
    if operation=='uid':return 'UID '+payload.hex().upper()
    if operation=='ping':return 'PING '+payload.hex().upper()
    if payload[0]!=0:return 'RESULT '+str(payload[0])
    if operation=='inputs':
        return f'RAW sensor_PA3={(payload[1]>>0)&1} button_PA4={(payload[1]>>1)&1} bus_PA5={(payload[1]>>2)&1}'
    return f'STATUS state={payload[1]} fault={payload[2]} motion_enabled={payload[3]} uptime_ms={int.from_bytes(payload[8:12],"little")}'

def exchange(port,request):
    try:import serial
    except ImportError:raise RuntimeError('Serial access requires: python -m pip install pyserial') from None
    # No retry: transport uncertainty must never become an implicit repeated command.
    with serial.Serial(port,115200,timeout=.1,write_timeout=1) as stream:
        time.sleep(.15)
        stream.reset_input_buffer()
        stream.write(b'XFER '+request.hex().upper().encode()+b'\n')
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            line=stream.readline(128).strip()
            if line.startswith(b'ERR '):raise RuntimeError(line.decode('ascii'))
            if line.startswith(b'RX '):return bytes.fromhex(line[3:].decode('ascii'))
        raise RuntimeError('USB response timeout; no command was retried')

def exchange_tcp(host,port,request):
    """One bounded diagnostic exchange, no reconnect or implicit retries."""
    with socket.create_connection((host,port),timeout=2) as stream:
        stream.sendall(b'XFER '+request.hex().upper().encode()+b'\n')
        deadline=time.monotonic()+2
        line=bytearray()
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise RuntimeError('TCP response timeout; no command was retried')
            stream.settimeout(remaining)
            chunk=stream.recv(128)
            if not chunk:raise RuntimeError('Bridge disconnected before a complete response')
            for byte in chunk:
                if byte==10:
                    reply=bytes(line).strip()
                    if reply.startswith(b'ERR '):raise RuntimeError(reply.decode('ascii'))
                    if not reply.startswith(b'RX '):raise ValueError('unexpected bridge response')
                    return bytes.fromhex(reply[3:].decode('ascii'))
                line.append(byte)
                if len(line)>127:raise ValueError('bridge response too long')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=OPS)
    parser.add_argument('--address',type=int,default=1)
    parser.add_argument('--transaction',type=lambda s:int(s,0))
    transport=parser.add_mutually_exclusive_group()
    transport.add_argument('--port',help='COM port or serial device')
    transport.add_argument('--host',help='Pico 2 W IP address or hostname; TCP bench protocol')
    parser.add_argument('--tcp-port',type=int,default=4242)
    args=parser.parse_args()
    transaction=secrets.randbits(32) if args.transaction is None else args.transaction
    request=encode(args.address,OPS[args.operation],transaction,b'MicroSMT' if args.operation=='ping' else b'')
    if not 1<=args.tcp_port<=65535:parser.error('--tcp-port must be 1..65535')
    if not args.port and not args.host:print('XFER '+request.hex().upper())
    else:
        reply=exchange_tcp(args.host,args.tcp_port,request) if args.host else exchange(args.port,request)
        print(describe(args.operation,decode_reply(reply,request)))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError,struct.error) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
