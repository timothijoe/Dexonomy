#!/usr/bin/env python3
"""Refine one V2 case with hard geometric thumb-bend constraints."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL', 'egl')
for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[name] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.shadow_thumb_v3 import refine_case

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('configs/bench2dex/shadow_thumb_v3.yaml'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--no-render', action='store_true')
    args = parser.parse_args()
    r = refine_case(args.baseline, args.config, args.output, not args.no_render)
    print(json.dumps({k: r[k] for k in ['status', 'selected_version', 'selection_reason', 'failure_reasons', 'seconds']}, ensure_ascii=False))
