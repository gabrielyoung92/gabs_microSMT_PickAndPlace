#!/usr/bin/env python3
"""Recover connected board objects from the preserved EasyEDA CAM exports.

Dependencies are listed alongside this script. KiCad's pcbnew Python bindings
are additionally required for native board validation and serialization.
"""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import uuid
from source_files import read_source_files

from gerbonara import GerberFile, ExcellonFile
from gerbonara import graphic_primitives as gp
from gerbonara.utils import MM, approximate_arc
from shapely.geometry import Point, Polygon, LineString
from shapely import union_all, make_valid
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
SOURCES = {
    'feeder_v2': 'Bing-feeder/V3-feeder/PCB_feeder/V3_feeder_gerber_2025-02-06.zip',
    'busbar_n1_n8': 'Bing-feeder/V3-Feeder Controller/PCB_busbar_N1-N8/V3_busbar_N1-N8_gerber.zip',
    'busbar_n9_n16': 'Bing-feeder/V3-Feeder Controller/PCB_busbar_N9-N16/V3_busbar_N9-N16_gerber.zip',
    'busbar_n17_n24': 'Bing-feeder/V3-Feeder Controller/PCB_busbar_N17-N24/V3_busbar_N17-N24_gerber.zip',
}
# Editable projects live beside their source Gerbers; build output stays here.
PROJECTS = {name: (ROOT / source).resolve().parent / 'KiCad'
            for name, source in SOURCES.items()}
PROJECTS['motherboard'] = ROOT / 'Microsmt-PNPv3/PCB_motherboard/KiCad'
# Recovery evidence belongs with each board, outside the editable project.
REPORTS = {name: folder.parent / 'docs' for name, folder in PROJECTS.items()}


LAYER_FILES = {
    'F.Cu': 'Gerber_TopLayer.GTL', 'B.Cu': 'Gerber_BottomLayer.GBL',
    'In1.Cu': 'Gerber_InnerLayer1.G1', 'In2.Cu': 'Gerber_InnerLayer2.G2',
    'F.SilkS': 'Gerber_TopSilkscreenLayer.GTO',
    'B.SilkS': 'Gerber_BottomSilkscreenLayer.GBO',
    'F.Mask': 'Gerber_TopSolderMaskLayer.GTS',
    'B.Mask': 'Gerber_BottomSolderMaskLayer.GBS',
    'F.Paste': 'Gerber_TopPasteMaskLayer.GTP',
    'B.Paste': 'Gerber_BottomPasteMaskLayer.GBP',
    'Edge.Cuts': 'Gerber_BoardOutlineLayer.GKO',
}
ARC_ERROR_MM = 0.001
MATCH_TOLERANCE_MM = 0.002


def ident(text):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'microsmt-recovery/' + text))


def polygon_parts(geometry):
    if geometry.geom_type == 'Polygon':
        return [geometry]
    if hasattr(geometry, 'geoms'):
        return [part for item in geometry.geoms for part in polygon_parts(item)]
    return []


def primitive_shape(primitive):
    if isinstance(primitive, gp.Circle):
        return Point(primitive.x, primitive.y).buffer(primitive.r, quad_segs=64)
    if isinstance(primitive, gp.Rectangle):
        # Gerbonara 1.6.3's Rectangle.to_arc_poly() returns a bounding rectangle
        # for rotated macros. That falsely shorts the feeder's crystal pads.
        cosine, sine = math.cos(primitive.rotation), math.sin(primitive.rotation)
        return Polygon([(primitive.x + x*cosine - y*sine,
                         primitive.y + x*sine + y*cosine)
                        for x,y in [(-primitive.w/2,-primitive.h/2),
                                    (-primitive.w/2,primitive.h/2),
                                    (primitive.w/2,primitive.h/2),
                                    (primitive.w/2,-primitive.h/2)]])
    if isinstance(primitive, gp.Line):
        return LineString([(primitive.x1, primitive.y1), (primitive.x2, primitive.y2)]).buffer(
            primitive.width / 2, quad_segs=32)
    if isinstance(primitive, gp.Arc):
        points = list(approximate_arc(primitive.cx, primitive.cy, primitive.x1,
            primitive.y1, primitive.x2, primitive.y2, primitive.clockwise,
            max_error=ARC_ERROR_MM))
        return LineString(points).buffer(primitive.width / 2, quad_segs=32)
    if not isinstance(primitive, gp.ArcPoly):
        primitive = primitive.to_arc_poly()
    # Flatten the public segment iterator directly. This also avoids the broken
    # ArcPoly.approximate_arcs implementation in Gerbonara's Python 3.11 release.
    points = []
    for (x1,y1),(x2,y2),(clockwise,(cx,cy)) in primitive.segments:
        if clockwise is None:
            points.append((x1,y1))
        else:
            points.extend(list(approximate_arc(cx,cy,x1,y1,x2,y2,clockwise,
                max_error=ARC_ERROR_MM))[:-1])
    if len(points) < 3:
        return Polygon()
    return make_valid(Polygon(points))


