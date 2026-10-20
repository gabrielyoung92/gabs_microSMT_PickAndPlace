#!/usr/bin/env python3
"""Build a connected hierarchical motherboard schematic from the recovered pad model."""
from copy import deepcopy
from collections import defaultdict
import json
import math
import re
import pcbnew as k
import build_schematics as bs
from build_motherboard import NAME,LIB,FOLDER,BUILD
from recover import OUTPUT,ident

bs.LIB=LIB
MCU=bs.stock('MCU_NXP_LPC','LPC1769FBD100')
for sub in bs.children(MCU,'symbol'):
    for pin in bs.children(sub,'pin'):
        name=bs.child(pin,'name');name[1]=name[1].replace('/','_')
bs.LIBS['LPC1769FBD100']=MCU
ROOT=ident(NAME+'/schematic')
ALL_DEFINITIONS={}


def definition(c):
    ref=c['ref'];numbers=[p['number'] for p in c['pins']]
    if ref=='IC1':return 'LPC1769FBD100'
    # Keep conventional passive graphics with exact physical pad numbering.
    kind='R' if ref.startswith('R') else 'C_Polarized' if ref in ['C63','C64','C84','C101','C102'] else 'C' if ref.startswith('C') else 'LED' if ref.startswith('LED') else 'D_Zener' if ref=='D5' else 'D_Schottky' if ref.startswith('D') else None
    if kind and len(numbers)==2:
        key='Recovered_'+ref
        e=bs.stock('Device',kind)
        # KiCad standard diode: 1 cathode, 2 anode. CAM uses C/A on these parts.
        mapping={'1':'C','2':'A'} if set(numbers)=={'A','C'} else {'1':'1','2':'2'}
        for sub in bs.children(e,'symbol'):
            sub[1]=key+'_'+sub[1].rsplit('_',2)[1]+'_'+sub[1].rsplit('_',2)[2]
            for pin in bs.children(sub,'pin'):
                bs.child(pin,'number')[1]=mapping[bs.child(pin,'number')[1]]
        e[1]=key;bs.LIBS[key]=e
        return key
    key='Recovered_'+ref
    names={}
    if ref=='IC10':names={'1':'GND','2':'VOUT','3':'VIN','4':'TAB / VOUT'}
    if ref=='IC11':names={'1':'VOUT','2':'GND','3':'VIN'}
    if ref=='IC13':names={'1':'VIN','2':'GND','3':'VOUT'}
    if ref in ['IC4','IC9']:
        names=dict(zip(map(str,range(1,21)),['P3A','P3W','P3B','HVC/A0','SCL','SDA','VSS','P1B','P1W','P1A','P0A','P0W','P0B','NC','RESET','A1','VDD','P2B','P2W','P2A']))
    if ref=='U1':names={'1':'NC','2':'CS','3':'DI','4':'VCC','5':'SCK','6':'GND','7':'DO','8':'RSV','CD1':'SHIELD','CD2':'SHIELD','GND1':'SHIELD','GND3':'SHIELD'}
    if ref=='S6':names={'1':'GND','2':'3V3','3':'TX_0 RESERVED','4':'RX_0 RESERVED'}
    if ref in ['Q5','Q6','Q7']:names={'G':'GATE','D':'DRAIN','S':'SOURCE'}
    if ref.startswith('JP') and ref[-1]=='1' and len(numbers)==8:names=dict(zip(map(str,range(1,9)),['DIR','STEP','CURRENT REF','NC','NC','MS2','MS1','EN']))
    if ref.startswith('JP') and len(numbers)==8 and ref in ['JP7','JP9','JP12','JP15','JP18']:names=dict(zip(map(str,range(1,9)),['GND','3V3','1B','1A','2A','2B','GND','VBB']))
    n=len(numbers);rows=math.ceil(n/2)
    pins=[(num,names.get(num,'PAD '+num),'passive','left' if i<rows else 'right',i if i<rows else i-rows) for i,num in enumerate(numbers)]
    bs.LIBS[key]=bs.box(key,re.sub('[0-9]+$','',ref),pins,12.7 if n<=8 else 17.78)
    return key


