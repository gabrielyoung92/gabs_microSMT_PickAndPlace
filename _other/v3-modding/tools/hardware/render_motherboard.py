#!/usr/bin/env python3
"""Render motherboard native exports and a schematic contact sheet for review."""
import site,sys
for folder in reversed(site.getsitepackages()):
 if folder in sys.path:sys.path.remove(folder)
 sys.path.insert(0,folder)
from pathlib import Path
import cairosvg
from PIL import Image,ImageDraw
from build_motherboard import NAME,BUILD,FOLDER
from recover import OUTPUT
OUT=OUTPUT/'previews'/'motherboard'
OUT.mkdir(parents=True,exist_ok=True)
source=sorted(BUILD.glob('motherboard*.svg'))
images=[]
for i,path in enumerate(source):
 key='overview' if path.name=='motherboard.svg' else path.stem.split(' - ')[0].removeprefix('motherboard-')
 output=OUT/('schematic-'+key+'.png')
 cairosvg.svg2png(url=str(path),write_to=str(output),output_width=2600)
 images.append((path.stem,output))
 print('rendered',output.name,flush=True)
for label in ['top','bottom']:
 cairosvg.svg2png(url=str(BUILD/('pcb-'+label+'.svg')),write_to=str(OUT/('pcb-'+label+'.png')),output_width=2400)
thumb_w,thumb_h=840,630
sheet=Image.new('RGB',(thumb_w*3,thumb_h*((len(images)+2)//3)),(235,239,243))
draw=ImageDraw.Draw(sheet)
for i,(title,path) in enumerate(images):
 im=Image.open(path).convert('RGB');im.thumbnail((thumb_w-20,thumb_h-50))
 x=(i%3)*thumb_w+10;y=(i//3)*thumb_h+35
 sheet.paste(im,(x,y));draw.text((x,y-24),title.replace('motherboard-','')[:105],fill='black')
sheet.save(OUT/'schematic-contact-sheet.png')
print('review sheet',OUT/'schematic-contact-sheet.png',flush=True)
