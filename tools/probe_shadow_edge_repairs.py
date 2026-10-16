#!/usr/bin/env python3
"""Compare static edge-repair proposals with the baseline under native-torque gravity."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing
import os
from pathlib import Path
import sys
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from dexonomy.integrations.bench2dex.gravity_hold_probe import probe,CONFIG
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256


def one(job):
    with np.load(job['pose_path'],allow_pickle=False) as z:q=z[job['pose_key']][2].copy()
    r=probe(job['folder'],q,job['output'],friction=job['friction'])
    return {**job,**{k:r[k] for k in ['passed','failure_reasons','object_mass_kg','max_translation_m',
        'max_rotation_deg','steady_hand_force_weight_ratio','duration_s']}}


def run(base,repair,root,workers=2):
    base,repair,root=map(Path,(base,repair,root))
    if root.exists():raise ValueError('Fresh output required')
    jobs=[];inputs=[]
    for p in sorted((repair/'samples').glob('*/result.json')):
        r=json.loads(p.read_text())
        if not r['static_proposal_passed']:continue
        cid=r['case_id']
        for version,folder,key in [('baseline',base/'samples'/cid,'wuji_selected_qpos'),('repaired',p.parent,'proposed_qpos')]:
            inputs.append(file_receipt(folder/'postures.npz'))
            for mu in [.5,1.]:jobs.append({'case_id':cid,'version':version,'folder':str(base/'samples'/cid),
                'pose_path':str(folder/'postures.npz'),'pose_key':key,'friction':mu,'output':str(root/cid/f'{version}_mu{mu}')})
    if not jobs:raise ValueError('No static proposals available for gravity comparison')
    root.mkdir(parents=True)
    atomic_json(root/'plan.json',{'jobs':jobs,'inputs':inputs,'config':CONFIG,
        'engine':file_receipt(Path('dexonomy/integrations/bench2dex/gravity_hold_probe.py')),
        'scope':'Static edge repairs compared at native torque; no pressure increase'})
    rows=[]
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as ex:
        for f in as_completed([ex.submit(one,j) for j in jobs]):
            r=f.result();rows.append(r);atomic_json(root/'summary.json',{'total':len(jobs),'completed':len(rows),'rows':rows})
            print(json.dumps(r),flush=True)
    for p in inputs:
        if sha256(p['path'])!=p['sha256']:raise ValueError('Input changed')
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    p.add_argument('--repair',type=Path,default=Path('output/shadow_wuji_v4/edge_repair_2026-10-15'))
    p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v4/edge_repair_2026-10-15/gravity'))
    p.add_argument('--workers',type=int,default=2,choices=range(1,5));a=p.parse_args();run(a.batch,a.repair,a.output,a.workers)
