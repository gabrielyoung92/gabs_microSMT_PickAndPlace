#!/usr/bin/env python3
"""Recover the remaining MicroSMT boards without regenerating earlier projects.

Run from the repository root with KiCad's pcbnew bindings and requirements.txt.
The three 180 mm variants share a KiCad folder but keep separate project names,
local libraries and evidence files. Never overwrite a hand-edited reference.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

import pcbnew as k
import sexpdata as sx
from shapely.geometry import Point
import recover
import build_boards as bb
import build_schematics as bs

SOURCES = {
    'v3_controller': 'Bing-feeder/V3-Feeder Controller/PCB_ControlBoard/V3_controller_48_feeders_gerber.zip',
    'v485_controller': 'Bing-feeder/V485-Feeder Controller/PCB_ControlBoard/Gerber_PCB1_2026-10-09.zip',
    'v485_busbar_480mm': 'Bing-feeder/V485-Feeder Controller/PCB_busbar_long_480mm/Gerber_PCB1_2026-10-09.zip',
    'v485_busbar_180mm_pcb1': 'Bing-feeder/V485-Feeder Controller/PCB_busbar_short_180mm/Gerber_PCB1_2026-10-09.zip',
    'v485_busbar_180mm_pcb2': 'Bing-feeder/V485-Feeder Controller/PCB_busbar_short_180mm/Gerber_PCB2_2026-10-09.zip',
    'v485_busbar_180mm_pcb4': 'Bing-feeder/V485-Feeder Controller/PCB_busbar_short_180mm/Gerber_PCB4_2026-10-09.zip',
    'v485_display': 'Bing-feeder/V485-feeder/PCB_display/Gerber_PCB1_2026-10-09.zip',
    'v485_feeder': 'Bing-feeder/V485-feeder/PCB_feeder/Gerber_PCB3_2026-10-09.zip',
}


def paths(name):
    board = (recover.ROOT / SOURCES[name]).resolve().parent
    prefix = name + '-' if '180mm' in name else ''
    return board, board/'KiCad', board/'docs', prefix


def normalize_probe(probe):
    """Collapse duplicate PTH faces/export rows only after physical/net agreement."""
    probe = deepcopy(probe)
    fields = probe['pins']['fields']
    unique = {}
    for row in probe['pins']['rows']:
        pin = dict(zip(fields, row))
        key = pin['PIN_NAME']
        if key in unique:
            previous = dict(zip(fields, unique[key]))
            for field in fields:
                if field not in {'PIN_NO', 'LAYER'}:
                    assert previous[field] == pin[field], (key, field, previous[field], pin[field])
            assert pin['PIN_TYPE'] == 'DIP' or previous['LAYER'] == pin['LAYER'], key
        else:
            unique[key] = row
    probe['pins']['rows'] = list(unique.values())
    return probe


def load(name):
    r = recover.Recovery(name, SOURCES[name], normalize_probe, both_sides=True)
    r.aliases = {}  # The earlier feeder's anonymous-net aliases do not apply here.
    r.report_prefix = paths(name)[3]
    return r


def infer_holes(r):
    """Retain unreferenced holes without guessing their connector/mounting purpose."""
    groups = []
    for xy, drill in sorted(r.drills.items()):
        if any(math.dist(xy, (p['x'], p['y'])) < .002 for p in r.pins.values()):
            continue
        nonplated = xy in r.nonplated_drills
        if drill <= .5 and not nonplated:
            continue  # Remaining small plated holes become native vias.
        ref = 'HREC' + str(len(groups)+1)
        flash = bb.flash_near(r, 'F.Cu', *xy) or bb.flash_near(r, 'B.Cu', *xy)
        assert flash is not None or nonplated, (r.name, xy, drill)
        if flash:
            x0, y0, x1, y1 = recover.object_shape(flash).bounds
            width, height = x1-x0, y1-y0
        else:
            width, height = r.drill_slots.get(xy, (drill, drill))
        r.components[ref] = {'COMPONENT_NAME': ref, 'X_COORDINATE': xy[0]/.0254,
            'Y_COORDINATE': xy[1]/.0254, 'ANGLE': 0, 'LAYER': 'T', 'inferred': True,
            'value': ('Non-plated' if nonplated else 'Unreferenced plated') + ' hole'}
        raw = '' if nonplated else r.net_at('F.Cu', *xy) or r.net_at('B.Cu', *xy)
        number = '' if nonplated else '1'
        pin = {'ref': ref, 'number': number, 'x': xy[0], 'y': xy[1],
            'global_width': width, 'global_height': height, 'drill': drill,
            'nonplated': nonplated, 'PAD_SHAPE': 'C', 'NET_NAME': raw,
            'PIN_NAME': ref+'_1', 'PIN_TYPE': 'DIP', 'side': 'F.Cu'}
        if xy in r.drill_slots:pin['drill_size'] = r.drill_slots[xy]
        r.pins[(ref, number)] = pin
        groups.append(ref)
    r.inferred_refs = groups
    # Preserve supplied net names. Single unnamed islands have no established signal.
    counts = Counter(p['NET_NAME'] for p in r.pins.values())
    r.net_aliases = {}
    for p in r.pins.values():
        raw = p['NET_NAME']
        p['net'] = '' if not raw or p.get('nonplated') or (counts[raw] == 1 and raw.startswith('RECOVERED_')) else raw
        r.net_aliases[raw] = p['net']


def bom_values(board):
    """Read original XLSX values with the standard library; retain part numbers."""
    values = {}
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    for file in (board/'docs').glob('*.xlsx'):
        with zipfile.ZipFile(file) as archive:
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(e.itertext()) for e in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
            for name in archive.namelist():
                if not name.startswith('xl/worksheets/sheet') or not name.endswith('.xml'):continue
                rows = []
                for row in ET.fromstring(archive.read(name)).findall('.//m:row', ns):
                    cells = {}
                    for cell in row:
                        column = re.sub('[0-9]', '', cell.get('r', ''))
                        v = cell.find('m:v', ns)
                        value = v.text if v is not None else ''.join(cell.itertext())
                        cells[column] = strings[int(value)] if cell.get('t') == 's' else value
                    rows.append(cells)
                if not rows:continue
                columns = {value: key for key, value in rows[0].items()}
                if 'Designator' not in columns:continue
                for row in rows[1:]:
                    refs = row.get(columns['Designator'], '')
                    value = row.get(columns.get('Comment', ''), '') or row.get(columns.get('Value', ''), '')
                    for ref in refs.split(','):
                        if ref.strip():values[ref.strip()] = value or 'Unspecified in BOM'
    return values


def library_tables(folder):
    """Keep all three short-busbar projects visible in their shared local tables."""
    for table, suffix, kind in [('sym-lib-table', '.kicad_sym', 'sym'), ('fp-lib-table', '.pretty', 'fp')]:
        entries = []
        for lib in sorted((folder/'libraries').glob('*'+suffix)):
            entries.append(f' (lib (name "{lib.stem}") (type "KiCad") (uri "${{KIPRJMOD}}/libraries/{lib.name}") (options "") (descr "MicroSMT CAM-derived reference"))')
        (folder/table).write_text('('+kind+'_lib_table (version 7)\n'+'\n'.join(entries)+'\n)\n')


def schematic(model, folder, library):
    """Lay out connected reference symbols on readable A3 hierarchical sheets.