class Page(bs.Sheet):
    def __init__(self,key,title,number):
        super().__init__({'name':key});self.title=title;self.number=number;self.sheet_uuid=ident(NAME+'/sheet/'+key)
    def place(self,c,symbol,x,y):
        start=len(self.items);super().place(c,symbol,x,y)
        vertical_ends=set()
        if symbol=='LPC1769FBD100':
            for sub in bs.children(MCU,'symbol'):
                for pin in bs.children(sub,'pin'):
                    a=bs.child(pin,'at')
                    if a[3] in (90,270):
                        angle=math.radians(a[3])
                        vertical_ends.add((round(x+a[1]-5.08*math.cos(angle),6),round(y-a[2]+5.08*math.sin(angle),6)))
        for item in self.items[start:]:
            if bs.tag(item)=='label':
                item[0]=bs.S('global_label');item.insert(2,bs.expr('(shape bidirectional)'))
                at=bs.child(item,'at')
                if tuple(at[1:3]) in vertical_ends:at[3]=90
            elif bs.tag(item)=='symbol':
                if c['ref'].startswith('R'):
                    for prop in bs.children(item,'property'):
                        if prop[1] in ('Reference','Value'):
                            at=bs.child(prop,'at');at[1]=x+3.81;at[2]=y+(-1.27 if prop[1]=='Reference' else 1.27)
                            bs.child(prop,'effects').append(bs.expr('(justify left)'))
                instances=bs.child(item,'instances');project=bs.child(instances,'project');project[1]=NAME
                path=bs.child(project,'path');path[1]='/'+ROOT+'/'+self.sheet_uuid
        ALL_DEFINITIONS[symbol]=bs.LIBS[symbol]
    def save(self):
        definitions=[]
        for name in sorted(self.used):
            e=deepcopy(bs.LIBS[name]);e[1]=LIB+':'+name;definitions.append(e)
        root=bs.expr(f'''(kicad_sch(version 20250114)(generator "eeschema")(uuid {self.root})(paper "A3")
          (title_block(title {bs.q(self.title)})(rev "Reference")
           (comment 1 "CAM nets preserved; component values from supplied PDF")
           (comment 2 "Reference reconstruction - not a fabrication release")))''')
        root.append([bs.S('lib_symbols'),*definitions]);root.extend(self.items)
        (FOLDER/(self.name+'.kicad_sch')).write_text(bs.pretty(root)+'\n')


