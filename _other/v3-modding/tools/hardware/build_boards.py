"""Create editable pads, footprints, tracks, vias and copper zones in KiCad."""
from collections import defaultdict, Counter
import csv
import hashlib
import json
import math
from pathlib import Path

import pcbnew as k
from gerbonara import graphic_primitives as gp
from gerbonara.utils import MM
from shapely.prepared import prep

from recover import ROOT, OUTPUT, Recovery, SOURCES, ident, polygon_parts, object_shape

LIBRARY = 'MicroSMT_Recovered'
VALUES = {**{f'C{i}':'100nF' for i in range(1,19)}, 'C6':'22pF','C8':'22pF',
    'C16':'100uF','C17':'100uF', **{f'R{i}':'10k' for i in range(1,4)},
    **{f'R{i}':'510' for i in range(4,7)}, 'U1':'AMS1117-3.3',
    'U2':'STM32C8T6', 'U3':'TC1508A', 'D1':'SS34', 'X1':'8MHz',
    'H1':'Host interface', 'H2':'SWD', 'CN1':'EE-SX672 interface',
    'U4':'Motor 1', 'U5':'Motor 2', 'SW1':'TS-1093A-A6B2-D2',
    'LED1':'3V3', 'LED2':'Status', 'LED3':'5V'}
ALIASES = {'$1N25822':'HOST_VIN', '$1N2515':'OSC_IN', '$1N2524':'OSC_OUT',
    '$1N8413':'NRST', '$1N2174':'BOOT0', '$1N1866':'PB2_BOOT1',
    '$1N2137':'PA0', '$1N2133':'PA1', '$1N4463':'LED_3V3_A',
    '$1N4467':'LED_STATUS_A', '$1N24150':'LED_5V_A',
    '$1N28406':'MOTOR1_A', '$1N28296':'MOTOR1_B',
    '$1N28093':'MOTOR2_B', '$1N28135':'MOTOR2_A'}


def vec(x,y): return k.VECTOR2I(round(x*1_000_000),round(y*1_000_000))
def point_tuple(v): return (k.ToMM(v.x),k.ToMM(v.y))


def flash_near(r, layer, x, y):
    candidates=[f for f in r.flashes.get(layer,[]) if math.hypot(f.x-x,f.y-y)<0.002]
    return max(candidates,key=lambda f:object_shape(f).area) if candidates else None


def add_inferred_components(r):
    leftover=[]
    for xy,drill in r.drills.items():
        if drill<=0.5 or any(math.dist(xy,(p['x'],p['y']))<0.002 for p in r.pins.values()):
            continue
        leftover.append((xy,drill))
    # Only the busbars have unreferenced 2x12 header holes. Their numbering is
    # intentionally new: top-view top-to-bottom, left odd/right even.
    headers=defaultdict(list)
    holes=[]
    for xy,drill in leftover:
        if r.name.startswith('busbar') and drill<1:
            headers['left' if xy[0]<r.min_x+r.width/2 else 'right'].append((xy,drill))
        else: holes.append((xy,drill))
    groups=[]
    for i,(side,items) in enumerate(sorted(headers.items()),1):
        assert len(items)==24, (r.name,side,len(items))
        xs=sorted({round(xy[0],3) for xy,d in items})
        assert len(xs)==2
        indexed=[]
        for col,x in enumerate(xs):
            points=sorted([(xy,d) for xy,d in items if abs(xy[0]-x)<0.001],
                          key=lambda item:-item[0][1])
            for row,(xy,d) in enumerate(points): indexed.append((str(2*row+col+1),xy,d))
        groups.append((f'JREC{i}',indexed,'Recovered 2x12 / 2mm header'))
    for i,(xy,d) in enumerate(sorted(holes),1):
        groups.append((f'MH{i}',[('1',xy,d)],f'Plated mounting hole {d:g}mm'))
    r.inferred_refs=[]
    for ref,items,value in groups:
        cx=sum(xy[0] for _,xy,d in items)/len(items)
        cy=sum(xy[1] for _,xy,d in items)/len(items)
        r.components[ref]={'COMPONENT_NAME':ref,'X_COORDINATE':cx/0.0254,
            'Y_COORDINATE':cy/0.0254,'ANGLE':0,'inferred':True,'value':value}
        r.inferred_refs.append(ref)
        for number,(x,y),drill in items:
            f=flash_near(r,'F.Cu',x,y)
            assert f is not None
            x0,y0,x1,y1=object_shape(f).bounds
            r.pins[(ref,number)]={'ref':ref,'number':number,'x':x,'y':y,
                'global_width':x1-x0,'global_height':y1-y0,'drill':drill,'flash':f,
                'PAD_SHAPE':'C','NET_NAME':r.net_at('F.Cu',x,y),
                'PIN_NAME':ref+'_'+number,'PIN_TYPE':'DIP'}
    counts=Counter(p['NET_NAME'] for p in r.pins.values())
    r.net_aliases={}
    for p in r.pins.values():
        raw=p['NET_NAME']
        # Single-pad generated names describe intentionally isolated pads.
        connected=not (counts[raw]==1 and (raw==p['PIN_NAME'] or raw.startswith('RECOVERED_')))
        p['net']=getattr(r,'aliases',ALIASES).get(raw,raw) if connected else ''
        r.net_aliases[raw]=p['net']