def object_shape(obj):
    result = Polygon()
    dark = []
    for p in obj.to_primitives(MM):
        geom = primitive_shape(p)
        if p.polarity_dark == obj.polarity_dark:
            dark.append(geom)
        else:
            result = union_all([result, *dark]).difference(geom)
            dark = []
    return union_all([result, *dark])


class DisjointSet:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        if item not in self.parent:
            self.parent[item] = item
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def join(self, a, b):
        self.parent[self.find(a)] = self.find(b)


class Recovery:
    def __init__(self, name, source=None, probe_transform=None, both_sides=False):
        self.name = name
        self.both_sides = both_sides
        self.source = source or SOURCES[name]
        members = read_source_files(ROOT / self.source)
        self.probe = json.loads(members['FlyingProbeTesting.json'])
        if probe_transform:
            self.probe = probe_transform(self.probe)
        self.layers = {layer: GerberFile.from_string(members[filename].decode())
                      for layer, filename in LAYER_FILES.items() if filename in members}
        drills = {}
        self.drill_slots = {}
        self.nonplated_drills = set()
        for filename in members:
            if filename.endswith('.DRL'):
                file = ExcellonFile.from_string(members[filename].decode())
                for obj in file.objects:
                    if type(obj).__name__ == 'Flash':
                        x,y=obj.x,obj.y
                    else:
                        assert type(obj).__name__ == 'Line', 'Curved drill slots require explicit handling'
                        x,y=(obj.x1+obj.x2)/2,(obj.y1+obj.y2)/2
                        assert abs(obj.x1-obj.x2)<1e-6 or abs(obj.y1-obj.y2)<1e-6
                        self.drill_slots[(round(x,5),round(y,5))]=(abs(obj.x2-obj.x1)+obj.aperture.diameter,abs(obj.y2-obj.y1)+obj.aperture.diameter)
                    key = (round(x, 5), round(y, 5))
                    if 'NPTH' in filename:
                        self.nonplated_drills.add(key)
                    drill = obj.aperture.diameter
                    if key in drills:
                        assert abs(drills[key] - drill) < 0.0001
                    drills[key] = drill
        self.drills = drills
        self.member_hashes = {n: hashlib.sha256(members[n]).hexdigest()
                              for n in members if not n.endswith('/')}
        assert self.probe['lengthUnit'] == 'mil'
        self.components = {row[1]: dict(zip(self.probe['components']['fields'], row))
                           for row in self.probe['components']['rows']}
        self.pins = {}
        for row in self.probe['pins']['rows']:
            p = dict(zip(self.probe['pins']['fields'], row))
            if p['LAYER'] != 'T' and not both_sides:
                continue  # PTH appears on both sides, but is a single physical pad.
            ref, number = p['PIN_NAME'].rsplit('_', 1)
            p.update(ref=ref, number=number, x=p['PIN_X']*0.0254, y=p['PIN_Y']*0.0254,
                     width=p['PAD_SIZEX']*0.0254, height=p['PAD_SIZEY']*0.0254,
                     drill=p['HOLE_SIZE']*0.0254)
            p['side'] = 'B.Cu' if p['LAYER'] == 'B' else 'F.Cu'
            self.pins[(ref, number)] = p
        # Gerber centers/dimensions have greater precision than the 0.01 mil test data.
        self.flashes = {layer: [o for o in file.objects if type(o).__name__ == 'Flash']
                        for layer, file in self.layers.items()}
        self.max_probe_snap = 0.0
        self.used_flashes = set()
        for key, p in self.pins.items():
            side = p['side']
            candidates = [(math.hypot(f.x-p['x'], f.y-p['y']), i, f)
                          for i, f in enumerate(self.flashes[side])]
            distance, index, flash = min(candidates, key=lambda t:t[0])
            if p['PAD_SHAPE']=='P' and distance>MATCH_TOLERANCE_MM:
                point=Point(p['x'],p['y'])
                regions=[(object_shape(o),o) for o in self.layers[side].objects if type(o).__name__=='Region' and o.polarity_dark]
                matches=[(g,o) for g,o in regions if g.distance(point)<MATCH_TOLERANCE_MM
                         and abs((g.bounds[2]-g.bounds[0])-p['width'])<.01
                         and abs((g.bounds[3]-g.bounds[1])-p['height'])<.01]
                assert len(matches)==1,('custom pad region',key,len(matches))
                geometry,flash=matches[0]
                x0,y0,x1,y1=geometry.bounds
                p['global_width'],p['global_height']=x1-x0,y1-y0
                p['flash']=flash
                continue
            assert distance <= MATCH_TOLERANCE_MM, (key, distance)
            self.max_probe_snap = max(self.max_probe_snap, distance)
            p['x'], p['y'] = flash.x, flash.y
            primitive = list(flash.to_primitives(MM))[0]
            x0, y0, x1, y1 = object_shape(flash).bounds
            p['global_width'], p['global_height'] = x1-x0, y1-y0
            if isinstance(primitive, gp.Rectangle) and both_sides:
                p['bounding_width'], p['bounding_height'] = x1-x0, y1-y0
                p['global_width'], p['global_height'] = primitive.w, primitive.h
                p['rotation_deg'] = math.degrees(primitive.rotation)
            p['flash'] = flash
            if p['drill']:
                drill_key = min(self.drills, key=lambda k: math.hypot(k[0]-p['x'], k[1]-p['y']))
                assert math.dist(drill_key, (p['x'],p['y'])) < MATCH_TOLERANCE_MM
                p['drill'] = self.drills[drill_key]
                if drill_key in self.drill_slots:p['drill_size']=self.drill_slots[drill_key]
            self.used_flashes.add((side, index))
        # Original Gerber coordinates -> positive KiCad page coordinates, preserving handedness.
        vertices = [(o.x1,o.y1) for o in self.layers['Edge.Cuts'].objects]
        self.min_x = min(x for x,y in vertices)
        self.max_y = max(y for x,y in vertices)
        self.width = max(x for x,y in vertices) - self.min_x
        self.height = self.max_y - min(y for x,y in vertices)
        self.object_geometries = {}
        self.copper = {}
        self.islands = {}
        self.trees = {}
        self.copper_layers = [layer for layer in ('F.Cu','In1.Cu','In2.Cu','B.Cu') if layer in self.layers]
        for layer in self.copper_layers:
            objects = self.layers[layer].objects
            self.object_geometries[layer] = [object_shape(o) for o in objects]
            copper, pending = Polygon(), []
            for obj, geometry in zip(objects,self.object_geometries[layer]):
                if obj.polarity_dark:
                    pending.append(geometry)
                else:
                    copper = union_all([copper,*pending]).difference(geometry)
                    pending = []
            self.copper[layer] = union_all([copper,*pending])
            self.islands[layer] = polygon_parts(self.copper[layer])
            self.trees[layer] = STRtree(self.islands[layer])
        self.connections = DisjointSet()
        layer_indices={layer:{id(obj):i for i,obj in enumerate(self.layers[layer].objects)} for layer in self.copper_layers}
        for p in self.pins.values():
            if p['PAD_SHAPE']=='P':p['pad_geometry']=self.object_geometries[p['side']][layer_indices[p['side']][id(p['flash'])]]
        for x,y in self.drills:
            if (x,y) in self.nonplated_drills:
                continue  # Mechanical holes cannot connect opposite copper layers.
            links = [link for layer in self.copper_layers for link in self.touching(layer,x,y)]
            for a,b in zip(links,links[1:]): self.connections.join(a,b)
        self.net_seeds = defaultdict(set)
        self.seed_pins = defaultdict(list)
        for key,p in self.pins.items():
            net = p['NET_NAME']
            for part in self.touching(p['side'],p['x'],p['y']):
                group = self.connections.find(part)
                self.net_seeds[group].add(net)
                self.seed_pins[group].append(p['PIN_NAME'])
        self.net_by_group = {}
        self.conflicts = []
        for layer in self.copper_layers:
            for i,part in enumerate(self.islands[layer]):
                group = self.connections.find((layer,i))
                seeds = self.net_seeds[group]
                if len(seeds)>1:
                    conflict = {'nets':sorted(seeds),'pins':self.seed_pins[group]}
                    if conflict not in self.conflicts:self.conflicts.append(conflict)
                if group not in self.net_by_group:
                    self.net_by_group[group] = (next(iter(seeds)) if len(seeds)==1 else
                        ('CONFLICT_' if seeds else 'RECOVERED_')+str(len(self.net_by_group)+1))

    def touching(self, layer, x, y):
        point = Point(x,y)
        return [(layer,int(i)) for i in self.trees[layer].query(point.buffer(MATCH_TOLERANCE_MM))
                if self.islands[layer][i].distance(point)<MATCH_TOLERANCE_MM]

    def net_at(self, layer, x, y):
        groups = {self.connections.find(p) for p in self.touching(layer,x,y)}
        assert len(groups)<=1, (layer,x,y,groups)
        return self.net_by_group[next(iter(groups))] if groups else ''

    def xy(self,x,y):
        return round(x-self.min_x+20,6), round(self.max_y-y+20,6)

    def summary(self):
        return dict(name=self.name, source=self.source, dimensions_mm=[self.width,self.height],
            components=len(self.components), pads=len(self.pins), drills=len(self.drills),
            probe_snap_max_mm=self.max_probe_snap, nets=sorted(set(self.net_by_group.values())),
            conflicts=self.conflicts, archive_members_sha256=self.member_hashes)


if __name__ == '__main__':
    for name in SOURCES:
        recovery = Recovery(name)
        summary = recovery.summary()
        summary.pop('archive_members_sha256')
        print(json.dumps(summary,indent=2))