def grid(page,components,columns=4):
    for i,c in enumerate(components):
        x=48.26+(i%columns)*(73.66 if columns==5 else 365.76/columns);y=55.88+(i//columns)*(30.48 if len(components)>24 else 38.1)
        page.place(c,definition(c),x,y)


def build():
    model=json.loads((FOLDER/'recovery.json').read_text());remaining={c['ref']:c for c in model['components']}
    pages=[];assignment={}
    def take(refs):return [remaining.pop(ref) for ref in refs if ref in remaining]
    def page(key,title):
        p=Page(key,title,len(pages)+2);p.text(title,20.32,17.78,2.0);pages.append(p);return p
    def record(p,cs):
        for c in cs:assignment[c['ref']]=p.sheet_uuid
    p=page('mcu','01 - LPC1769 pin map / reserved UART / expansion')
    cs=take(['IC1']);p.place(cs[0],'LPC1769FBD100',167.64,142.24);record(p,cs)
    p.text('RX_0 / TX_0 are reserved for future use.\nPreferred feeder bus candidate: P2.11, pin 52.\nP0.23 / AD0.0, pin 9: RESERVED vacuum head 1.\nP0.24 / AD0.1, pin 8: RESERVED vacuum head 2.\nP1.30 / AD0.4, pin 21: RESERVED pump vacuum.\nSensors: XGZP6847A100KPGN33, 3.3V analog.\nPin and timing availability still require a firmware audit.\nNC means isolated in CAM, not validated on hardware.\nDo not infer 5V tolerance for analog sensor operation.',254,53.34,1.4)
    for i,net in enumerate(['3.3V','GND']):
        p.place({'ref':'#FLG'+str(i+1),'value':'PWR_FLAG','pins':[{'number':'1','net':net}]},'PWR_FLAG',284.48+i*40.64,111.76)
    for number,base in enumerate([7,9,12,15,18],1):
        p=page('stepper_'+str(number),f'{number+1:02d} - Stepper channel {number} / source module contacts')
        refs=[f'JP{base}',f'JP{base}1',f'JP{base}2',f'JP{base}3',f'H{number}', ['X','Y','Z','N1','N2'][number-1]]+[f'C{i}' for i in range(85+(number-1)*3,88+(number-1)*3)]
        cs=take(refs);grid(p,cs,3);record(p,cs)
        p.text('Module socket pins and source contact numbering are preserved.\nCurrent-reference nets come from the digital potentiometer sheet.\nBypass H connector functions and fitted modules require physical confirmation.\nCapacitors without PDF values are explicitly marked unspecified.',20.32,223.52)
    groups=[('digipots','07 - Digital current references',['IC4','IC9','R4','R18','R30','R35','R36','R37','C31','C68']),
            ('endstops','08 - Endstop input conditioning',['JP26','JP14','JP16','JP19','JP21','JP22']+[f'C{i}' for i in range(78,84)]+[f'R{i}' for i in range(92,104)]),
            ('interfaces','09 - USB / SD / UART / buttons / status',['U1','X14','S6','S1','S2','S3','JP23','JP24','Q1','Q2','R7','R8','R9','R14','R15','R16','R17']),
            ('power_input','10 - Supply input / regulators / protection',['J1','Q10','D1','D4','D5','D6','IC10','IC11','IC13','C62','C63','C64','C65','C66','C67','C76','C77','C84','R77','R78','R89','LED9','LED10']),
            ('power_outputs','11 - Switched power outputs / gate drivers',['IC14','IC15','Q4','Q5','Q6','Q7','Q8','J7','J8','J9','J11','J13','D7','D9','D11','D12','D13','C75','C101','C102','LED5','LED7','LED8','LED11','LED12']),
            ('output_resistors','12 - Output gate / indicator resistors',[f'R{i}' for i in [65,67,68,69,70,71,72,73,74,82,83,84,85,86,87,88,90,91]])]
    for key,title,refs in groups:
        p=page(key,title);cs=take(refs);grid(p,cs);record(p,cs)
    # Small MCU passives and status LEDs get their own uncluttered reference page.
    p=page('mcu_support','13 - MCU decoupling / clock / status passives')
    cs=list(remaining.values());assert len(cs)<=30,len(cs);grid(p,cs,5);record(p,cs);remaining.clear()
    for p in pages:p.save()
    root=bs.expr(f'''(kicad_sch(version 20250114)(generator "eeschema")(uuid {ROOT})(paper "A3")
     (title_block(title "MicroSMT LPC1769 motherboard - recovered reference")(rev "Reference"))
     (lib_symbols))''')
    overview=bs.Sheet({'name':NAME})
    overview.text('MicroSMT motherboard / editable reference reconstruction',20.32,20.32,2.2)
    overview.text('Four-layer copper, component pads and net identities follow the preserved CAM export.\nSheet symbols open the functional reference pages. Global labels connect pages.\nDedicated UART0 RX/TX remain reserved. Feeder GPIO and vacuum ADC choices are provisional.\nRead README.md, recovery.json, validation.json and PIN_AUDIT.md before modifications.',20.32,33.02,1.35)
    root.extend(overview.items)
    for i,p in enumerate(pages):
        x=20.32+(i%3)*129.54;y=73.66+(i//3)*35.56
        root.append(bs.expr(f'''(sheet(at {x} {y})(size 116.84 22.86)(stroke(width 0.254)(type default))(fill(color 0 0 0 0))
          (uuid {p.sheet_uuid})
          (property "Sheetname" {bs.q(p.title)}(at {x} {y-1.27} 0)(effects(font(size 1.0 1.0))(justify left bottom)))
          (property "Sheetfile" {bs.q(p.name+'.kicad_sch')}(at {x} {y+24.13} 0)(effects(font(size 1.0 1.0))(justify left top)))
          (instances(project "motherboard"(path {bs.q('/'+ROOT)}(page {bs.q(str(p.number))})))) )'''))
    (FOLDER/(NAME+'.kicad_sch')).write_text(bs.pretty(root)+'\n')
    lib=bs.expr('(kicad_symbol_lib(version 20241209)(generator "kicad_symbol_editor"))')
    lib.extend(ALL_DEFINITIONS.values());(OUTPUT/'libraries'/(LIB+'.kicad_sym')).write_text(bs.pretty(lib)+'\n')
    (FOLDER/'sym-lib-table').write_text(f'(sym_lib_table(version 7)(lib(name "{LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/../libraries/{LIB}.kicad_sym")(options "")(descr "Motherboard recovered reference symbols")))\n')
    board=k.LoadBoard(str(FOLDER/(NAME+'.kicad_pcb')))
    for fp in board.GetFootprints():fp.SetPath(k.KIID_PATH('/'+ROOT+'/'+assignment[fp.GetReference()]+'/'+ident(NAME+'/symbol/'+fp.GetReference())))
    k.SaveBoard(str(FOLDER/(NAME+'.kicad_pcb')),board)
    model['schematic_pages']=[{'file':p.name+'.kicad_sch','title':p.title,'sheet_uuid':p.sheet_uuid} for p in pages]
    (FOLDER/'recovery.json').write_text(json.dumps(model,indent=2)+'\n')
    print('Schematic:',len(pages)+1,'pages;',len(assignment),'linked components',flush=True)

if __name__=='__main__':build()
