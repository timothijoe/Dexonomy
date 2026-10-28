#!/usr/bin/env python3
"""After optimization, export every current-model type and audit new contacts."""
import argparse
import fcntl
from concurrent.futures import ProcessPoolExecutor,as_completed,ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sys
import time
import threading
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
os.environ.setdefault('MUJOCO_GL','egl')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256
from dexonomy.integrations.bench2dex.shadow_batch import digest,verify_completed
from dexonomy.integrations.bench2dex.thumb_v3_rotation import export_case,AZIMUTHS,ELEVATIONS
from dexonomy.integrations.bench2dex.contact_region_audit import run as run_contact_audit
from tools.review_current_shadow_grasp_types import review,publish_rotation
from tools.check_current_shadow_grasp_types import check as check_plan
from tools.check_shadow_thumb_v3 import audit as check_poses


def progress(root,stage,completed,total,finished=False):
    payload={'stage':stage,'completed':completed,'total':total,'finished':finished}
    atomic_json(root/'progress.json',payload)
    path=root/'review/batch_progress.js'
    path.write_text('window.updateBatchProgress&&window.updateBatchProgress('+json.dumps(payload)+');')


def export_views(root,workers):
    review(root);folder=root/'review/rotation';frames=folder/'frames';frames.mkdir(parents=True,exist_ok=True)
    folders=json.loads((root/'review/case_folders.json').read_text())
    coverage=json.loads((root/'coverage_plan.json').read_text());kinds={e['case_id']:e['kind'] for e in coverage['entries']}
    if not (folder/'plan.json').is_file():
        jobs=[]
        for cid,path in sorted(folders.items()):
            actual=Path(path);job={'case_id':cid,'result':file_receipt(actual/'result.json'),'postures':file_receipt(actual/'postures.npz')}
            old_frames=actual.parent.parent/'rotation/frames'/actual.name
            if kinds[cid]=='reused' and (old_frames/'receipt.json').is_file():
                saved=json.loads((old_frames/'receipt.json').read_text())
                if saved['row']['postures']['sha256']!=job['postures']['sha256'] or saved['row']['frames']!=360:
                    raise ValueError('Cached views belong to another posture')
                job['reuse_frames']=str(old_frames);job['frame_receipt']=file_receipt(old_frames/'receipt.json')
            jobs.append(job)
        plan={'scope':'all_current_model_type_views','jobs':jobs,'coverage':file_receipt(root/'coverage_plan.json'),
            'renderer':file_receipt(Path('dexonomy/integrations/bench2dex/thumb_v3_rotation.py')),
            'config':{'width':480,'height':360,'quality':76}}
        plan['identity']=digest(plan);atomic_json(folder/'plan.json',plan)
    plan=json.loads((folder/'plan.json').read_text());rows=[];pending=[];ready=set()
    for job in plan['jobs']:
        for key in ['result','postures']:
            if sha256(job[key]['path'])!=job[key]['sha256']:raise ValueError('View source changed')
        dest=frames/job['case_id']
        if job.get('reuse_frames'):
            if sha256(job['frame_receipt']['path'])!=job['frame_receipt']['sha256']:raise ValueError('Cached view receipt changed')
            if not dest.exists():dest.symlink_to(Path(job['reuse_frames']).resolve(),target_is_directory=True)
            expected=json.loads(Path(job['frame_receipt']['path']).read_text())['identity']
        else:expected=digest({'plan':plan['identity'],'case':job['case_id']})
        done=verify_completed(dest,expected)
        if done:rows.append(done);ready.add(job['case_id'])
        elif dest.exists():raise ValueError('Incomplete views need inspection: '+str(dest))
        else:pending.append((job,dest,expected))
    progress(root,'rotation_frames',len(rows),len(plan['jobs']))
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as ex:
        futures={ex.submit(export_case,j,str(d),plan['config'],expected):j['case_id'] for j,d,expected in pending}
        for f in as_completed(futures):
            rows.append(f.result());ready.add(futures[f]);progress(root,'rotation_frames',len(rows),len(plan['jobs']))
            if len(rows)%20==0:
                publish_rotation(root,ready);review(root)
                print(json.dumps({'stage':'rotation_frames','completed':len(rows),'total':len(plan['jobs'])}),flush=True)
    data=json.loads((root/'review/review.json').read_text())
    entries=[]
    for e in data['entries']:
        entries.append({k:e[k] for k in ['asset','assetLabel','category','categoryLabel','status','versionLabel','selectedVersion','source','matchLabel','physicalPassed']}|
            {'caseId':Path(e['result']).parent.name,'entryId':e['asset']+'::'+e['category']})
    viewer={'caseCount':len(plan['jobs']),'scope':'full','entries':entries,**plan['config'],
        'azimuths':list(AZIMUTHS),'elevations':list(ELEVATIONS),'back':'../index.html'}
    template=Path('tools/shadow_thumb_v3_rotation.html').read_text().replace('第三版旋转对照','当前物体全部握法对照')
    (folder/'index.html').write_text(template.replace('__ROTATION_DATA__',json.dumps(viewer,ensure_ascii=False).replace('<',r'\u003c')))
    shutil.copyfile('tools/shadow_thumb_v3_rotation.js',folder/'app.js');atomic_json(folder/'viewer.json',viewer)
    atomic_json(folder/'summary.json',{'cases':len(rows),'frames':sum(r['frames'] for r in rows),
        'reused_cases':sum('reuse_frames' in j for j in plan['jobs']),'all_complete':len(rows)==len(plan['jobs'])})
    review(root)
    # All checksums are verified above; inspect dimensions and representative pixels independently.
    def inspect(job):
        path=frames/job['case_id'];files=sorted(path.glob('*.webp'))
        if len(files)!=360:raise ValueError('Incomplete camera grid')
        for f in files:
            with Image.open(f) as im:
                if im.size!=(1440,360):raise ValueError('Invalid view dimensions')
                if f.name.endswith('_p02_y00.webp'):
                    im.load()
                    for role in range(3):
                        if im.crop((480*role,0,480*(role+1),360)).getbbox() is None:raise ValueError('Blank comparison role')
        return len(files)
    with ThreadPoolExecutor(max_workers=4) as ex:headers=sum(ex.map(inspect,plan['jobs']))
    atomic_json(folder/'export_check.json',{'cases':len(plan['jobs']),'headers_verified':headers,
        'all_receipts_verified':True,'representative_three_role_frames_decoded':len(plan['jobs'])*6})


