#!/usr/bin/env python3
"""Native check of the actual stock journal; no hardware is opened."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
crc=re.search(r'uint32_t Boot_Crc32\(.*?^\}',(root/'src/boot.c').read_text(),re.S|re.M).group()
source=r'''
#include <assert.h>
#include <string.h>
#include "stock.c"
static uint8_t memory[256];
static int writes,failAfter=-1,readFail;
uint8_t EEPROM_ReadChecked(uint8_t offset,uint8_t* value){if(readFail)return 0;*value=memory[offset];return 1;}
uint8_t EEPROM_WriteByte(uint8_t offset,uint8_t value){assert(offset>=STOCK_BASE);if(failAfter==0)return 0;if(failAfter>0)failAfter--;memory[offset]=value;writes++;return 1;}
CRC_FUNCTION
int main(void){
 memset(memory,255,sizeof memory);assert(Stock_Init());
 uint32_t qty,count,seq;Stock_Read(&qty,&count,&seq);assert(qty==STOCK_UNKNOWN&&count==0);
 assert(Stock_Flush()&&!writes); // Polling/boot does not write.
 Stock_Advance();assert(Stock_Flush());assert(Stock_Init());
 Stock_Read(&qty,&count,&seq);assert(qty==STOCK_UNKNOWN&&count==1);
 Stock_Set(123);assert(Stock_Flush());assert(Stock_Init());
 Stock_Read(&qty,&count,&seq);assert(qty==123&&count==0);
 for(int i=0;i<30;i++){Stock_Advance();assert(Stock_Flush());assert(Stock_Init());}
 Stock_Read(&qty,&count,&seq);assert(qty==93&&count==30);
 assert(lastSlot>=0); // Slots wrapped repeatedly, newest survives reboot.
 uint8_t saved[256];memcpy(saved,memory,sizeof memory);
 for(int cut=0;cut<16;cut++){
  memcpy(memory,saved,sizeof memory);assert(Stock_Init());Stock_Advance();failAfter=cut;
  assert(!Stock_Flush());failAfter=-1;assert(Stock_Init());
  Stock_Read(&qty,&count,&seq);assert(qty==93&&count==30);
 }
 memcpy(memory,saved,sizeof memory);assert(Stock_Init());
 memset(memory+STOCK_BASE,255,256-STOCK_BASE);lastSlot=-1;sequence=UINT32_MAX-1;dirty=1;assert(Stock_Flush());Stock_Advance();assert(Stock_Flush());assert(Stock_Init());
 Stock_Read(&qty,&count,&seq);assert(qty==92&&count==31&&seq==0);
 remaining=STOCK_UNKNOWN;advances=UINT32_MAX;Stock_Advance();assert(Stock_Flush());assert(Stock_Init());
 Stock_Read(&qty,&count,&seq);assert(qty==STOCK_UNKNOWN&&count==UINT32_MAX);
 Stock_Set(0);assert(Stock_Flush());Stock_Advance();assert(Stock_Flush());assert(Stock_Init());
 Stock_Read(&qty,&count,&seq);assert(qty==0&&count==1);
 int before=writes;for(int i=0;i<100;i++){Stock_Read(&qty,&count,&seq);assert(Stock_Flush());}assert(writes==before);
 readFail=1;assert(!Stock_Init());
 for(unsigned i=0;i<STOCK_BASE;i++)assert(memory[i]==255); // Settings/loader untouched.
}
'''.replace('CRC_FUNCTION',crc)
with tempfile.TemporaryDirectory(prefix='v485-stock-') as directory:
    p=Path(directory);(p/'check.c').write_text(source)
    subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=undefined,address','-I',str(root/'src'),str(p/'check.c'),'-o',str(p/'check')],check=True)
    subprocess.run([str(p/'check')],check=True)
print('Stock journal passed: defaults, persistent counts, all torn writes, rotating slots, sequence wrap, saturation, zero, read failure and unchanged settings/loader bytes.')
