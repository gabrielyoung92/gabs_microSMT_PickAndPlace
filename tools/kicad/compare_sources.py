"""Compare duplicate-labelled archives and quantify mask/paste recovery differences."""
import json
from shapely.affinity import translate
from gerbonara import GerberFile
from recover import Recovery, SOURCES, OUTPUT, object_shape, REPORTS
from validate import composite, BUILD


def compare():
    first=Recovery('busbar_n1_n8');second=Recovery('busbar_n9_n16');layers={}
    for layer in first.layers:
        a=first.layers[layer].objects;b=second.layers[layer].objects
        layers[layer]=len(a)==len(b) and all(object_shape(x).equals(object_shape(y)) for x,y in zip(a,b))
    report={'archives':['busbar_n1_n8','busbar_n9_n16'],
        'identical_ordered_geometry_by_layer':layers,
        'identical_drills':first.drills==second.drills,
        'identical_flying_probe_data':first.probe==second.probe}
    (OUTPUT/'busbar-archive-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    for name in SOURCES:
        r=Recovery(name);data={}
        for layer,suffix in [('F.Mask','F_Mask.gts'),('B.Mask','B_Mask.gbs'),('F.Paste','F_Paste.gtp')]:
            if layer not in r.layers:continue
            source=composite(r.layers[layer])
            exported=composite(GerberFile.open(BUILD/name/'gerbers'/(name+'-'+suffix)))
            exported=translate(exported,xoff=r.min_x-20,yoff=r.max_y+20)
            data[layer]={'source_area_mm2':source.area,'exported_area_mm2':exported.area,
                        'symmetric_difference_mm2':source.symmetric_difference(exported).area}
        (REPORTS[name]/'mask-paste-comparison.json').write_text(json.dumps(data,indent=2)+'\n')
        print(name,'mask/paste comparison recorded',flush=True)

if __name__=='__main__':compare()
