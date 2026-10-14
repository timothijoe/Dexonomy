#!/usr/bin/env python3
"""Export the existing V3 poses at the previous viewer's camera angles."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL', 'egl')
for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[name] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.thumb_v3_rotation import prepare, run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    parser.add_argument('--output', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/rotation'))
    parser.add_argument('--ids', nargs='*')
    parser.add_argument('--width', type=int, default=480)
    parser.add_argument('--height', type=int, default=360)
    parser.add_argument('--quality', type=int, default=76)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    plan = json.loads((args.output / 'plan.json').read_text()) if args.resume else prepare(
        args.batch, args.output, args.ids, args.width, args.height, args.quality)
    if not args.prepare_only:
        r = run(plan, args.output, args.workers)
        print(json.dumps({k: v for k, v in r.items() if k != 'rows'}, ensure_ascii=False))
