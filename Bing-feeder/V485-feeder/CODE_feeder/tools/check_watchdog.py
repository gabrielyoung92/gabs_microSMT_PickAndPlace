#!/usr/bin/env python3
"""Check the application IWDG register setup and main-only refresh placement."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
board = (root / 'src/board.c').read_text()
main = (root / 'src/main.c').read_text()
feeder = (root / 'src/feeder.c').read_text()
functions = '\n'.join(re.search(pattern, board, re.S | re.M).group() for pattern in (
    r'void Board_WatchdogFeed\(void\) \{.*?^\}',
    r'static void Watchdog_Start\(void\) \{.*?^\}',
))
assert re.search(r'#if !FEEDER_BOOTLOADER\s+void Board_WatchdogFeed.*?Watchdog_Start.*?#endif', board, re.S)
assert re.search(r'#if !FEEDER_BOOTLOADER\s+Watchdog_Start\(\);\s+#endif', board)
assert main.index('Feeder_Run();') < main.index('Board_WatchdogFeed();')
assert 'Watchdog' not in re.search(r'void SysTick_Handler.*?^\}', main, re.S | re.M).group()
assert 'Board_WatchdogFeed(); // Invalid settings' in feeder
assert feeder.count('Board_WatchdogFeed(') == 2
# Execute the actual register routines with a write-recording peripheral stub.
source = '''#include <cassert>
#include <vector>
struct Reg {
 unsigned value = 0; std::vector<unsigned> writes;
 void operator=(unsigned v) { value=v; writes.push_back(v); }
 operator unsigned() const { return value; }
};
struct { Reg KR, PR, RLR, SR; } peripheral;
#define IWDG (&peripheral)
''' + functions + '''
int main() {
 Watchdog_Start();
 assert((IWDG->KR.writes == std::vector<unsigned>{0xCCCC,0x5555,0xAAAA}));
 assert(IWDG->PR == 4 && IWDG->RLR == 2499);
 Board_WatchdogFeed();
 assert(IWDG->KR.writes.back() == 0xAAAA);
}
'''
with tempfile.TemporaryDirectory(prefix='v485-watchdog-') as directory:
    path = Path(directory)
    (path / 'check.cpp').write_text(source)
    subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', str(path / 'check.cpp'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
print('Watchdog passed: actual register sequence, nominal 4 s reload, main-only refresh, bootloader excluded. Hardware reset timing requires a bench test.')
