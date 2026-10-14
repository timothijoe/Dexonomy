"""Verify and refine the exact V1 batch, retaining explicit non-adoptions."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing
from pathlib import Path
import shutil

import yaml

from .common import atomic_json,file_receipt,sha256
from .shadow_batch import digest,verify_plan,job_identity,verify_completed
from .shadow_thumb_v2 import refine_case


def prepare_v2(baseline_root,config_path,output):
    baseline_root,config_path,output=Path(baseline_root),Path(config_path),Path(output)
    if output.exists():raise ValueError('V2 batch directory exists; use resume or a new directory')
    base=json.loads((baseline_root/'plan.json').read_text());verify_plan(base)
    cfg=yaml.safe_load(config_path.read_text())
    if cfg.get('schema_version')!=2:raise ValueError('V2 configuration required')
    jobs=[]
    for job in base['jobs']:
        folder=baseline_root/'samples'/job['case_id']
        row=verify_completed(folder,job_identity(base,job))
        if not row or not row['postures_available']:raise ValueError('V1 case has no verified posture: '+job['case_id'])
        jobs.append({**job,'baseline_folder':str(folder),'baseline_receipt':file_receipt(folder/'receipt.json'),
                     'baseline_result':file_receipt(folder/'result.json'),'baseline_postures':file_receipt(folder/'postures.npz')})
    fallback=file_receipt(Path(cfg['fallback_config'])) if cfg.get('fallback_config') else None
    plan={'schema_version':2,'asset_count':base['asset_count'],'coverage_entries':base['coverage_entries'],
          'unique_source_cases':len(jobs),'assets':base['assets'],'jobs':jobs,'deferred_assets':base['deferred_assets'],
          'baseline_root':str(baseline_root),'baseline_plan':file_receipt(baseline_root/'plan.json'),
          'baseline_plan_identity':base['plan_identity'],'side':'right',
          'inputs':{'config':file_receipt(config_path),'annotation':file_receipt(Path(cfg['source_pad_annotation'])),
                    'engine':file_receipt(Path(__file__).parent/'shadow_thumb_v2.py'),'batch_engine':file_receipt(Path(__file__))},
          'fallback_config':fallback,'physical_passed':None}
    plan['plan_identity']=digest(plan)
    output.mkdir(parents=True);atomic_json(output/'plan.json',plan)
    return plan


def verify_v2(plan):
    copy=dict(plan);expected=copy.pop('plan_identity')
    if digest(copy)!=expected:raise ValueError('V2 plan changed')
    for receipt in [plan['baseline_plan'],*plan['inputs'].values(),*[j[k] for j in plan['jobs'] for k in ['baseline_receipt','baseline_result','baseline_postures']]]:
        if sha256(receipt['path'])!=receipt['sha256']:raise ValueError('V2 input changed: '+receipt['path'])
    if plan.get('fallback_config') and sha256(plan['fallback_config']['path'])!=plan['fallback_config']['sha256']:
        raise ValueError('Fallback configuration changed')
    verify_plan(json.loads(Path(plan['baseline_plan']['path']).read_text()))


def identity(plan,job):return digest({'plan':plan['plan_identity'],'case':job['case_id']})


def _run(job,config,folder,expected):
    folder=Path(folder)
    try:
        result=refine_case(Path(job['baseline_folder']),Path(config),folder,True)
        attempts=[{'config':result['config'],'selected_version':result['selected_version'],'reason':result['selection_reason']}]
        cfg=yaml.safe_load(Path(config).read_text())
        if result['selected_version']=='v1_retained' and cfg.get('fallback_config'):
            primary=folder/'primary_trial';primary.mkdir()
            for name in ['result.json','postures.npz','comparison.png']:
                if (folder/name).is_file():shutil.copyfile(folder/name,primary/name)
            for name in ['hand_only','proposal']:
                if (folder/name).is_dir():shutil.copytree(folder/name,primary/name)
            fallback=refine_case(Path(job['baseline_folder']),Path(cfg['fallback_config']),folder/'fallback_trial',True)
            attempts.append({'config':fallback['config'],'selected_version':fallback['selected_version'],'reason':fallback['selection_reason']})
            if fallback['selected_version']=='v2':
                result=fallback
                for name in ['postures.npz','comparison.png','hand_only/comparison.png']:
                    shutil.copyfile(folder/'fallback_trial'/name,folder/name)
        result['refinement_attempts']=attempts
        result['bench_targets']=sorted({a['bench_object'] for a in job['aliases']})
        result['batch_aliases']=job['aliases'];atomic_json(folder/'result.json',result)
        old=sum(m['score'] for m in result['baseline_thumb'].values())/3
        new=sum(m['score'] for m in result['selected_thumb'].values())/3
        row={'case_id':job['case_id'],'status':result['status'],'selected_version':result['selected_version'],
             'selection_reason':result['selection_reason'],'failure_reasons':result['selected_quality']['failure_reasons'],
             'baseline_passed':result['baseline_quality']['passed'],'proposed_passed':result['proposed_quality']['passed'],
             'thumb_score_before':old,'thumb_score_selected':new,'seconds':result['seconds'],
             'attempt_count':len(attempts),
             'postures_available':True,'solver_termination':result['joint_solver']['termination']}
    except Exception as exc:
        folder.mkdir(parents=True,exist_ok=True)
        row={'case_id':job['case_id'],'status':'error','error':f'{type(exc).__name__}: {exc}',
             'postures_available':(folder/'postures.npz').is_file()}
        atomic_json(folder/'failure.json',row)
    artifacts=[{'path':str(p.relative_to(folder)),'sha256':sha256(p)} for p in sorted(folder.rglob('*')) if p.is_file()]
    atomic_json(folder/'receipt.json',{'identity':expected,'row':row,'artifacts':artifacts})
    return row


def summary(plan,rows):
    ordered=[rows[j['case_id']] for j in plan['jobs'] if j['case_id'] in rows]
    return {'schema_version':2,'asset_count':plan['asset_count'],'coverage_entries':plan['coverage_entries'],
            'unique_source_cases':len(plan['jobs']),'completed_source_cases':len(ordered),
            'status_counts':dict(Counter(r['status'] for r in ordered)),
            'selection_counts':dict(Counter(r.get('selected_version','error') for r in ordered)),
            'all_cases_terminal':len(ordered)==len(plan['jobs']),
            'cases_with_postures':sum(r['postures_available'] for r in ordered),'results':ordered,
            'physical_passed':None,'full_task_passed':None}


def run_v2(plan,output,workers=4):
    if not 1<=workers<=4:raise ValueError('One to four workers supported')
    verify_v2(plan);output=Path(output);rows={};pending=[]
    for job in plan['jobs']:
        folder=output/'samples'/job['case_id'];expected=identity(plan,job)
        completed=verify_completed(folder,expected)
        if completed:rows[job['case_id']]=completed
        elif folder.exists():raise ValueError('Incomplete V2 case directory: '+str(folder))
        else:pending.append((job,folder,expected))
    atomic_json(output/'summary.json',summary(plan,rows))
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as executor:
        futures=[executor.submit(_run,job,plan['inputs']['config']['path'],str(folder),expected) for job,folder,expected in pending]
        for future in as_completed(futures):
            row=future.result();rows[row['case_id']]=row
            atomic_json(output/'summary.json',summary(plan,rows))
            print(json.dumps({'completed':len(rows),'total':len(plan['jobs']),**row},ensure_ascii=False),flush=True)
    return summary(plan,rows)