def finalize(root,workers):
    root=Path(root);check_plan(root)
    check_poses(root/'final')
    export_views(root,workers)
    if not (root/'contact_audit/plan.json').is_file():
        total=len(json.loads((root/'final/plan.json').read_text())['jobs'])
        progress(root,'contact_audit',0,total)
        stop=threading.Event()
        def audit_progress():
            while not stop.wait(15):
                n=len(list((root/'contact_audit/cases').glob('*.json')))
                progress(root,'contact_audit',n,total)
        monitor=threading.Thread(target=audit_progress,daemon=True);monitor.start()
        try:reports=run_contact_audit(root/'final',root/'contact_audit',workers)
        finally:stop.set();monitor.join()
    else:
        plan=json.loads((root/'contact_audit/plan.json').read_text())
        if not all((root/'contact_audit/cases'/(j['case_id']+'.json')).is_file() for j in plan['jobs']):
            raise ValueError('Incomplete contact audit needs inspection')
        reports=[json.loads(p.read_text()) for p in (root/'contact_audit/cases').glob('*.json')]
    from collections import defaultdict
    flags=defaultdict(set)
    for report in reports:
        for r in report['rows']:
            if r['version']=='selected':
                for flag in r['flags']:flags[flag].add(report['case_id'])
    atomic_json(root/'contact_audit/summary.json',{'cases':len(reports),'cases_by_flag':{k:len(v) for k,v in flags.items()},'diagnostic_only':True})
    report=review(root);progress(root,'complete',report['completed_types'],report['total_types'],True)
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_all_types/current44_2026-10-16'))
    p.add_argument('--workers',type=int,default=8,choices=range(1,9));p.add_argument('--wait',action='store_true');a=p.parse_args()
    with (a.output.parent/('.'+a.output.name+'.run.lock')).open('a+') as lock:
        print('Waiting for numerical batch lock' if a.wait else 'Acquiring batch lock',flush=True)
        fcntl.flock(lock,fcntl.LOCK_EX if a.wait else fcntl.LOCK_EX|fcntl.LOCK_NB)
        completed=a.output/'final/summary.json'
        if not completed.is_file() or not json.loads(completed.read_text())['all_cases_terminal']:
            raise RuntimeError('Numerical publication incomplete; inspect run.log and resume optimization first')
        finalize(a.output,a.workers)
