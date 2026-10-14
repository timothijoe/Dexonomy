#!/usr/bin/env python3
"""Refine the same V2 sources with hard geometric thumb-bend constraints."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL', 'egl')
for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[name] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.thumb_v3_batch import prepare_v3, run_v3

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=Path('output/shadow_wuji_v2/all_matched_thumb_v2'))
    parser.add_argument('--config', type=Path, default=Path('configs/bench2dex/shadow_thumb_v3.yaml'))
    parser.add_argument('--output', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    plan = json.loads((args.output / 'plan.json').read_text()) if args.resume else prepare_v3(args.baseline, args.config, args.output)
    print(json.dumps({k: plan[k] for k in ['asset_count', 'coverage_entries', 'unique_source_cases']}, indent=2), flush=True)
    if not args.prepare_only:
        result = run_v3(plan, args.output, args.workers)
        print(json.dumps({k: v for k, v in result.items() if k != 'results'}, indent=2))
        if result['status_counts'].get('error'): sys.exit(1)
