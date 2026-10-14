#!/usr/bin/env python3
"""Find source patch, edge and finger-segment changes in frozen V3 poses."""
import argparse
import os
from pathlib import Path
import sys

for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[name] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.contact_region_audit import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    parser.add_argument('--output', type=Path, default=Path('output/shadow_wuji_v3/contact_region_audit_2026-10-14'))
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args(); run(args.batch, args.output, args.workers)
