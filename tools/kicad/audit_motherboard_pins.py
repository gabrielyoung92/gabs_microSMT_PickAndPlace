#!/usr/bin/env python3
"""Create a source-based MCU pin inventory; hardware and firmware availability remain separate."""
import csv,json,re
from collections import defaultdict
import build_schematics as bs
from build_motherboard import DOCS

ADC={'P0.23':0,'P0.24':1,'P0.25':2,'P0.26':3,'P1.30':4,'P1.31':5,'P0.3':6,'P0.2':7}
UART={'P0.2':'TXD0','P0.3':'RXD0','P0.15':'TXD1','P0.16':'RXD1','P0.25':'TXD3','P0.26':'RXD3',
      'P4.28':'TXD3','P4.29':'RXD3','P0.0':'TXD3','P0.1':'RXD3','P0.10':'TXD2','P0.11':'RXD2','P2.8':'TXD2','P2.9':'RXD2','P2.0':'TXD1','P2.1':'RXD1'}

def audit():
 m=json.loads((DOCS/'recovery.json').read_text())
 s=bs.stock('MCU_NXP_LPC','LPC1769FBD100')
 names={bs.child(p,'number')[1]:bs.child(p,'name')[1] for sub in bs.children(s,'symbol') for p in bs.children(sub,'pin')}
 endpoints=defaultdict(list)
 for c in m['components']:
  for p in c['pins']:endpoints[p['source_net']].append(c['ref']+'.'+p['number'])
 ic=next(c for c in m['components'] if c['ref']=='IC1');rows=[]
 for p in sorted(ic['pins'],key=lambda x:int(x['number'])):
  name=names[p['number']];match=re.match(r'P([0-9]+)\[([0-9]+)\]',name);gpio=f'P{match[1]}.{match[2]}' if match else ''
  other=[x for x in endpoints[p['source_net']] if x!='IC1.'+p['number']]
  isolated=not p['net'];reserved=bool(gpio in UART)
  status='connected in source CAM' if not isolated else 'isolated non-GPIO' if not gpio else 'isolated GPIO; UART alternate reserved' if reserved else 'isolated GPIO candidate'
  purpose='UART0 header reserved' if gpio in ['P0.2','P0.3'] else 'RESERVED vacuum head 1' if gpio=='P0.23' else 'RESERVED vacuum head 2' if gpio=='P0.24' else 'RESERVED vacuum pump/manifold' if gpio=='P1.30' else 'preferred feeder bus candidate' if isolated and gpio=='P2.11' else 'alternative feeder bus candidate' if isolated and gpio in ['P0.18','P0.17'] else 'additional ADC candidate' if isolated and gpio=='P1.31' else ''
  rows.append({'package_pin':p['number'],'gpio':gpio,'symbol_pin_name':name,'source_net':p['source_net'],
    'board_status':status,'other_source_pins':'; '.join(other),'adc_channel':str(ADC[gpio]) if gpio in ADC else '',
    'uart_alternate':UART.get(gpio,''),'proposed_use':purpose,
    'pcb_x_mm':p['position_mm'][0],'pcb_y_mm':p['position_mm'][1],
    'access':'MCU pad only; no source connector' if isolated else 'source endpoints listed; fitted access unverified',
    'firmware_status':'not audited; verify pin configuration and timer/interrupt ownership'})
 with (DOCS/'mcu-pins.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 (DOCS/'mcu-pins.json').write_text(json.dumps(rows,indent=2)+'\n')
 print('MCU pins',len(rows),'isolated GPIO',sum(x['board_status'].startswith('isolated GPIO') for x in rows),'isolated non-UART GPIO',sum(x['board_status']=='isolated GPIO candidate' for x in rows))
 for r in rows:
  if r['proposed_use']:print(r['package_pin'],r['gpio'],r['source_net'],r['proposed_use'],r['board_status'])
 return rows

if __name__=='__main__':audit()
