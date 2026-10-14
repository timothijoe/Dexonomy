#!/usr/bin/env python3
"""Refine a fixed V1 source case with thumb-specific V2 objectives."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL','egl')
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.shadow_thumb_v2 import refine_case

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path('configs/bench2dex/shadow_thumb_v2.yaml'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--no-render',action='store_true')
    args=parser.parse_args()
    r=refine_case(args.baseline,args.config,args.output,not args.no_render)
    print(json.dumps({'selected':r['selected_version'],'reason':r['selection_reason'],
        'baseline_thumb_score':sum(m['score'] for m in r['baseline_thumb'].values())/3,
        'proposed_thumb_score':sum(m['score'] for m in r['proposed_thumb'].values())/3,
        'quality_passed':r['selected_quality']['passed'],'seconds':r['seconds']},indent=2),flush=True)
