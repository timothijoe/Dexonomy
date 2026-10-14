#!/usr/bin/env python3
"""Compare frozen V3 and patch-repair proposals under declared hold probes."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
import os
from pathlib import Path
import sys

for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256
from dexonomy.integrations.bench2dex.gravity_hold_probe import probe,CONFIG

CASES=['case_0091__24_Tip_Pinch','case_0038__10_Power_Disk','case_0041__1_Large_Diameter']


def one(job):
    with np.load(job['pose_path'],allow_pickle=False) as z:q=z[job['pose_key']][2].copy()
    r=probe(job['baseline_folder'],q,job['output'],job['friction'],job['pressure_rad'])
    return {**job,**{k:r[k] for k in ['passed','failure_reasons','max_translation_m','max_rotation_deg',
             'max_hand_object_penetration_m','steady_hand_force_weight_ratio','max_joint_effort_fraction','duration_s']}}


if __name__=='__main__':
    root=Path('output/shadow_wuji_v3/contact_gravity_comparison')
    if root.exists():raise ValueError('Use a fresh comparison output')
    root.mkdir(parents=True);jobs=[];inputs=[]
    for cid in CASES:
        baseline=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/samples')/cid
        repair=Path('output/shadow_wuji_v3/contact_repair_pilot')/cid
        for version,folder,key in [('baseline',baseline,'wuji_selected_qpos'),('repaired',repair,'proposed_qpos')]:
            inputs.append(file_receipt(folder/'postures.npz'))
            for friction in [.5,1.]:
                for pressure in [0.,.025]:
                    job={'case_id':cid,'version':version,'pose_path':str(folder/'postures.npz'),'pose_key':key,
                         'baseline_folder':str(baseline),'friction':friction,'pressure_rad':pressure,
                         'output':str(root/cid/f'{version}_mu{friction}_press{pressure}')}
                    jobs.append(job)
    atomic_json(root/'plan.json',{'jobs':jobs,'config':CONFIG,'inputs':inputs,
                'engine':file_receipt(Path('dexonomy/integrations/bench2dex/gravity_hold_probe.py')),
                'scope':'24 fixed-wrist suspended hold comparisons; no original posture overwrite'})
    rows=[]
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn')) as ex:
        futures=[ex.submit(one,j) for j in jobs]
        for f in as_completed(futures):
            r=f.result();rows.append(r);atomic_json(root/'summary.json',{'completed':len(rows),'total':len(jobs),'rows':rows})
            print(json.dumps(r,ensure_ascii=False),flush=True)
    for p in inputs:
        if sha256(p['path'])!=p['sha256']:raise ValueError('Input changed')