Pin numbers and nets come from CAM. Generic passive pin types deliberately avoid
inventing device electrical functions that the manufacturing files cannot prove.
The supplied schematic PDF/PNG remains the functional reference.
"""
    name = model['name']
    bs.LIB = library
    bs.LIBS = {}
    pages = []
    assignment = {}

    def page():
        key = name+'_sheet_'+str(len(pages)+1).zfill(2)
        sheet = bs.Sheet({'name': key})
        sheet.sheet_uuid = recover.ident(name+'/sheet/'+key)
        sheet.text(name.replace('_', ' ')+' / components '+str(len(pages)+1), 20.32, 17.78, 1.8)
        sheet.text('MicroSMT CAM-derived reference. Pad numbers/nets preserved; generic pin electrical types.\nUse the supplied schematic for functional interpretation. Not a fabrication release.', 20.32, 25.4, 1.0)
        pages.append(sheet)
        return sheet

    sheet = page(); x = 53.34; y = 53.34; row_height = 0
    for c in model['components']:
        pins = sorted(c['pins'], key=lambda p: (not p['number'].isdigit(), int(p['number']) if p['number'].isdigit() else p['number']))
        rows = math.ceil(len(pins)/2)
        height = max(25.4, rows*2.54+17.78)
        if x > 350:
            x = 53.34; y += row_height; row_height = 0
        if y + height/2 > 269:
            sheet = page(); x = 53.34; y = 53.34; row_height = 0
        key = name+'_'+c['ref']
        mechanical = len(pins)==1 and pins[0]['number']==''
        if mechanical:
            definition=bs.expr(f'(symbol {bs.q(key)} (exclude_from_sim no) (in_bom no) (on_board yes) (property "Reference" "HREC" (at 0 5.08 0) (effects (font (size 1.27 1.27)))) (property "Value" "Non-plated hole" (at 0 -5.08 0) (effects (font (size 1.27 1.27)))) (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes))) (symbol {bs.q(key+"_0_1")} (circle (center 0 0) (radius 2.54) (stroke (width .254) (type default)) (fill (type none)))))')
        else:
            definition = bs.box(key, re.sub('[0-9]+$', '', c['ref']),
                [(p['number'], 'PAD '+p['number'], 'passive', 'left' if i < rows else 'right', i if i < rows else i-rows) for i,p in enumerate(pins)], 15.24)
        bs.LIBS[key] = definition
        start = len(sheet.items)
        cy = y + max(0, height/2-12.7)
        schematic_component=deepcopy(c)
        if mechanical:schematic_component['pins']=[]
        sheet.place(schematic_component, key, x, cy)
        for item in sheet.items[start:]:
            if bs.tag(item) == 'label':
                item[0] = bs.S('global_label');item.insert(2, bs.expr('(shape bidirectional)'))
            elif bs.tag(item) == 'symbol':
                if c['inferred']:bs.child(item,'in_bom')[1]=bs.S('no')
                instances = bs.child(item, 'instances');project = bs.child(instances, 'project');project[1] = name
                bs.child(project, 'path')[1] = '/'+recover.ident(name+'/schematic')+'/'+sheet.sheet_uuid
        assignment[c['ref']] = sheet.sheet_uuid
        x += 119.38; row_height = max(row_height, height)
    for sheet in pages:
        definitions = []
        for key in sorted(sheet.used):
            definition = deepcopy(bs.LIBS[key]);definition[1] = library+':'+key;definitions.append(definition)
        doc = bs.expr(f'(kicad_sch (version 20250114) (generator "eeschema") (uuid {sheet.root}) (paper "A3") (title_block (title {bs.q(name+" / recovered reference")}) (rev "recovery-1")) (lib_symbols))')
        bs.child(doc, 'lib_symbols').extend(definitions);doc.extend(sheet.items)
        (folder/(sheet.name+'.kicad_sch')).write_text(bs.pretty(doc)+'\n')
    root_uuid = recover.ident(name+'/schematic')
    root = bs.expr(f'(kicad_sch (version 20250114) (generator "eeschema") (uuid {root_uuid}) (paper "A3") (title_block (title {bs.q(name+" / MicroSMT recovered reference")}) (rev "recovery-1")) (lib_symbols))')
    overview = bs.Sheet({'name': name})
    overview.text('MicroSMT / '+name.replace('_', ' '), 20.32, 20.32, 2.0)
    overview.text('Editable reference reconstructed from original Gerbers, drills and flying-probe nets.\nOpen the sheets below for connected components. Original source files remain in the parent folder.\nValues come from the supplied BOM where available. Generic PAD labels are not device pin-function claims.\nRecovered copper contours preserve plotted geometry, not original pour design intent.\nRead ../README.md and the recovery/validation reports in ../docs/ before edits or fabrication.',20.32,33.02,1.1)
    root.extend(overview.items)
    for i,sheet in enumerate(pages):
        px=20.32+(i%3)*124.46;py=73.66+(i//3)*35.56
        root.append(bs.expr(f'(sheet (at {px} {py}) (size 111.76 22.86) (stroke (width 0) (type default)) (fill (color 0 0 0 0)) (uuid {sheet.sheet_uuid}) (property "Sheetname" {bs.q("Components "+str(i+1))} (at {px} {py-.762} 0) (effects (font (size 1.27 1.27)) (justify left bottom))) (property "Sheetfile" {bs.q(sheet.name+".kicad_sch")} (at {px} {py+23.622} 0) (effects (font (size 1.27 1.27)) (justify left top))) (instances (project {bs.q(name)} (path {bs.q("/"+root_uuid)} (page {bs.q(str(i+2))})))))'))
    root.append(bs.expr('(sheet_instances (path "/" (page "1")))'))
    (folder/(name+'.kicad_sch')).write_text(bs.pretty(root)+'\n')
    lib = bs.expr('(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor"))')
    lib.extend(bs.LIBS.values());(folder/'libraries'/(library+'.kicad_sym')).write_text(bs.pretty(lib)+'\n')
    board = k.LoadBoard(str(folder/(name+'.kicad_pcb')))
    by_ref={c['ref']:c for c in model['components']}
    for fp in board.GetFootprints():
        fp.SetPath(k.KIID_PATH('/'+root_uuid+'/'+assignment[fp.GetReference()]+'/'+recover.ident(name+'/symbol/'+fp.GetReference())))
        if by_ref[fp.GetReference()]['inferred']:fp.SetAttributes(fp.GetAttributes() | k.FP_EXCLUDE_FROM_BOM)
    k.SaveBoard(str(folder/(name+'.kicad_pcb')), board)
    return len(pages)+1


def build(name):
    board, folder, docs, prefix = paths(name)
    recover.PROJECTS[name] = folder;recover.REPORTS[name] = docs
    target = folder/(name+'.kicad_pcb')
    assert not target.exists(), 'Refusing to overwrite an existing project: '+str(target)
    r = load(name)
    assert not r.conflicts, (name, r.conflicts)
    values = bom_values(board)
    for ref,c in r.components.items():
        c['value'] = values.get(ref, 'Unspecified in source BOM')
    library = 'MicroSMT_'+name
    bb.LIBRARY = library
    model = bb.make_board(r, values, infer=infer_holes)
    model['schematic_pages'] = schematic(model, folder, library)
    used={c['footprint'].split(':')[1] for c in model['components']}
    for file in (folder/'libraries'/(library+'.pretty')).glob('*.kicad_mod'):
        if file.stem not in used:file.unlink()
    model['nonplated_holes'] = len(r.nonplated_drills)
    model['probe_normalization'] = {'source_rows':len(json.loads(zipfile.ZipFile(recover.ROOT/SOURCES[name]).read('FlyingProbeTesting.json'))['pins']['rows']), 'unique_source_pads':len(r.pins)-len(r.inferred_refs)}
    model['interpretation'] = ['CAM pad numbers and net names preserved; generic passive symbol pins.', 'HREC references identify unreferenced source holes; their mechanical purpose is unverified.', 'Copper contours preserve final plots, not editable original pour intent.']
    (docs/(prefix+'recovery.json')).write_text(json.dumps(model,indent=2)+'\n')
    license_source = recover.ROOT/'Bing-feeder/V3-feeder/PCB_feeder/KiCad/libraries/LICENSE.KiCad-symbols.txt'
    shutil.copy2(license_source, folder/'libraries'/license_source.name)
    library_tables(folder)
    print(name, 'built', len(model['components']), 'components;', model['schematic_pages'], 'schematic pages',flush=True)


def geometry_self_check():
    """Catch the rotated-macro regression before it can create false shorts."""
    from gerbonara import graphic_primitives as gp
    shape = recover.primitive_shape(gp.Rectangle(0, 0, 2, 1, math.pi/4))
    assert abs(shape.area-2) < 1e-9
    assert not shape.covers(Point(1, 1))
    assert shape.covers(Point(.5, .5))
    triangle = recover.primitive_shape(gp.ArcPoly([(0,0),(1,0),(0,1)]))
    assert abs(triangle.area-.5) < 1e-9


def validate(name):
    """Check native parity, physical pads/drills and independently replotted copper."""
    from validate import run, composite
    from gerbonara import GerberFile
    from shapely.affinity import translate
    board_dir, folder, docs, prefix = paths(name)
    model = json.loads((docs/(prefix+'recovery.json')).read_text())
    r = load(name)
    infer_holes(r)
    out = recover.ROOT/'build/kicad'/name
    out.mkdir(parents=True, exist_ok=True)
    pcb = folder/(name+'.kicad_pcb');sch = folder/(name+'.kicad_sch')
    run('sch','export','netlist','--format','kicadxml','-o',out/'netlist.xml',sch)
    schematic_nets = {}
    netlist=ET.parse(out/'netlist.xml').getroot()
    excluded={c.get('ref') for c in netlist.findall('components/comp') if c.find("property[@name='exclude_from_bom']") is not None}
    for net in netlist.findall('nets/net'):
        for node in net.findall('node'):
            schematic_nets[(node.get('ref'),node.get('pin'))] = net.get('name')
    board = k.LoadBoard(str(pcb))
    # Global labels have no leading '/'. Match KiCad's generated NC names too.
    for net in board.GetNetInfo().NetsByNetcode().values():
        if net.GetNetname().startswith('/'):net.SetNetname(net.GetNetname().lstrip('/'))
    expected = {(c['ref'],p['number']):p for c in model['components'] for p in c['pins']}
    isolated = {}
    for fp in board.GetFootprints():
        fp.Reference().SetMirrored(fp.IsFlipped())
        if fp.GetReference() in excluded:fp.SetAttributes(fp.GetAttributes() | k.FP_EXCLUDE_FROM_BOM)
        for pad in fp.Pads():
            pin = expected[(fp.GetReference(),pad.GetNumber())]
            if pin['net']:continue
            label = schematic_nets.get((fp.GetReference(),pad.GetNumber()),'')
            if not label:continue
            assert label.startswith('unconnected-'),label
            item = board.FindNet(label)
            if not item:
                item=k.NETINFO_ITEM(board,label);board.Add(item)
            pad.SetNet(item)
            if pin['source_net']:isolated[pin['source_net']] = item
    for zone in board.Zones():
        if zone.GetNetCode():continue
        layer,index=zone.GetZoneName().split(': ')[1].split('/')
        raw=r.net_by_group[r.connections.find((layer,int(index)))]
        if raw in isolated:zone.SetNet(isolated[raw])
    for track in board.GetTracks():
        if track.GetNetCode():continue
        position=track.GetPosition()
        x=k.ToMM(position.x)+r.min_x-20;y=r.max_y+20-k.ToMM(position.y)
        raw=r.net_at('F.Cu' if isinstance(track,k.PCB_VIA) else board.GetLayerName(track.GetLayer()),x,y)
        if raw in isolated:track.SetNet(isolated[raw])
    k.SaveBoard(str(pcb),board)
    run('sch','erc','--format','json','-o',out/'erc.json',sch)
    run('pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','-o',str(out/'gerbers')+'/',pcb)
    run('pcb','drc','--schematic-parity','--format','json','-o',out/'drc.json',pcb)
    board=k.LoadBoard(str(pcb))
    actual={(fp.GetReference(),pad.GetNumber()):pad for fp in board.GetFootprints() for pad in fp.Pads()}
    def normal(net):return '' if net.startswith('unconnected-') else net.lstrip('/')
    errors=[]
    for key,pin in expected.items():
        if normal(schematic_nets.get(key,''))!=pin['net']:errors.append(['schematic',key])
        if normal(actual[key].GetNetname())!=pin['net']:errors.append(['pcb',key])
    pad_error=max(math.dist(bb.point_tuple(actual[key].GetPosition()),pin['position_mm']) for key,pin in expected.items())
    holes=[(*bb.point_tuple(p.GetPosition()),k.ToMM(p.GetDrillSize().x)) for p in actual.values() if p.GetDrillSize().x]
    holes.extend((*bb.point_tuple(t.GetPosition()),k.ToMM(t.GetDrillValue())) for t in board.GetTracks() if isinstance(t,k.PCB_VIA))
    assert len(holes)==len(r.drills),(name,'drill count',len(holes),len(r.drills))
    drill_error=max(min(math.dist((x,y),r.xy(*xy))+abs(d-diameter) for x,y,d in holes) for xy,diameter in r.drills.items())
    copper={};mask_paste={}
    for layer,suffix in [('F.Cu','F_Cu.gtl'),('B.Cu','B_Cu.gbl'),('F.Mask','F_Mask.gts'),('B.Mask','B_Mask.gbs'),('F.Paste','F_Paste.gtp'),('B.Paste','B_Paste.gbp')]:
        if layer not in r.layers:continue
        native=composite(GerberFile.open(out/'gerbers'/(name+'-'+suffix)))
        native=translate(native,xoff=r.min_x-20,yoff=r.max_y+20)
        source=r.copper[layer] if layer in r.copper else composite(r.layers[layer])
        record={'source_area_mm2':source.area,'exported_area_mm2':native.area,'symmetric_difference_mm2':source.symmetric_difference(native).area}
        if layer in r.copper:
            record['extra_beyond_2um_mm2']=native.difference(source.buffer(.002)).area
            record['missing_beyond_2um_mm2']=source.difference(native.buffer(.002)).area
            record['within_2um_tolerance']=record['extra_beyond_2um_mm2']<.00001 and record['missing_beyond_2um_mm2']<.00001
            copper[layer]=record
        else:mask_paste[layer]=record
    erc=json.loads((out/'erc.json').read_text());drc=json.loads((out/'drc.json').read_text())
    ercs=[v for sheet in erc['sheets'] for v in sheet['violations']]
    report={'name':name,'kicad_version':k.Version(),'source_archive_sha256':hashlib.sha256((recover.ROOT/SOURCES[name]).read_bytes()).hexdigest(),
        'matched_pads':len(expected),'schematic_board_model_net_mismatches':errors,'maximum_pad_position_error_mm':pad_error,
        'matched_drills':len(holes),'nonplated_drills':len(r.nonplated_drills),'maximum_drill_error_mm':drill_error,
        'copper_comparison':copper,'erc_counts':dict(Counter(v['type'] for v in ercs)),
        'drc_counts':dict(Counter(v['type'] for v in drc['violations'])),
        'unconnected_items':len(drc['unconnected_items']),'schematic_parity_counts':dict(Counter(v['type'] for v in drc['schematic_parity'])),
        'notes':['Original-layout DRC and single-pin-label ERC findings are retained, not excluded.',
                 'Generic passive symbols verify numbered-pad connectivity, not device electrical behavior.',
                 'Copper contours are recovered plot geometry, not original pour design intent.']}
    (docs/(prefix+'validation.json')).write_text(json.dumps(report,indent=2)+'\n')
    (docs/(prefix+'mask-paste-comparison.json')).write_text(json.dumps(mask_paste,indent=2)+'\n')
    print(name,json.dumps(report),flush=True)
    assert not errors,(name,errors)
    assert pad_error<.00001 and drill_error<.002,(pad_error,drill_error)
    assert all(v['within_2um_tolerance'] for v in copper.values()),(name,copper)
    assert not drc['schematic_parity'],(name,drc['schematic_parity'][:3])
    assert not drc['unconnected_items'],(name,'unrouted',drc['unconnected_items'][:3])
    assert not any(v['type'].startswith('lib_') for v in ercs+drc['violations']),(name,'library mismatch')


def render(name):
    """Create JPG review images from native exports; preserve existing Gerber photos."""
    import io
    import cairosvg
    from PIL import Image, ImageDraw
    from validate import run
    board, folder, docs, prefix = paths(name)
    out = recover.ROOT/'build/kicad'/name/'previews'
    out.mkdir(parents=True,exist_ok=True)
    photos=board/'photos';photos.mkdir(exist_ok=True)
    run('sch','export','svg','-o',str(out/'schematics')+'/',folder/(name+'.kicad_sch'))
    for side,layers in [('top','F.Cu,F.SilkS,Edge.Cuts'),('bottom','B.Cu,B.SilkS,Edge.Cuts')]:
        run('pcb','export','svg','--layers',layers,'--mode-single','--fit-page-to-board','--exclude-drawing-sheet','-o',out/(side+'.svg'),folder/(name+'.kicad_pcb'))
    def jpg(svg,destination,width):
        png=cairosvg.svg2png(url=str(svg),output_width=width,background_color='white')
        Image.open(io.BytesIO(png)).convert('RGB').save(destination,quality=94,optimize=True,progressive=True)
    for side in ['top','bottom']:jpg(out/(side+'.svg'),photos/('kicad-'+name+'-'+side+'.jpg'),3200)
    sheets=[]
    for svg in sorted((out/'schematics').glob('*.svg')):
        if svg.stem==name:
            jpg(svg,photos/('kicad-'+name+'-overview.jpg'),2600)
        else:
            destination=photos/('kicad-'+name+'-sheet-'+str(len(sheets)+1).zfill(2)+'.jpg')
            jpg(svg,destination,3200);sheets.append(destination)
    assert sheets,(name,'no component sheets exported')
    if len(sheets)==1:
        shutil.copy2(sheets[0],photos/('kicad-'+name+'-schematic.jpg'))
    else:
        cell_w,cell_h=1200,900
        columns=min(2,len(sheets))
        contact=Image.new('RGB',(cell_w*columns,cell_h*math.ceil(len(sheets)/columns)),(235,239,243))
        draw=ImageDraw.Draw(contact)
        for index,path in enumerate(sheets):
            im=Image.open(path);im.thumbnail((cell_w-24,cell_h-55))
            x=(index%columns)*cell_w+12;y=(index//columns)*cell_h+42
            contact.paste(im,(x,y));draw.text((x,y-25),'Components '+str(index+1),fill='black')
        contact.save(photos/('kicad-'+name+'-schematic.jpg'),quality=94,optimize=True,progressive=True)
    print(name,'JPG previews rendered:',len(sheets),'component sheets plus PCB top/bottom.',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('names', nargs='*', metavar='BOARD', help='Only these boards; default all eight. Names: '+', '.join(SOURCES))
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--inspect', action='store_true', help='Parse source geometry without generating CAD.')
    modes.add_argument('--validate', action='store_true', help='Run native parity, hole and CAM copper comparisons on generated projects.')
    modes.add_argument('--render', action='store_true', help='Render native PCB and schematic JPG previews.')
    modes.add_argument('--self-check', action='store_true', help='Check rotated-rectangle geometry without opening source files.')
    args = parser.parse_args()
    geometry_self_check()
    if args.self_check:
        print('Rotated-rectangle geometry check passed.')
    else:
        names=args.names or list(SOURCES)
        if any(name not in SOURCES for name in names):parser.error('Unknown board name; see --help.')
        for name in names:
            if args.inspect:
                r=load(name);print(name, json.dumps({'size_mm':[r.width,r.height],'components':len(r.components),'pads':len(r.pins),'drills':len(r.drills),'nonplated':len(r.nonplated_drills),'conflicts':r.conflicts}),flush=True)
            elif args.validate:validate(name)
            elif args.render:render(name)
            else:build(name)