def make_polyset(poly, r):
    result=k.SHAPE_POLY_SET()
    outline=result.NewOutline()
    for x,y in list(poly.exterior.coords)[:-1]:result.Append(vec(*r.xy(x,y)),outline)
    for interior in poly.interiors:
        hole=result.NewHole(outline)
        for x,y in list(interior.coords)[:-1]:result.Append(vec(*r.xy(x,y)),outline,hole)
    return result


def add_zone(board,r,poly,layer,net,tag):
    if poly.area<1e-9:return
    zone=k.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(net)
    zone.SetLocalClearance(0)
    zone.SetMinThickness(k.FromMM(0.001))
    zone.SetPadConnection(k.ZONE_CONNECTION_FULL)
    shape=make_polyset(poly,r)
    zone.SetOutline(shape)
    shape.thisown=False
    filled=make_polyset(poly,r)
    filled.Fracture()
    zone.SetFilledPolysList(layer,filled)
    zone.SetIsFilled(True)
    zone.SetFillFlag(layer,False)
    zone.SetZoneName('Recovered copper: '+tag)
    board.Add(zone)


def add_graphics(board,r,layer):
    layerid={"F.SilkS":k.F_SilkS,"B.SilkS":k.B_SilkS}.get(layer,board.GetLayerID(layer))
    for i,obj in enumerate(r.layers[layer].objects):
        assert obj.polarity_dark
        for j,p in enumerate(obj.to_primitives(MM)):
            shape=k.PCB_SHAPE()
            shape.SetLayer(layerid)
            if isinstance(p,gp.Line):
                shape.SetShape(k.SHAPE_T_SEGMENT)
                shape.SetStart(vec(*r.xy(p.x1,p.y1)));shape.SetEnd(vec(*r.xy(p.x2,p.y2)))
                shape.SetWidth(k.FromMM(p.width if layer!='Edge.Cuts' else 0.05))
            elif isinstance(p,gp.Arc):
                # Silk arcs converted to fine editable polygon strokes.
                for m,poly in enumerate(polygon_parts(object_shape(obj))):
                    add_graphic_polygon(board,r,poly,layerid,f'{layer}/{i}/{j}/{m}')
                continue
            else:
                for m,poly in enumerate(polygon_parts(object_shape(obj))):
                    add_graphic_polygon(board,r,poly,layerid,f'{layer}/{i}/{j}/{m}')
                continue
            board.Add(shape)


def add_graphic_polygon(board,r,poly,layer,tag):
    shape=k.PCB_SHAPE()
    shape.SetLayer(layer);shape.SetShape(k.SHAPE_T_POLY)
    shape.SetPolyShape(make_polyset(poly,r));shape.SetFilled(True);shape.SetWidth(0)
    board.Add(shape)


