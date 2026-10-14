#!/usr/bin/env python3
"""Extract bounded Shadow grasp seeds for Bench2Dex-related local assets."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.asset_matching import build_matching

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,default=Path('output/bench2dex_mujoco/catalog/catalog.json'))
    parser.add_argument('--object-root',type=Path,default=Path('assets/object'))
    parser.add_argument('--config',type=Path,default=Path('configs/bench2dex/dexonomy_asset_matching.yaml'))
    parser.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v1/asset_selection'))
    args=parser.parse_args()
    report=build_matching(args.catalog,args.object_root,args.config,args.output)
    print(json.dumps({'bench_object_count':report['bench_object_count'],'match_counts':report['match_counts'],
                      'selected_sources':len(report['initial_selection'])},indent=2))
