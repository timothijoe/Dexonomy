#!/usr/bin/env python3
"""Repair the frozen current-model required-finger drift set, with fresh audits."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import sys
import traceback
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
os.environ.setdefault('MUJOCO_GL','egl')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256
from dexonomy.integrations.bench2dex.shadow_batch import digest
from dexonomy.integrations.bench2dex.current_contact_repair import refine,audit_gate,focus_by_phase,validate_audit_binding
from dexonomy.integrations.bench2dex.contact_region_audit import audit_case,CONFIG

DEFAULT=Path('output/shadow_wuji_contact_repair/current44_2026-10-16')
BASE=Path('output/shadow_wuji_all_types/current44_2026-10-16')


def verify(receipts):
    for r in receipts:
        if sha256(r['path'])!=r['sha256']:raise ValueError('Frozen input changed: '+r['path'])


def prepare(root,base,max_nfev=80,seconds=240):
    root,base=Path(root),Path(base)
    if root.exists():raise ValueError('Fresh output required; use --resume for an existing plan')
    results=base/'results.json';data=json.loads(results.read_text());jobs=[];inputs=[file_receipt(results)]
    for case in data['cases']:
        if case['status']!='kinematic_candidate' or not case['required_source_patch_displaced']:continue
        folder=Path(case['result_folder']).resolve();audit=Path(case['contact_audit']).resolve()
        a=json.loads(audit.read_text());validate_audit_binding(folder,a)
        receipts=[file_receipt(folder/'postures.npz'),file_receipt(folder/'result.json'),file_receipt(audit)]
        inputs.extend(receipts)
        jobs.append({'case_id':case['case_id'],'baseline_folder':str(folder),'audit':str(audit),
            'focus_by_phase':focus_by_phase(a),'inputs':receipts})
    for name in ['tools/repair_current_shadow_contacts.py','dexonomy/integrations/bench2dex/current_contact_repair.py',
        'dexonomy/integrations/bench2dex/contact_region_refine.py','dexonomy/integrations/bench2dex/contact_region_audit.py',
        'dexonomy/integrations/bench2dex/shadow_retarget.py','dexonomy/integrations/bench2dex/shadow_thumb_v2.py',
        'dexonomy/integrations/bench2dex/shadow_thumb_v3.py','dexonomy/integrations/bench2dex/gravity_hold_probe.py']:
        inputs.append(file_receipt(Path(name)))
    plan={'base':str(base.resolve()),'jobs':jobs,'inputs':inputs,'max_nfev':max_nfev,'seconds':seconds,
        'scope':'Only baseline static candidates with required-finger source-patch drift; original data read-only',
        'physical_passed':None}
    plan['identity']=digest(plan);root.mkdir(parents=True);atomic_json(root/'plan.json',plan);return plan


def one(job,root,max_nfev,seconds):
    root=Path(root);cid=job['case_id'];dest=root/'samples'/cid
    verify(job['inputs'])
    if dest.exists():raise ValueError('Incomplete output needs explicit inspection: '+str(dest))
    report=refine(job['baseline_folder'],job['audit'],dest,max_nfev,seconds)
    # A V3-compatible rendering/audit adapter. Its metadata explicitly identifies the proposal.
    # This does not update the frozen result or reuse its old selected-quality labels.
    proposal=dest/'proposal';proposal.mkdir()
    old=json.loads((Path(job['baseline_folder'])/'result.json').read_text())
    old['status']='kinematic_candidate' if report['static_proposal_passed'] else 'kinematic_rejected'
    old['selected_version']='contact_repair_proposal';old['selected_quality']=report['geometry']
    old['selected_natural']=report['natural'];old['proposed_quality']=report['geometry'];old['proposed_natural']=report['natural']
    old['failure_reasons']=report['geometry']['failure_reasons']+report['natural']['failure_reasons']
    old['physical_passed']=None;old['full_task_passed']=None
    old['contact_repair']={'proposal_only':True,'report':file_receipt(dest/'result.json'),
        'baseline':file_receipt(Path(job['baseline_folder'])/'result.json')}
    atomic_json(proposal/'result.json',old)
    with np.load(dest/'postures.npz',allow_pickle=False) as z:
        source=z['source_qpos'].copy();baseline=z['baseline_qpos'].copy();proposed=z['proposed_qpos'].copy()
    if not np.array_equal(proposed[0],baseline[0]):raise ValueError('Pregrasp changed')
    for pi,phase in [(1,'grasp'),(2,'squeeze')]:
        if not job['focus_by_phase'][phase] and not np.array_equal(proposed[pi],baseline[pi]):raise ValueError('Unaffected phase changed')
    if not np.isfinite(proposed).all():raise ValueError('Non-finite pose')
    np.savez_compressed(proposal/'postures.npz',source_qpos=source,wuji_v2_qpos=baseline,wuji_selected_qpos=proposed,
        phase=np.array(['pregrasp','grasp','squeeze']))
    a_job={'case_id':cid,'folder':str(proposal.resolve()),'postures':file_receipt(proposal/'postures.npz'),
        'result':file_receipt(proposal/'result.json')}
    after=audit_case(a_job,root/'audit',CONFIG);before=json.loads(Path(job['audit']).read_text())
    gate=audit_gate(before,after);adopt=bool(report['static_proposal_passed'] and gate['passed'])
    reasons=[]
    if not report['geometry']['passed']:reasons+=report['geometry']['failure_reasons']
    if not report['natural']['passed']:reasons+=report['natural']['failure_reasons']
    if not report['patch_restored']:reasons.append('focus_patch_not_restored_to_2mm')
    if not report['protected_patches_passed']:reasons.append('protected_patch_regressed')
    if not gate['passed']:reasons.append('fresh_audit_gate_failed')
    verify(job['inputs'])
    row={'case_id':cid,'adopted':adopt,'baseline_folder':job['baseline_folder'],
        'proposal_folder':str(proposal.resolve()),'selected_folder':str(proposal.resolve()) if adopt else job['baseline_folder'],
        'selected_audit':str((root/'audit/cases'/f'{cid}.json').resolve()) if adopt else job['audit'],
        'focus_by_phase':job['focus_by_phase'],'static_proposal_passed':report['static_proposal_passed'],
        'audit_gate':gate,'failure_reasons':reasons,'seconds':report['seconds'],
        'physical_passed':None,'full_task_passed':None,
        'artifacts':[file_receipt(p) for p in [dest/'result.json',dest/'postures.npz',proposal/'result.json',
            proposal/'postures.npz',root/'audit/cases'/f'{cid}.json']]}
    atomic_json(dest/'receipt.json',row);return row


def run(root,workers=8,limit=None):
    root=Path(root);plan=json.loads((root/'plan.json').read_text());verify(plan['inputs'])
    assert digest({k:v for k,v in plan.items() if k!='identity'})==plan['identity']
    rows=[];todo=[]
    for j in plan['jobs']:
        receipt=root/'samples'/j['case_id']/'receipt.json'
        if receipt.is_file():
            row=json.loads(receipt.read_text());verify(row['artifacts']);rows.append(row)
        else:todo.append(j)
    if limit is not None:todo=todo[:limit]
    def save():
        data={'total':len(plan['jobs']),'completed':len(rows),'adopted':sum(x['adopted'] for x in rows),
            'baseline_retained':sum(not x['adopted'] for x in rows),'finished':len(rows)==len(plan['jobs']),
            'rows':sorted(rows,key=lambda x:x['case_id']),'physical_passed':None,'full_task_passed':None}
        atomic_json(root/'summary.json',data)
        atomic_json(root/'progress.json',{k:v for k,v in data.items() if k!='rows'})
    save()
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as ex:
        fs={ex.submit(one,j,str(root),plan['max_nfev'],plan['seconds']):j for j in todo}
        for f in as_completed(fs):
            try:row=f.result()
            except Exception:
                atomic_json(root/'error.json',{'job':fs[f],'traceback':traceback.format_exc()});raise
            rows.append(row);save();print(json.dumps({k:row[k] for k in ['case_id','adopted','failure_reasons','seconds']}),flush=True)
    verify(plan['inputs']);save();return rows


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--base',type=Path,default=BASE);p.add_argument('--resume',action='store_true')
    p.add_argument('--workers',type=int,default=8,choices=range(1,9));p.add_argument('--limit',type=int)
    p.add_argument('--max-nfev',type=int,default=80);p.add_argument('--seconds',type=float,default=240)
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    with (a.output.parent/('.'+a.output.name+'.run.lock')).open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not a.resume:prepare(a.output,a.base,a.max_nfev,a.seconds)
        run(a.output,a.workers,a.limit)
