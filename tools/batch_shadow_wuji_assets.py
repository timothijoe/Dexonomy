#!/usr/bin/env python3
"""Cover all currently matched assets with three to four fixed source grasp types."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL','egl')
for variable in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[variable]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.shadow_batch import prepare_plan,run_batch

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matches',type=Path,default=Path('output/shadow_wuji_v1/asset_selection_v3/matches.json'))
    parser.add_argument('--profile',type=Path,default=Path('configs/bench2dex/shadow_asset_batch.yaml'))
    parser.add_argument('--object-root',type=Path,default=Path('assets/object'))
    parser.add_argument('--target-model',type=Path,default=Path('output/bench2dex_v1/models/right/hand.xml'))
    parser.add_argument('--grasp-config',type=Path,default=Path('configs/bench2dex/shadow_retarget_batch.yaml'))
    parser.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v1/all_matched_batch_v1'))
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if args.resume:
        plan=json.loads((args.output/'plan.json').read_text())
    else:
        plan=prepare_plan(args.matches,args.profile,args.object_root,args.target_model,args.grasp_config,args.output)
    print(json.dumps({k:plan[k] for k in ['asset_count','coverage_entries','unique_source_cases']},indent=2),flush=True)
    if not args.prepare_only:
        summary=run_batch(plan,args.output,args.workers)
        print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
        if summary['status_counts'].get('error',0):sys.exit(2)
