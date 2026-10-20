"""Build native, connected KiCad schematics from the verified recovery models."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sexpdata as sx
from recover import SOURCES, ident, PROJECTS, REPORTS

S=sx.Symbol
LIB='MicroSMT_Recovered'
STOCK=Path(os.environ.get('KICAD9_SYMBOL_DIR',''))
cache={}
def tag(x):return str(x[0]) if isinstance(x,list) and x else ''
def child(x,key):return next((e for e in x if tag(e)==key),None)
def children(x,key):return [e for e in x if tag(e)==key]
def expr(text):return sx.loads(text)
def q(text):return json.dumps(text)
def stock(lib,name):
    if lib not in cache:
        cache[lib]={e[1]:e for e in sx.loads((STOCK/(lib+'.kicad_sym')).read_text()) if tag(e)=='symbol'}
    e=deepcopy(cache[lib][name]);parent=child(e,'extends')
    if parent:
        base=stock(lib,parent[1]); overrides={p[1] for p in children(e,'property')}
        merged=[v for v in base[2:] if not (tag(v)=='property' and v[1] in overrides)]
        e=[S('symbol'),name,*merged,*[v for v in e[2:] if tag(v)!='extends']]
    for sub in children(e,'symbol'):
        sub[1]=name+'_'+sub[1].rsplit('_',2)[1]+'_'+sub[1].rsplit('_',2)[2]
    return e

def box(name,ref,pins,width=12.7):
    # pins: number, name, electrical type, left/right, row
    count=max(p[4] for p in pins)+1;top=(count-1)*1.27
    e=expr(f'''(symbol {q(name)} (pin_names (offset 0.635))
      (exclude_from_sim no)(in_bom yes)(on_board yes)
      (property "Reference" {q(ref)} (at 0 {top+5.08} 0)(effects(font(size 1.27 1.27))))
      (property "Value" {q(name)} (at 0 {top+2.54} 0)(effects(font(size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0)(effects(font(size 1.27 1.27))(hide yes)))
      (symbol {q(name+'_0_1')}(rectangle(start {-width} {top+1.27})(end {width} {-top-1.27})
        (stroke(width 0.254)(type default))(fill(type background))))
      (symbol {q(name+'_1_1')}))''')
    sub=children(e,'symbol')[-1]
    for num,label,typ,side,row in pins:
        x=-(width+5.08) if side=='left' else width+5.08;a=0 if side=='left' else 180
        sub.append(expr(f'''(pin {typ} line(at {x} {top-row*2.54} {a})(length 5.08)
          (name {q(label)}(effects(font(size 1.0 1.0))))
          (number {q(str(num))}(effects(font(size 1.0 1.0)))))'''))
    return e

def library():
    lib={n:stock('Device',n) for n in ['R','C','C_Polarized','D_Schottky','LED','Crystal']}
    for n in ['Conn_01x02','Conn_01x03','Conn_01x04','Conn_02x12_Odd_Even']:
        lib[n]=stock('Connector_Generic',n)
    lib['MountingHole_Pad']=stock('Mechanical','MountingHole_Pad')
    lib['PWR_FLAG']=stock('power','PWR_FLAG')
    lib['STM32F103C8Tx']=stock('MCU_ST_STM32F1','STM32F103C8Tx')
    lib['AMS1117_4pad']=box('AMS1117_4pad','U',[(3,'VIN','power_in','left',0),
        (1,'GND','power_in','left',2),(2,'VOUT','power_out','right',0),(4,'TAB (VOUT)','passive','right',2)])
    # Physical pins 1 and 5 are NC in the supplied TC1508A drawing.
    names=['NC','IN1','IN2','VCC1','NC','IN3','IN4','VCC2',
           'OUT4','GND','GND','OUT3','OUT2','GND','GND','OUT1']
    lib['TC1508A']=box('TC1508A','U',[(i,names[i-1],
        'input' if i in [2,3,6,7] else 'power_in' if i in [4,8,10,11,14,15] else
        'output' if i in [9,12,13,16] else 'no_connect',
        'left' if i<=8 else 'right',(i-1) if i<=8 else 16-i) for i in range(1,17)])
    lib['Switch_2contact_2anchor']=box('Switch_2contact_2anchor','SW',[
        (1,'CONTACT','passive','left',0),(2,'CONTACT','passive','right',0),
        (3,'PAD3','passive','left',2),(4,'PAD4','passive','right',2)],7.62)
    return lib

# The original builders load stock symbols explicitly; the remaining-board
# generator supplies its own CAM-derived definitions without a stock-library lookup.
LIBS={}

def pretty(e,depth=0):
    if not isinstance(e,list):return sx.dumps(e)
    if not any(isinstance(x,list) for x in e):return sx.dumps(e)
    prefix=[];rest=[]
    for x in e:
        (rest if isinstance(x,list) else prefix).append(x)
    return '('+' '.join(sx.dumps(x) for x in prefix)+''.join('\n'+'  '*(depth+1)+pretty(x,depth+1) for x in rest)+')'

class Sheet:
    def __init__(self,model):
        self.model=model;self.name=model['name'];self.root=ident(self.name+'/schematic')
        self.items=[];self.used=set();self.count=0
    def uid(self,kind):
        self.count+=1;return ident(f'{self.name}/{kind}/{self.count}')
    def text(self,text,x,y,size=1.27):
        self.items.append(expr(f'(text {q(text)}(at {x} {y} 0)(effects(font(size {size} {size}))(justify left top))(uuid {self.uid("text")}))'))
    def section(self,title,x,y):self.text(title,x,y,1.8)
    def place(self,c,symbol,x,y):
        self.used.add(symbol);definition=LIBS[symbol]
        ref=c['ref'];uid=c.get('uuid',ident(self.name+'/symbol/'+ref))
        instance=expr(f'''(symbol(lib_id {q(LIB+':'+symbol)})(at {x} {y} 0)(unit 1)
          (exclude_from_sim no)(in_bom {'no' if ref.startswith('#') else 'yes'})
          (on_board {'no' if ref.startswith('#') else 'yes'})(dnp no)(uuid {uid}))''')
        for key,value in [('Reference',ref),('Value',c['value']),('Footprint',c.get('footprint','')),('Datasheet','')]:
            props={a[1]:a for a in children(definition,'property')}
            source=deepcopy(props.get(key,expr(f'(property {q(key)} ""(at 0 0 0)(effects(font(size 1.27 1.27))(hide yes)))')))
            source[2]=value
            at=child(source,'at');at[1]=round(x+at[1],6);at[2]=round(y-at[2],6)
            # Library passive fields can be rotated; horizontal text is easier here.
            at[3]=0
            if symbol=='R' and key in ('Reference','Value'):
                at[1]=x+3.81;at[2]=y+(-1.27 if key=='Reference' else 1.27)
                effects=child(source,'effects');effects.append(expr('(justify left)'))
            if ref.startswith('MH') and key=='Value':child(source,'effects').append(expr('(hide yes)'))
            instance.append(source)
        pins=[p for sub in children(definition,'symbol') for p in children(sub,'pin')]
        expected={p['number']:p['net'] for p in c['pins']}
        assert set(expected)=={child(p,'number')[1] for p in pins},ref
        endpoints=set()
        for p in pins:
            num=child(p,'number')[1];a=child(p,'at');px=round(x+a[1],6);py=round(y-a[2],6)
            instance.append(expr(f'(pin {q(num)}(uuid {ident(self.name+"/pin/"+ref+"/"+num)}))'))
            net=expected[num]
            if (px,py,net) in endpoints:continue
            endpoints.add((px,py,net))
            if not net:
                self.items.append(expr(f'(no_connect(at {px} {py})(uuid {self.uid("nc")}))'));continue
            angle=math.radians(a[3]);ex=round(px-5.08*math.cos(angle),6);ey=round(py+5.08*math.sin(angle),6)
            self.items.append(expr(f'(wire(pts(xy {px} {py})(xy {ex} {ey}))(stroke(width 0)(type default))(uuid {self.uid("wire")}))'))
            vertical=symbol=='STM32F103C8Tx' and a[3] in (90,270)
            rotation=90 if vertical else 0
            justify='right bottom' if a[3]==0 else 'left bottom'
            self.items.append(expr(f'(label {q(net)}(at {ex} {ey} {rotation})(effects(font(size 1.0 1.0))(justify {justify}))(uuid {self.uid("label")}))'))
        instance.append(expr(f'(instances(project {q(self.name)}(path {q("/"+self.root)}(reference {q(ref)})(unit 1))))'))
        self.items.append(instance)
    def save(self):
        definitions=[]
        for name in sorted(self.used):
            e=deepcopy(LIBS[name]);e[1]=LIB+':'+name;definitions.append(e)
        title='Bing feeder V2 - recovered reference' if self.name=='feeder_v2' else self.name.replace('_',' ').upper()+' - recovered reference'
        root=expr(f'''(kicad_sch(version 20250114)(generator "eeschema")(uuid {self.root})(paper "A3")
          (title_block(title {q(title)})(date "2026-09-21")(rev "recovery-1")
          (comment 1 "CAM-derived reference; review source discrepancies before redesign or fabrication."))
          (lib_symbols))''')
        child(root,'lib_symbols').extend(definitions);root.extend(self.items)
        root.append(expr('(sheet_instances(path "/"(page "1")))'))
        root.append(expr('(embedded_fonts no)'))
        folder=PROJECTS[self.name]
        (folder/(self.name+'.kicad_sch')).write_text(pretty(root)+'\n')
        (folder/'sym-lib-table').write_text(f'(sym_lib_table (version 7) (lib (name "{LIB}") (type "KiCad") (uri "${{KIPRJMOD}}/libraries/{LIB}.kicad_sym") (options "") (descr "Recovered symbols and cached KiCad standard symbols")))\n')

def feeder(m):
    sh=Sheet(m);components={c['ref']:c for c in m['components']}
    def place(ref,sym,x,y):sh.place(components.pop(ref),sym,x,y)
    sh.section('01 / HOST POWER AND REGULATION',22.86,20.32)
    place('H1','Conn_01x04',48.26,45.72)
    place('D1','D_Schottky',88.9,40.64)
    place('U1','AMS1117_4pad',106.68,73.66)
    for ref,x in [('C2',35.56),('C3',63.5),('C4',96.52),('C5',124.46)]:place(ref,'C',x,111.76)
    sh.text('H1: 1 GND / 2 HOST_VIN / 3 PA5 / 4 PA11\nU1 tab pad 4 is isolated in the supplied PCB.\nThe source drawing appears to join it to VOUT.',22.86,134.62)
    sh.section('02 / MCU (F103 PINOUT IS PROVISIONAL)',157.48,20.32)
    place('U2','STM32F103C8Tx',203.2,99.06)
    sh.text('Source marking: STM32C8T6 (incomplete).\nVerify exact fitted device before selecting firmware.\nPA0 / PA1 retain source single-pin copper nets.',157.48,157.48)
    sh.section('03 / DUAL MOTOR DRIVER',274.32,20.32)
    place('U3','TC1508A',309.88,58.42)
    place('U4','Conn_01x02',378.46,40.64);place('U5','Conn_01x02',378.46,66.04)
    for ref,x in [('C13',284.48),('C12',312.42),('C14',342.9),('C15',373.38)]:place(ref,'C',x,101.6)
    for ref,sym,x in [('C16','C_Polarized',289.56),('C17','C_Polarized',322.58),('C18','C',355.6)]:place(ref,sym,x,132.08)
    sh.section('04 / CLOCK, RESET AND BOOT',22.86,172.72)
    place('X1','Crystal',45.72,198.12)
    place('C6','C',33.02,231.14);place('C8','C',60.96,231.14)
    place('R2','R',91.44,195.58);place('C9','C',91.44,231.14)
    place('R1','R',121.92,195.58);place('R3','R',121.92,231.14)
    sh.section('05 / LOCAL INPUTS AND STATUS',271.78,157.48)
    place('H2','Conn_01x04',292.1,180.34);place('CN1','Conn_01x03',342.9,180.34)
    place('SW1','Switch_2contact_2anchor',307.34,210.82)
    for i,x in enumerate([281.94,322.58,363.22],1):
        place('R'+str(i+3),'R',x,228.6);place('LED'+str(i),'LED',x,246.38)
    sh.section('06 / 3V3 DECOUPLING',157.48,185.42)
    for i,ref in enumerate(['C1','C7','C10','C11']):place(ref,'C',167.64+(i%2)*43.18,208.28+(i//2)*30.48)
    sh.text('Mounting holes and copper islands follow the CAM.\nNo body outline or courtyard is inferred from copper.',22.86,254)
    for i in range(1,5):place('MH'+str(i),'MountingHole_Pad',30.48+(i-1)*25.4,274.32)
    for i,net in enumerate(['GND','+5V','HOST_VIN']):
        sh.place({'ref':'#FLG0'+str(i+1),'value':'PWR_FLAG','pins':[{'number':'1','net':net}]},'PWR_FLAG',167.64+i*27.94,269.24)
    assert not components,components.keys();sh.save()

def busbar(m):
    sh=Sheet(m);components={c['ref']:c for c in m['components']}
    def place(ref,sym,x,y):sh.place(components.pop(ref),sym,x,y)
    sh.section('FEEDER SLOTS / SOURCE CONNECTOR REFERENCES',22.86,22.86)
    for i in range(8):place('N'+str(i+1),'Conn_01x03',45.72+i*45.72,53.34)
    sh.text('Slot pins: 1 = signal, 2 = VCC, 3 = GND. Supply voltage is not established by the busbar CAM.',22.86,73.66)
    sh.section('RECOVERED INTERCONNECT HEADERS',22.86,93.98)
    place('JREC1','Conn_02x12_Odd_Even',91.44,137.16)
    if 'JREC2' in components:place('JREC2','Conn_02x12_Odd_Even',223.52,137.16)
    sh.text('JREC references and pad numbering were added during reconstruction.\nTop view: rows from top to bottom; odd numbers left, even numbers right.\nThese are 2 mm pitch headers. Confirm mating cable numbering physically.\nRECOVERED_* nets are copper-traced pass-through nets with no source name.',22.86,170.18)
    if m['name'] in ['busbar_n1_n8','busbar_n9_n16']:
        sh.text('SOURCE DISCREPANCY: both N1-N8 and N9-N16 archives label their slot nets N9...N16.\nThe schematic preserves those exported names. Do not assume an N1...N8 mapping.',22.86,203.2,1.5)
    else:sh.text('This archive has one 2x12 interconnect header; no right-hand header is present.',22.86,203.2,1.5)
    sh.section('PLATED MOUNTING HOLES / ISOLATED COPPER',22.86,226.06)
    for i in range(1,6):place('MH'+str(i),'MountingHole_Pad',35.56+(i-1)*40.64,246.38)
    assert not components,components.keys();sh.save()

if __name__=='__main__':
    LIBS=library()
    root=expr('(kicad_symbol_lib(version 20241209)(generator "kicad_symbol_editor"))')
    root.extend(LIBS.values())
    for name in SOURCES:
        (PROJECTS[name]/'libraries'/(LIB+'.kicad_sym')).write_text(pretty(root)+'\n')
        m=json.loads((REPORTS[name]/'recovery.json').read_text())
        (feeder if name=='feeder_v2' else busbar)(m)
        print('Schematic:',name)
