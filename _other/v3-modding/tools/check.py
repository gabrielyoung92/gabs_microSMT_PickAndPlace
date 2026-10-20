#!/usr/bin/env python3
"""Run repository and firmware host checks without GNU Make."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
def run(args):subprocess.run(args,cwd=ROOT,check=True)
pio=shutil.which('pio') or shutil.which('platformio')
if not pio:raise SystemExit('Open a PlatformIO Core terminal, then run this script again.')
run([pio,'run','-e','native'])
program=ROOT/'.pio'/'build'/'native'/('program.exe' if os.name=='nt' else 'program')
run([str(program)])
# The Wi-Fi adapter uses SDK fakes so callback/session behavior is checked offline.
cc=os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
if not cc:raise SystemExit('Wi-Fi adapter tests require a desktop C compiler.')
wifi_test=ROOT/'build'/('test_wifi_plain.exe' if os.name=='nt' else 'test_wifi_plain')
run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion','-Wshadow',
     '-Itests/fakes','tests/test_wifi.c','-o',str(wifi_test)])
run([str(wifi_test)])
run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_bus_client.py'])
