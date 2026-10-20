#!/usr/bin/env python3
"""Recover only the MicroSMT motherboard; never regenerate existing reference boards.

Run with the dependencies/environment documented in hardware/RECOVERY_NOTES.md.
Generated motherboard files are overwritten. Use a disposable checkout after edits.
"""
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import pickle
import re
import sys
import zipfile

import pcbnew as k
import recover
import build_boards as bb

NAME='motherboard'
SOURCE='../../Microsmt-PNPv3/PCB_motherboard/Gerber_PCB.zip'
LIB='MicroSMT_Motherboard'
FOLDER=recover.OUTPUT/NAME
BUILD=recover.ROOT/'build'/'hardware'/NAME
NORMALIZATION={}


def normalize_probe(d):
    d=deepcopy(d)
    source_component_rows=len(d['components']['rows'])
    fields=d['pins']['fields']
    rows=[dict(zip(fields,r)) for r in d['pins']['rows']]
    real=[r for r in rows if not r['PIN_NAME'].startswith('PAD')]
    aliases=[]
    for p in rows:
        if not p['PIN_NAME'].startswith('PAD'):continue
        matches=[q for q in real if abs(p['PIN_X']-q['PIN_X'])<.02 and abs(p['PIN_Y']-q['PIN_Y'])<.02
                 and p['NET_NAME']==q['NET_NAME'] and p['LAYER']==q['LAYER']]
        assert matches,('unmatched synthetic pad',p)
        aliases.append({'alias':p['PIN_NAME'],'physical_pin':matches[0]['PIN_NAME'],'layer':p['LAYER'],'net':p['NET_NAME']})
    unique={}
    for p in real:
        key=(p['PIN_NAME'],p['LAYER'])
        if key in unique:assert p==unique[key] or all(p[n]==unique[key][n] for n in fields if n!='PIN_NO'),p
        unique[key]=p
    d['pins']['rows']=[[p[n] for n in fields] for p in unique.values()]
    comps={}
    for row in d['components']['rows']:
        if row[1].startswith('PAD'):continue
        if row[1] in comps:assert row[2:]==comps[row[1]][2:],row
        comps[row[1]]=row
    d['components']['rows']=list(comps.values())
    NORMALIZATION.update(original_component_rows=source_component_rows,original_pin_rows=len(rows),
                         synthetic_alias_rows=aliases,unique_component_count=len(comps),
                         retained_probe_pin_rows=len(unique))
    return d


def recovery():
    r=recover.Recovery(NAME,SOURCE,normalize_probe)
    # NET_nn is an export-generated name, not a functional signal identity.
    r.aliases={}
    return r


def values():
    v={f'C{i}':'100nF' for i in [1,8,9,10,11,12,13,14,31,62,65,66,68,75,76,78,79,80,81,82,83]}
    v.update(C2='12pF',C3='12pF',C4='18pF',C5='18pF',C7='10uF',C63='100uF',C64='10uF',C67='1uF',C77='330nF',C84='100uF')
    for i in list(range(85,100))+[101,102]:v[f'C{i}']='Unspecified in PDF'
    for i in [1,2,3,14,15,16,71,72,74,83,86,87,89,90,91]:v[f'R{i}']='10k'
    for i in [4,37]:v[f'R{i}']='100k'
    for i in [10,11,12,13,77,93,94,96,98,100,102]:v[f'R{i}']='1k'
    for i in [65,67,68,78,84,85]:v[f'R{i}']='8.2k'
    for i in [69,70,73,82,88]:v[f'R{i}']='22R'
    for i in [92,95,97,99,101,103]:v[f'R{i}']='5.6k'
    v.update(R7='1.5k',R8='33R',R9='33R',R17='330R',R18='33k',R30='33k',R35='2.2k',R36='2.2k')
    for ref in ['D1','D6','D7','D9','D11','D12','D13']:v[ref]='MBRA210LT3'
    v.update(D4='B1100-13-F',D5='15V zener',IC1='LPC1769',IC4='MCP44X1',IC9='MCP44X1',IC10='LM1117-3.3V',
             IC11='78L12F',IC13='R-78E-5.0',IC14='Gate driver (part unspecified)',IC15='Gate driver (part unspecified)',
             Q1='BSL207SP',Q2='12MHz crystal',Q4='ZXMN4A06',Q8='ZXMN4A06',Q5='AOT240L',Q6='AOT240L',Q7='AOT240L',
             Q10='SUD50P04-08-GE3',S1='RESET',S2='ISPBOOT',S3='PLAY / LED',S6='UART0 - RESERVED',U1='MicroSD',X14='USB',
             X='Motor X',Y='Motor Y',Z='Motor Z',N1='Motor 4',N2='Motor 5')
    for i in range(1,6):v[f'H{i}']='Driver supply bypass'
    for i in [1,2,3,4]:v[f'LED{i}']='Status LED'
    for i in [5,7,8,9,10,11,12]:v[f'LED{i}']='Indicator LED'
    for i in [1,7,8,9,11,13]:v[f'J{i}']='Supply input' if i==1 else 'Switched power output'
    for i in [14,16,19,21,22,26]:v[f'JP{i}']='Endstop / 5V'
    v.update(JP23='PLAY input',JP24='PLAY LED')
    for base in [7,9,12,15,18]:
        v[f'JP{base}']='Stepper power / motor'
        v[f'JP{base}1']='Stepper control'
        for j in [2,3]:v[f'JP{base}{j}']='Microstep select'
    return v


def build_board(r):
    bb.LIBRARY=LIB
    # Isolated NET_nn names are retained so the pin inventory can cite the export.
    # Mark truly isolated pads NC only after copper connectivity has been checked.
    m=bb.make_board(r,values())
    counts=Counter(p['net'] for c in m['components'] for p in c['pins'])
    isolated={n for n,count in counts.items() if n.startswith('NET_') and count==1}
    board=k.LoadBoard(str(FOLDER/(NAME+'.kicad_pcb')))
    for c in m['components']:
        for p in c['pins']:
            if p['net'] in isolated:p['net']=''
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname().lstrip('/') in isolated:pad.SetNet(board.FindNet(0))
    for item in [*board.GetTracks(),*board.Zones()]:
        if item.GetNetname().lstrip('/') in isolated:item.SetNet(board.FindNet(0))
    k.SaveBoard(str(FOLDER/(NAME+'.kicad_pcb')),board)
    m['probe_normalization']=NORMALIZATION
    m['source_schematic']={'path':'../../Microsmt-PNPv3/PCB_motherboard/SCH.pdf',
                         'sha256':hashlib.sha256((recover.ROOT/'../../Microsmt-PNPv3/PCB_motherboard/SCH.pdf').read_bytes()).hexdigest()}
    m['isolated_source_nets']=sorted(isolated)
    (FOLDER/'recovery.json').write_text(json.dumps(m,indent=2)+'\n')
    used={c['footprint'].split(':',1)[1] for c in m['components']}
    for file in (recover.OUTPUT/'libraries'/(LIB+'.pretty')).glob('*.kicad_mod'):
        if file.stem not in used:file.unlink()
    return m

if __name__=='__main__':
    FOLDER.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    r=recovery()
    print('source geometry',r.width,r.height,'components',len(r.components),'pins',len(r.pins),'conflicts',r.conflicts,flush=True)
    with (BUILD/'recovery-cache.pkl').open('wb') as f:pickle.dump(r,f)
    m=build_board(r)
