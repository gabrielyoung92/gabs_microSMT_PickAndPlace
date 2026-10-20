"""Render the native KiCad SVG exports for convenient review."""
import site
import sys
# Prefer the active virtualenv's matching cffi package and extension.
for folder in reversed(site.getsitepackages()):
    if folder in sys.path:sys.path.remove(folder)
    sys.path.insert(0,folder)
import cairosvg
from recover import ROOT, OUTPUT, SOURCES

folder=OUTPUT/'previews';folder.mkdir(exist_ok=True)
for name in SOURCES:
    source=ROOT/'build'/'hardware'/name
    for original,label,width in [(name+'.svg','schematic',2600),('pcb-top.svg','top',2200),('pcb-bottom.svg','bottom',2200)]:
        cairosvg.svg2png(url=str(source/original),write_to=str(folder/(name+'-'+label+'.png')),output_width=width)
        print(name,label,flush=True)