def make_board(r, values=None):
    assert not r.conflicts, r.conflicts
    add_inferred_components(r)
    output=OUTPUT/r.name;output.mkdir(parents=True,exist_ok=True)
    lib=OUTPUT/'libraries'/(LIBRARY+'.pretty');lib.mkdir(parents=True,exist_ok=True)
    board=k.BOARD()
    board.SetCopperLayerCount(len(r.copper_layers))
    board.GetDesignSettings().SetBoardThickness(k.FromMM(1.6))
    nets={}
    for name in sorted({r.net_aliases.get(n,n) for n in r.net_by_group.values()}|{''}):
        if not name:continue
        item=k.NETINFO_ITEM(board,"/"+name);board.Add(item);nets[name]=item
    def net_for(raw):return nets.get(r.net_aliases.get(raw,raw),board.FindNet(0))
    covered_drills=set()
    components=[]
    for ref,comp in r.components.items():
        cx,cy=comp['X_COORDINATE']*0.0254,comp['Y_COORDINATE']*0.0254
        fp=k.FOOTPRINT(board);fp.SetReference(ref)
        fp.SetValue(comp.get('value',(values or VALUES).get(ref,'Feeder slot' if ref.startswith('N') else ref)))
        fp.SetPath(k.KIID_PATH('/'+ident(r.name+'/schematic')+'/'+ident(r.name+'/symbol/'+ref)))
        pins=[p for (pr,num),p in r.pins.items() if pr==ref]
        for p in pins:
            pad=k.PAD(fp);pad.SetNumber(p['number'])
            pad.SetPosition(vec(p['x']-cx,-(p['y']-cy)))
            pad.SetSize(vec(p['global_width'],p['global_height']))
            if p['PAD_SHAPE']=='P':
                pad.SetShape(k.PAD_SHAPE_CUSTOM)
                pad.SetAnchorPadShape(k.F_Cu,k.PAD_SHAPE_RECT)
                pad.SetSize(vec(.01,.01))
                for poly in polygon_parts(p['pad_geometry']):
                    shape=k.SHAPE_POLY_SET();outline=shape.NewOutline()
                    for x,y in list(poly.exterior.coords)[:-1]:shape.Append(vec(x-p['x'],p['y']-y),outline)
                    for interior in poly.interiors:
                        hole=shape.NewHole(outline)
                        for x,y in list(interior.coords)[:-1]:shape.Append(vec(x-p['x'],p['y']-y),outline,hole)
                    pad.AddPrimitivePoly(k.F_Cu,shape,0,True)
            else:
                pad.SetShape({'R':k.PAD_SHAPE_RECT,'C':k.PAD_SHAPE_CIRCLE,'O':k.PAD_SHAPE_OVAL}[p['PAD_SHAPE']])
            if p['drill']:
                pad.SetAttribute(k.PAD_ATTRIB_PTH);pad.SetDrillSize(vec(p['drill'],p['drill']))
                if 'drill_size' in p:
                    pad.SetDrillShape(k.PAD_DRILL_SHAPE_OBLONG);pad.SetDrillSize(vec(*p['drill_size']))
                layers=[k.F_Cu,k.B_Cu]
                covered_drills.add(min(r.drills,key=lambda xy:math.dist(xy,(p['x'],p['y']))))
            else:pad.SetAttribute(k.PAD_ATTRIB_SMD);layers=[k.F_Cu]
            margins={}
            for layer in ('F.Mask','B.Mask','F.Paste'):
                flash=flash_near(r,layer,p['x'],p['y'])
                if flash:
                    x0,y0,x1,y1=object_shape(flash).bounds
                    margins[layer]=((x1-x0-p['global_width'])/2+(y1-y0-p['global_height'])/2)/2
                    layers.append(board.GetLayerID(layer))
            if any(key.endswith('Mask') for key in margins):
                pad.SetLocalSolderMaskMargin(k.FromMM(margins.get('F.Mask',margins.get('B.Mask',0))))
            if 'F.Paste' in margins:pad.SetLocalSolderPasteMargin(k.FromMM(margins['F.Paste']))
            layer_set=k.LSET.AllCuMask() if p['drill'] else k.LSET()
            for layer_id in layers:layer_set.AddLayer(layer_id)
            pad.SetLayerSet(layer_set);fp.Add(pad)
        angle=comp['ANGLE']
        # Convert the source component into a canonical local footprint before
        # hashing/saving, then restore its board orientation and location.
        fp.SetOrientationDegrees(-angle)
        canonical=[(p, k.VECTOR2I(p.GetPosition()), p.GetOrientationDegrees()) for p in fp.Pads()]
        fp.SetOrientationDegrees(0)
        for p, position, orientation in canonical:
            p.SetPosition(position);p.SetOrientationDegrees(orientation)
        fingerprint=[]
        for pad in fp.Pads():
            fingerprint.append([pad.GetNumber(),*[round(v,6) for v in point_tuple(pad.GetPosition())],
                *[round(v,6) for v in point_tuple(pad.GetSize())],
                round(pad.GetOrientationDegrees()%360,6),pad.GetShape(),
                *[round(v,6) for v in point_tuple(pad.GetDrillSize())],
                pad.GetLocalSolderMaskMargin(),pad.GetLocalSolderPasteMargin(),pad.GetLayerSet().FmtHex()])
            source_pin=r.pins[(ref,pad.GetNumber())]
            if source_pin['PAD_SHAPE']=='P':
                from shapely.affinity import translate
                local=translate(source_pin['pad_geometry'],xoff=-source_pin['x'],yoff=-source_pin['y'])
                fingerprint[-1].append(local.normalize().wkb_hex)
        prefix=('PTH' if all(p['drill'] for p in pins) else 'SMD')+f'_{len(pins)}'
        fpname=prefix+'_'+hashlib.sha256(json.dumps(sorted(fingerprint)).encode()).hexdigest()[:10]
        fp.SetFPID(k.LIB_ID(LIBRARY,fpname))
        fp.Reference().SetLayer(k.F_Fab);fp.Reference().SetTextSize(vec(.7,.7))
        fp.Reference().SetTextThickness(k.FromMM(.12));fp.Reference().SetPosition(vec(0,-2))
        fp.Value().SetVisible(False)
        fp.SetAttributes(k.FP_THROUGH_HOLE if all(p['drill'] for p in pins) else k.FP_SMD)
        saved_ref=fp.GetReference();fp.SetReference('REF**')
        k.PCB_IO_MGR.PluginFind(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(lib),fp)
        fp.SetReference(saved_ref)
        fp.SetOrientationDegrees(angle)
        fp.SetPosition(vec(*r.xy(cx,cy)))
        for pad in fp.Pads():
            p=r.pins[(ref,pad.GetNumber())]
            assert math.dist(point_tuple(pad.GetPosition()),r.xy(p['x'],p['y']))<.00001, (ref, pad.GetNumber(), point_tuple(pad.GetPosition()), r.xy(p['x'],p['y']), angle)
            pad.SetNet(net_for(p['NET_NAME']))
        board.Add(fp)
        components.append({'ref':ref,'value':fp.GetValue(),'footprint':LIBRARY+':'+fpname,
            'uuid':ident(r.name+'/symbol/'+ref),'inferred':bool(comp.get('inferred')),
            'pins':[{'number':p['number'],'source_net':p['NET_NAME'],'net':p['net'],
                     'position_mm':list(r.xy(p['x'],p['y'])),'drill_mm':p['drill']}
                    for p in pins]})
    for index,(xy,drill) in enumerate(r.drills.items()):
        if xy in covered_drills:continue
        assert drill<=.5
        f=flash_near(r,'F.Cu',*xy);b=flash_near(r,'B.Cu',*xy)
        assert f and b
        if hasattr(f.aperture,'diameter') and hasattr(b.aperture,'diameter'):
            width=min(f.aperture.diameter,b.aperture.diameter)
        else:
            # A via-in-pad can have rectangular copper on one side. The native
            # via uses the largest common inscribed circle; zones retain CAM copper.
            bounds=[object_shape(obj).bounds for obj in (f,b)]
            width=min(min(x1-x0,y1-y0) for x0,y0,x1,y1 in bounds)
        via=k.PCB_VIA(board);via.SetPosition(vec(*r.xy(*xy)))
        via.SetDrill(k.FromMM(drill));via.SetWidth(k.F_Cu,k.FromMM(width))
        via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetViaType(k.VIATYPE_THROUGH)
        via.SetNet(net_for(r.net_at('F.Cu',*xy)));board.Add(via)
    # Native tracks retain the original centerline and width. Any clear-polarity
    # clipping is recovered as zone geometry, so the final copper stays faithful.
    for layer in r.copper_layers:
        layerid=board.GetLayerID(layer)
        prepared_copper=prep(r.copper[layer].buffer(0.000001))
        kept=[]
        for index,(obj,geometry) in enumerate(zip(r.layers[layer].objects,r.object_geometries[layer])):
            if not obj.polarity_dark or type(obj).__name__ not in ('Line','Arc'):continue
            if not prepared_copper.covers(geometry):continue
            p=list(obj.to_primitives(MM))[0]
            center=geometry.representative_point()
            raw=r.net_at(layer,center.x,center.y)
            if isinstance(p,gp.Line):
                track=k.PCB_TRACK(board)
                track.SetStart(vec(*r.xy(p.x1,p.y1)));track.SetEnd(vec(*r.xy(p.x2,p.y2)))
            elif isinstance(p,gp.Arc):
                if p.is_circle:continue
                track=k.PCB_ARC(board)
                start=math.atan2(p.y1-p.cy,p.x1-p.cx);end=math.atan2(p.y2-p.cy,p.x2-p.cx)
                sweep=(end-start)%(2*math.pi)
                if p.clockwise:sweep-=2*math.pi
                radius=math.hypot(p.x1-p.cx,p.y1-p.cy)
                mid=start+sweep/2
                track.SetStart(vec(*r.xy(p.x1,p.y1)))
                track.SetMid(vec(*r.xy(p.cx+radius*math.cos(mid),p.cy+radius*math.sin(mid))))
                track.SetEnd(vec(*r.xy(p.x2,p.y2)))
            else:continue
            track.SetLayer(layerid);track.SetWidth(k.FromMM(p.width));track.SetNet(net_for(raw))
            board.Add(track);kept.append(geometry)
        # Use final composited copper islands as zone contours. Original tracks
        # and pads overlap same-net copper; no guessed pour boundary is introduced.
        for index,poly in enumerate(r.islands[layer]):
            group=r.connections.find((layer,index));raw=r.net_by_group[group]
            add_zone(board,r,poly,layerid,net_for(raw),f'{layer}/{index}')
    for layer in ('Edge.Cuts','F.SilkS','B.SilkS'):
        add_graphics(board,r,layer)
    # Openings not generated by ordinary pads are preserved as mask graphics.
    # This includes original exposed copper regions and mounting annuli.
    for layer in ('F.Mask','B.Mask','F.Paste'):
        if layer not in r.layers:continue
        for index,obj in enumerate(r.layers[layer].objects):
            if type(obj).__name__=='Flash' and any(math.dist((obj.x,obj.y),(p['x'],p['y']))<.002 for p in r.pins.values()):
                continue
            for j,poly in enumerate(polygon_parts(object_shape(obj))):
                add_graphic_polygon(board,r,poly,board.GetLayerID(layer),f'{layer}/{index}/{j}')
    filename=output/(r.name+'.kicad_pcb')
    assert k.SaveBoard(str(filename),board)
    loaded=k.LoadBoard(str(filename))
    assert len(list(loaded.GetFootprints()))==len(components)
    model={'name':r.name,'source':r.source,'components':components,
        'aliases':r.net_aliases,'dimensions_mm':[r.width,r.height],
        'coordinate_transform':{'x_offset_mm':20-r.min_x,'y_offset_mm':20+r.max_y,'invert_y':True},
        'source_summary':r.summary(),
        'inferred_references':r.inferred_refs,
        'board_counts':{'copper_layers':len(r.copper_layers),'footprints':len(components),'tracks_and_vias':len(list(loaded.GetTracks())),
                        'zones':len(list(loaded.Zones()))}}
    (output/'recovery.json').write_text(json.dumps(model,indent=2)+'\n')
    with (output/'components.csv').open('w',newline='') as stream:
        writer=csv.writer(stream,lineterminator="\n")
        writer.writerow(['Reference','Value','Recovered footprint','Pad count','Inferred reference'])
        writer.writerows((c['ref'],c['value'],c['footprint'],len(c['pins']),c['inferred']) for c in components)
    (output/'fp-lib-table').write_text('(fp_lib_table\n (version 7)\n'
        f' (lib (name "{LIBRARY}")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/../libraries/{LIBRARY}.pretty")(options "")'
        '(descr "Pad geometry recovered from the preserved CAM exports"))\n)\n')
    project={'meta':{'filename':r.name+'.kicad_pro','version':1},
             'board':{'design_settings':{'rules':{'min_clearance':0.1,'min_track_width':0.1,
                'min_via_diameter':0.4,'min_through_hole_diameter':0.2,
                'min_via_annular_width':0.05,'min_hole_clearance':0.15},
                'defaults':{'zones':{'min_clearance':0.1}}}}}
    (output/(r.name+'.kicad_pro')).write_text(json.dumps(project,indent=2)+'\n')
    print(r.name,model['board_counts'],flush=True)
    return model


if __name__=='__main__':
    models=[make_board(Recovery(name)) for name in SOURCES]
    used={c['footprint'].split(':')[1] for m in models for c in m['components']}
    for file in (OUTPUT/'libraries'/(LIBRARY+'.pretty')).glob('*.kicad_mod'):
        if file.stem not in used:file.unlink()
