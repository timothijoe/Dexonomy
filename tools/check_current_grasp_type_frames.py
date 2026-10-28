#!/usr/bin/env python3
"""Independently verify all current-type camera-grid receipts and source hashes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json,sha256
from dexonomy.integrations.bench2dex.shadow_batch import digest,verify_completed
from dexonomy.integrations.bench2dex.thumb_v3_rotation import frame_name


def check(root):
    root=Path(root);folder=root/'review/rotation';plan=json.loads((folder/'plan.json').read_text())
    copy=dict(plan);expected=copy.pop('identity')
    if digest(copy)!=expected:raise ValueError('View plan identity changed')
    for receipt in [plan['coverage'],plan['renderer']]:
        if sha256(receipt['path'])!=receipt['sha256']:raise ValueError('View source changed')
    names={frame_name(phase,mode,pitch,yaw) for phase in ['pregrasp','grasp','squeeze'] for mode in ['scene','hand'] for pitch in range(5) for yaw in range(12)}
    def inspect(job):
        for key in ['result','postures']:
            if sha256(job[key]['path'])!=job[key]['sha256']:raise ValueError('Pose/result changed')
        dest=folder/'frames'/job['case_id']
        if job.get('reuse_frames'):
            receipt=job['frame_receipt']
            if sha256(receipt['path'])!=receipt['sha256']:raise ValueError('Cached receipt changed')
            expected=json.loads(Path(receipt['path']).read_text())['identity']
        else:expected=digest({'plan':plan['identity'],'case':job['case_id']})
        row=verify_completed(dest,expected)
        if row is None or row['frames']!=360 or {p.name for p in dest.glob('*.webp')}!=names:raise ValueError('Incomplete camera grid')
        if row['postures']['sha256']!=job['postures']['sha256']:raise ValueError('Frames correspond to another pose')
        return row['frames']
    with ThreadPoolExecutor(max_workers=8) as ex:frames=sum(ex.map(inspect,plan['jobs']))
    report={'cases_verified':len(plan['jobs']),'frames_verified':frames,
        'all_frame_checksums_and_grid_names_verified':True,'source_pose_and_result_hashes_unchanged':True,
        'reused_cases':sum('reuse_frames' in j for j in plan['jobs'])}
    atomic_json(root/'frame_checksum_check.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_all_types/current44_2026-10-16'))
    p.add_argument('--wait',action='store_true');a=p.parse_args()
    if a.wait:
        while not (a.output/'review/rotation/export_check.json').is_file():time.sleep(10)
    print(json.dumps(check(a.output),ensure_ascii=False,indent=2),flush=True)
