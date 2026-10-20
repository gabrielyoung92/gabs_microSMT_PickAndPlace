"""Give isolated CAM pads KiCad's schematic-generated unconnected net names.

This changes names only. No copper, routing or source connectivity is changed.
"""
import json
import xml.etree.ElementTree as ET
import pcbnew as k
from recover import OUTPUT, ROOT, SOURCES, Recovery
from validate import run, BUILD


def sync(name):
    folder=OUTPUT/name;out=BUILD/name;out.mkdir(parents=True,exist_ok=True)
    run('sch','export','netlist','--format','kicadxml','-o',out/'netlist.xml',folder/(name+'.kicad_sch'))
    model=json.loads((folder/'recovery.json').read_text())
    expected={(c['ref'],p['number']):p for c in model['components'] for p in c['pins']}
    nets={}
    for net in ET.parse(out/'netlist.xml').getroot().findall('nets/net'):
        for node in net.findall('node'):nets[(node.get('ref'),node.get('pin'))]=net.get('name')
    r=Recovery(name);board=k.LoadBoard(str(folder/(name+'.kicad_pcb')))
    raw_map={};created={}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            key=(fp.GetReference(),pad.GetNumber());pin=expected[key]
            if pin['net']:continue
            label=nets[key];assert label.startswith('unconnected-'),(key,label)
            item=k.NETINFO_ITEM(board,label);board.Add(item);pad.SetNet(item)
            raw_map[pin['source_net']]=item;created[label]=item
    for zone in board.Zones():
        if zone.GetNetCode()!=0:continue
        layer,index=zone.GetZoneName().split(': ')[1].split('/')
        raw=r.net_by_group[r.connections.find((layer,int(index)))]
        if raw in raw_map:zone.SetNet(raw_map[raw])
    for track in board.GetTracks():
        if track.GetNetCode()!=0:continue
        pos=track.GetPosition();x=k.ToMM(pos.x)+r.min_x-20;y=r.max_y+20-k.ToMM(pos.y)
        layer='F.Cu' if track.GetLayer()==k.F_Cu else 'B.Cu'
        raw=r.net_at(layer,x,y)
        if raw in raw_map:track.SetNet(raw_map[raw])
    k.SaveBoard(str(folder/(name+'.kicad_pcb')),board)
    print(name,len(created),'isolated pad nets synchronized',flush=True)

if __name__=='__main__':
    for name in SOURCES:sync(name)
