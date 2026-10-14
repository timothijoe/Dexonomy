#!/usr/bin/env python3
"""Bounded three-phase retargeting of selected Shadow source grasps."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL','egl')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json
from dexonomy.integrations.bench2dex.shadow_retarget import transfer

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection',type=Path,default=Path('output/shadow_wuji_v1/asset_selection/matches.json'))
    parser.add_argument('--target-model',type=Path,default=Path('output/bench2dex_v1/models/right/hand.xml'))
    parser.add_argument('--config',type=Path,default=Path('configs/bench2dex/shadow_retarget.yaml'))
    parser.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v1/retarget_v1'))
    parser.add_argument('--assets',nargs='+')
    parser.add_argument('--max-cases',type=int,default=8)
    parser.add_argument('--no-render',action='store_true')
    args=parser.parse_args()
    if args.max_cases<1 or args.max_cases>8:parser.error('max-cases must be 1..8')
    if args.output.exists():parser.error('output exists; choose a new directory')
    args.output.mkdir(parents=True)
    selected=json.loads(args.selection.read_text())['initial_selection']
    if args.assets:
        unknown=set(args.assets)-{s['bench_object'] for s in selected}
        if unknown:parser.error('unknown selected assets: '+str(sorted(unknown)))
        selected=[s for s in selected if s['bench_object'] in args.assets]
    groups={}
    for s in selected:
        if s['status']!='source_extracted_not_transferred':continue
        key=(s['source']['sha256'],s['source_index'])
        groups.setdefault(key,[]).append(s)
    results=[]
    for group in list(groups.values())[:args.max_cases]:
        s=group[0];folder=args.output/s['id']
        try:
            report=transfer(s,args.target_model,args.config,folder,not args.no_render)
            report['bench_targets']=[g['bench_object'] for g in group]
            atomic_json(folder/'result.json',report)
            row={'source':s['id'],'bench_targets':report['bench_targets'],'status':report['status'],
                 'failure_reasons':report['failure_reasons'],'result':str(folder/'result.json')}
        except Exception as exc:
            row={'source':s['id'],'bench_targets':[g['bench_object'] for g in group],
                 'status':'error','error':f'{type(exc).__name__}: {exc}'}
            atomic_json(folder/'failure.json',row)
        results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        atomic_json(args.output/'summary.json',{'attempts':len(results),'results':results,'physical_passed':None})
