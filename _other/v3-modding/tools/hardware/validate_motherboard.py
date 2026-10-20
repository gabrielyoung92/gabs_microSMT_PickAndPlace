#!/usr/bin/env python3
"""Native KiCad validation and four-layer CAM comparison for the motherboard only."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json,math,pickle,zipfile
import xml.etree.ElementTree as ET
import pcbnew as k
from gerbonara import GerberFile
from shapely.affinity import translate
from build_motherboard import NAME,FOLDER,BUILD,SOURCE
from validate import run,composite
from recover import ROOT


def sync(r,m):
 run('sch','export','netlist','--format','kicadxml','-o',BUILD/'netlist.xml',FOLDER/(NAME+'.kicad_sch'))
 nets={}
 for n in ET.parse(BUILD/'netlist.xml').getroot().findall('nets/net'):
  for node in n.findall('node'):nets[(node.get('ref'),node.get('pin'))]=n.get('name')
 board=k.LoadBoard(str(FOLDER/(NAME+'.kicad_pcb')));created={};by_source={}
 # Global labels are not prefixed with '/' in KiCad's native netlist.
 for item in list(board.GetNetInfo().NetsByNetcode().values()):
  name=item.GetNetname()
  if name.startswith('/') and 'unconnected-(' not in name:item.SetNetname(name.lstrip('/'))
 expected={(c['ref'],p['number']):p for c in m['components'] for p in c['pins']}
 for fp in board.GetFootprints():
  for pad in fp.Pads():
   p=expected[(fp.GetReference(),pad.GetNumber())]
   if p['net']:continue
   n=nets[(fp.GetReference(),pad.GetNumber())];assert 'unconnected-(' in n,n
   if n not in created:
    item=k.NETINFO_ITEM(board,n);board.Add(item);created[n]=item
   pad.SetNet(created[n]);by_source[p['source_net']]=created[n]
 for z in board.Zones():
  if z.GetNetCode():continue
  layer,index=z.GetZoneName().split(': ')[1].split('/')
  raw=r.net_by_group[r.connections.find((layer,int(index)))]
  if raw in by_source:z.SetNet(by_source[raw])
 for t in board.GetTracks():
  if t.GetNetCode():continue
  pos=t.GetPosition();x=k.ToMM(pos.x)+r.min_x-20;y=r.max_y+20-k.ToMM(pos.y)
  layer='F.Cu' if isinstance(t,k.PCB_VIA) else board.GetLayerName(t.GetLayer())
  raw=r.net_at(layer,x,y)
  if raw in by_source:t.SetNet(by_source[raw])
 k.SaveBoard(str(FOLDER/(NAME+'.kicad_pcb')),board)
 print('isolated pad names synchronized',len(created),flush=True)


def export():
 pcb=FOLDER/(NAME+'.kicad_pcb');sch=FOLDER/(NAME+'.kicad_sch')
 commands=[('sch','export','svg','-o',str(BUILD)+'/',sch),
   ('sch','erc','--format','json','-o',BUILD/'erc.json',sch),
   ('pcb','export','gerbers','--layers','F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,Edge.Cuts','-o',str(BUILD/'gerbers')+'/',pcb),
   ('pcb','export','drill','-o',str(BUILD/'drills')+'/',pcb),
   ('pcb','export','svg','--layers','F.Cu,F.SilkS,Edge.Cuts','--mode-single','--fit-page-to-board','--exclude-drawing-sheet','-o',BUILD/'pcb-top.svg',pcb),
   ('pcb','export','svg','--layers','B.Cu,B.SilkS,Edge.Cuts','--mode-single','--fit-page-to-board','--exclude-drawing-sheet','-o',BUILD/'pcb-bottom.svg',pcb),
   ('pcb','drc','--schematic-parity','--format','json','-o',BUILD/'drc.json',pcb)]
 with ThreadPoolExecutor(max_workers=3) as pool:
  results=list(pool.map(lambda c:run(*c),commands))
 for c,result in zip(commands,results):print('export',c[:3],result[-160:],flush=True)


def validate(r,m):
 board=k.LoadBoard(str(FOLDER/(NAME+'.kicad_pcb')))
 clean=lambda n:'' if 'unconnected-(' in n else n.lstrip('/')
 expected={(c['ref'],p['number']):p['net'] for c in m['components'] for p in c['pins']}
 sch={}
 for n in ET.parse(BUILD/'netlist.xml').getroot().findall('nets/net'):
  for node in n.findall('node'):sch[(node.get('ref'),node.get('pin'))]=clean(n.get('name'))
 pcb={(f.GetReference(),p.GetNumber()):clean(p.GetNetname()) for f in board.GetFootprints() for p in f.Pads()}
 errors=[{'pin':key,'expected':n,'schematic':sch.get(key),'pcb':pcb.get(key)} for key,n in expected.items() if n!=sch.get(key) or n!=pcb.get(key)]
 assert not errors,errors
 positions={(f.GetReference(),p.GetNumber()):(k.ToMM(p.GetPosition().x),k.ToMM(p.GetPosition().y)) for f in board.GetFootprints() for p in f.Pads()}
 pad_error=max(math.dist(positions[(c['ref'],p['number'])],p['position_mm']) for c in m['components'] for p in c['pins'])
 assert pad_error<.00001,pad_error
 holes=[]
 for f in board.GetFootprints():
  for p in f.Pads():
   size=p.GetDrillSize();d=min(k.ToMM(size.x),k.ToMM(size.y))
   if d:holes.append((k.ToMM(p.GetPosition().x),k.ToMM(p.GetPosition().y),d))
 for t in board.GetTracks():
  if isinstance(t,k.PCB_VIA):holes.append((k.ToMM(t.GetPosition().x),k.ToMM(t.GetPosition().y),k.ToMM(t.GetDrillValue())))
 assert len(holes)==len(r.drills),(len(holes),len(r.drills))
 drill_error=max(min(math.dist((x,y),r.xy(*xy))+abs(d-diameter) for x,y,d in holes) for xy,diameter in r.drills.items())
 assert drill_error<.002,drill_error
 copper={}
 for layer,suffix in [('F.Cu','F_Cu.gtl'),('In1.Cu','In1_Cu.g1'),('In2.Cu','In2_Cu.g2'),('B.Cu','B_Cu.gbl')]:
  source=r.copper[layer];native=composite(GerberFile.open(BUILD/'gerbers'/(NAME+'-'+suffix)))
  native=translate(native,xoff=r.min_x-20,yoff=r.max_y+20)
  extra=native.difference(source.buffer(.002)).area;missing=source.difference(native.buffer(.002)).area
  copper[layer]={'source_area_mm2':source.area,'exported_area_mm2':native.area,'symmetric_difference_mm2':source.symmetric_difference(native).area,
                 'extra_beyond_2um_mm2':extra,'missing_beyond_2um_mm2':missing,'within_2um_tolerance':extra<.00001 and missing<.00001}
  print('copper',layer,copper[layer],flush=True)
 # Parse mask/paste source fresh: cached Gerbonara macro unit objects lose
 # singleton identity through pickle. Cached Shapely copper is safe to compare.
 mask_paste={}
 with zipfile.ZipFile(ROOT/SOURCE) as archive:
  for layer,member,suffix in [('F.Mask','Gerber_TopSolderMaskLayer.GTS','F_Mask.gts'),
                            ('B.Mask','Gerber_BottomSolderMaskLayer.GBS','B_Mask.gbs'),
                            ('F.Paste','Gerber_TopPasteMaskLayer.GTP','F_Paste.gtp')]:
   source=composite(GerberFile.from_string(archive.read(member).decode()))
   native=composite(GerberFile.open(BUILD/'gerbers'/(NAME+'-'+suffix)))
   native=translate(native,xoff=r.min_x-20,yoff=r.max_y+20)
   mask_paste[layer]={'source_area_mm2':source.area,'exported_area_mm2':native.area,
                     'symmetric_difference_mm2':source.symmetric_difference(native).area}
 (FOLDER/'mask-paste-comparison.json').write_text(json.dumps(mask_paste,indent=2)+'\n')
 erc=json.loads((BUILD/'erc.json').read_text());drc=json.loads((BUILD/'drc.json').read_text())
 violations=[v for sheet in erc['sheets'] for v in sheet['violations']]
 report={'name':NAME,'kicad_version':drc['kicad_version'],'matched_pads':len(expected),'copper_layers':board.GetCopperLayerCount(),
   'matched_plated_drills':len(holes),'source_axis_aligned_slots':len(r.drill_slots),
   'maximum_pad_position_error_mm':pad_error,'maximum_drill_error_mm':drill_error,
   'schematic_board_model_net_mismatches':errors,'copper_comparison':copper,'mask_paste_comparison':mask_paste,
   'erc_counts':dict(Counter(v['type'] for v in violations)),'drc_counts':dict(Counter(v['type'] for v in drc['violations'])),
   'unconnected_items':len(drc['unconnected_items']),'schematic_parity_counts':dict(Counter(v['type'] for v in drc['schematic_parity'])),
   'notes':['Recovered copper contours are reference geometry, not original editable pour intent.',
            'Electrical types on custom source symbols are passive when the source does not establish them.',
            'No exclusions were added. DRC results are reported under working rules, not a recovered fabrication specification.']}
 (FOLDER/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report),flush=True)
 assert not drc['schematic_parity'],drc['schematic_parity'][:8]
 assert not drc['unconnected_items'],drc['unconnected_items'][:8]
 assert not any(x['type'].startswith('lib_') for x in drc['violations'])
 assert all(x['within_2um_tolerance'] for x in copper.values()),'CAM copper comparison outside tolerance'
 return report

if __name__=='__main__':
 with (BUILD/'recovery-cache.pkl').open('rb') as f:r=pickle.load(f)
 m=json.loads((FOLDER/'recovery.json').read_text())
 sync(r,m);export();validate(r,m)
