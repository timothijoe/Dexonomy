#!/usr/bin/env python3
"""Audit inward-to-edge drift and run four bounded multi-region repair trials."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing
import os
from pathlib import Path
import sys

for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
os.environ.setdefault('MUJOCO_GL','egl')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256
from dexonomy.integrations.bench2dex.contact_region_refine import edge_shift,refine

FOCUS={'case_0015__11_Power_Sphere':['index','middle'],'case_0046__16_Lateral':['index'],
       'case_0096__15_Fixed_Hook':['pinky'],'case_0170__16_Lateral':['index']}


def one(job):
    r=refine(job['folder'],job['audit'],job['fingers'],job['output'])
    return {k:r[k] for k in ['case_id','focus_fingers','static_proposal_passed','patch_restored','protected_patches_passed','details','seconds']}


def run(batch,audit,output,workers=2):
    batch,audit,output=map(Path,(batch,audit,output))
    if output.exists():raise ValueError('Use a fresh edge repair output')
    rows=[]
    for path in sorted((audit/'cases').glob('*.json')):
        d=json.loads(path.read_text())
        for r in d['rows']:
            if r['version']=='selected' and edge_shift(r):
                rows.append({'case_id':d['case_id'],'status':d['original_status'],'phase':r['phase'],'finger':r['finger'],
                    'required_by_v3':r['required'] and r['finger']!='palm','source_edge_m':r['source']['edge_distance_m'],
                    'target_edge_m':r['target']['edge_distance_m'],'patch_gap_m':r['target']['anchor']['distance_m'],
                    'object':d['source_selection']['dexonomy_object']})
    output.mkdir(parents=True);jobs=[]
    for cid,fingers in FOCUS.items():jobs.append({'case_id':cid,'fingers':fingers,'folder':str(batch/'samples'/cid),
        'audit':str(audit/'cases'/(cid+'.json')),'output':str(output/'samples'/cid)})
    inputs=[file_receipt(batch/'samples'/cid/'postures.npz') for cid in FOCUS]
    atomic_json(output/'plan.json',{'jobs':jobs,'inputs':inputs,'engine':file_receipt(Path(__file__)),
        'scope':'Four source-interior to target-edge repair proposals, original V3 preserved'})
    atomic_json(output/'edge_shift_audit.json',{'rows':rows,'cases':len({r['case_id'] for r in rows}),
        'candidate_cases':len({r['case_id'] for r in rows if r['status']=='kinematic_candidate'}),'diagnostic_only':True})
    results=[]
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as ex:
        futures=[ex.submit(one,j) for j in jobs]
        for f in as_completed(futures):
            result=f.result();results.append(result);atomic_json(output/'summary.json',{'completed':len(results),'total':len(jobs),'results':results})
            print(json.dumps({'case_id':result['case_id'],'completed':len(results),'passed':result['static_proposal_passed'],'seconds':result['seconds']}),flush=True)
    for item in inputs:
        if sha256(item['path'])!=item['sha256']:raise ValueError('Original posture changed')
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    parser.add_argument('--audit',type=Path,default=Path('output/shadow_wuji_v3/contact_region_audit_2026-10-14'))
    parser.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v4/edge_repair_2026-10-15'))
    parser.add_argument('--workers',type=int,default=2,choices=range(1,5));a=parser.parse_args()
    run(a.batch,a.audit,a.output,a.workers)
