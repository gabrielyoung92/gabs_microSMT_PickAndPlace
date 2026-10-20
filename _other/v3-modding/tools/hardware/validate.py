"""Run KiCad checks and compare native outputs with the preserved CAM evidence."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import pcbnew as k
from gerbonara import GerberFile
from shapely import union_all
from shapely.geometry import Polygon
from shapely.affinity import translate
from recover import ROOT, OUTPUT, SOURCES, Recovery, object_shape

BUILD=ROOT/'build'/'hardware'

def run(*args):
    p=subprocess.run(['kicad-cli',*map(str,args)],capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stdout+p.stderr)
    return p.stdout

def export(name):
    folder=OUTPUT/name;out=BUILD/name;out.mkdir(parents=True,exist_ok=True)
    pcb=folder/(name+'.kicad_pcb');sch=folder/(name+'.kicad_sch')
    run('sch','export','netlist','--format','kicadxml','-o',out/'netlist.xml',sch)
    run('sch','export','svg','-o',str(out)+'/',sch)
    run('sch','erc','--format','json','-o',out/'erc.json',sch)
    run('pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,Edge.Cuts','-o',str(out/'gerbers')+'/',pcb)
    run('pcb','export','svg','--layers','F.Cu,F.SilkS,Edge.Cuts','--mode-single','--fit-page-to-board','--exclude-drawing-sheet','-o',out/'pcb-top.svg',pcb)
    run('pcb','export','svg','--layers','B.Cu,B.SilkS,Edge.Cuts','--mode-single','--fit-page-to-board','--exclude-drawing-sheet','-o',out/'pcb-bottom.svg',pcb)
    run('pcb','drc','--schematic-parity','--format','json','-o',out/'drc.json',pcb)
    return name

def composite(file):
    result=Polygon();pending=[]
    for obj in file.objects:
        geom=object_shape(obj)
        if obj.polarity_dark:pending.append(geom)
        else:result=union_all([result,*pending]).difference(geom);pending=[]
    return union_all([result,*pending])

def validate(name):
    folder=OUTPUT/name;out=BUILD/name
    m=json.loads((folder/'recovery.json').read_text());r=Recovery(name)
    board=k.LoadBoard(str(folder/(name+'.kicad_pcb')));assert board
    netlist=ET.parse(out/'netlist.xml').getroot()
    sch={}
    for net in netlist.findall('nets/net'):
        raw=net.get('name');n=raw.lstrip('/')
        if n.startswith('unconnected-'):n=''
        for node in net.findall('node'):sch[(node.get('ref'),node.get('pin'))]=n
    pcb={(fp.GetReference(),p.GetNumber()):p.GetNetname().lstrip('/') for fp in board.GetFootprints() for p in fp.Pads()}
    pcb={key:('' if value.startswith('unconnected-') else value) for key,value in pcb.items()}
    expected={(c['ref'],p['number']):p['net'] for c in m['components'] for p in c['pins']}
    errors=[]
    for key,value in expected.items():
        if sch.get(key,'')!=value:errors.append(['schematic',key,value,sch.get(key)])
        if pcb.get(key,'')!=value:errors.append(['pcb',key,value,pcb.get(key)])
    assert not errors,errors
    pad_positions={(fp.GetReference(),p.GetNumber()):(k.ToMM(p.GetPosition().x),k.ToMM(p.GetPosition().y)) for fp in board.GetFootprints() for p in fp.Pads()}
    pad_error=max(math.dist(pad_positions[(c['ref'],p['number'])],p['position_mm']) for c in m['components'] for p in c['pins'])
    assert pad_error<.00001
    holes=[]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            d=k.ToMM(pad.GetDrillSize().x)
            if d:holes.append((k.ToMM(pad.GetPosition().x),k.ToMM(pad.GetPosition().y),d))
    for item in board.GetTracks():
        if isinstance(item,k.PCB_VIA):holes.append((k.ToMM(item.GetPosition().x),k.ToMM(item.GetPosition().y),k.ToMM(item.GetDrillValue())))
    assert len(holes)==len(r.drills),(name,len(holes),len(r.drills))
    drill_error=max(min(math.dist((x,y),r.xy(*xy))+abs(d-diameter) for x,y,d in holes) for xy,diameter in r.drills.items())
    assert drill_error<.002
    copper={}
    for layer,suffix in [('F.Cu','F_Cu.gtl'),('B.Cu','B_Cu.gbl')]:
        exported=composite(GerberFile.open(out/'gerbers'/(name+'-'+suffix)))
        exported=translate(exported,xoff=r.min_x-20,yoff=r.max_y+20)
        source=r.copper[layer]
        extra=exported.difference(source.buffer(.002)).area
        missing=source.difference(exported.buffer(.002)).area
        assert extra<.00001 and missing<.00001, (name,layer,extra,missing)
        copper[layer]={'source_area_mm2':source.area,'exported_area_mm2':exported.area,
            'symmetric_difference_mm2':source.symmetric_difference(exported).area,
            'extra_beyond_2um_mm2':extra,'missing_beyond_2um_mm2':missing}
    erc=json.loads((out/'erc.json').read_text());drc=json.loads((out/'drc.json').read_text())
    ercs=[v for sheet in erc['sheets'] for v in sheet['violations']]
    report={'name':name,'kicad_version':drc['kicad_version'],'matched_pads':len(expected),
       'schematic_board_model_net_mismatches':errors,'maximum_pad_position_error_mm':pad_error,
       'matched_plated_drills':len(holes),'maximum_drill_error_mm':drill_error,'copper_comparison':copper,
       'erc_counts':dict(Counter(v['type'] for v in ercs)),
       'drc_counts':dict(Counter(v['type'] for v in drc['violations'])),
       'unconnected_items':len(drc['unconnected_items']),
       'schematic_parity_counts':dict(Counter(v['type'] for v in drc['schematic_parity']))}
    assert not drc['unconnected_items'], (name,'unrouted connections')
    assert not drc['schematic_parity'], (name,'schematic parity')
    assert not any(v['type'].startswith('lib_') for v in drc['violations']), (name,'library mismatch')
    if name=='feeder_v2':
        assert len(ercs)==2 and all(v['type']=='label_dangling' for v in ercs)
        assert {v['items'][0]['description'] for v in ercs}=={"Label 'PA0'","Label 'PA1'"}
    else:assert not ercs
    (folder/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    return report

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(export,SOURCES))
    for name in SOURCES:validate(name)
