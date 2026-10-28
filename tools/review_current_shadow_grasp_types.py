#!/usr/bin/env python3
"""Build a current-object category coverage review, including honest pending states."""
import argparse
import fcntl
from collections import Counter
import json
from pathlib import Path
from urllib.parse import quote
import sys
import os
import shutil
import numpy as np
import trimesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json
from tools.review_shadow_thumb_v3 import build
from dexonomy.util.file_util import load_scene_cfg

_MESH_EXTENTS={}


def publish_rotation(root,ready):
    root=Path(root);dest=root/'review/rotation';dest.mkdir(parents=True,exist_ok=True)
    data=json.loads((root/'review/review.json').read_text());entries=[]
    for e in data['entries']:
        if not e.get('result'):continue
        cid=Path(e['result']).parent.name
        if cid not in ready:continue
        entries.append({k:e[k] for k in ['asset','assetLabel','category','categoryLabel','status','versionLabel','selectedVersion','source','matchLabel','physicalPassed']}|{'caseId':cid,'entryId':e['asset']+'::'+e['category']})
    viewer={'caseCount':len(entries),'scope':'full','entries':entries,'width':480,'height':360,
        'azimuths':[(135+30*i)%360 for i in range(12)],'elevations':[-65,-45,-25,-5,15],'back':'../index.html'}
    template=Path('tools/shadow_thumb_v3_rotation.html').read_text().replace('第三版旋转对照','当前物体全部握法对照')
    (dest/'index.html').write_text(template.replace('__ROTATION_DATA__',json.dumps(viewer,ensure_ascii=False).replace('<',r'\u003c')))
    shutil.copyfile('tools/shadow_thumb_v3_rotation.js',dest/'app.js');atomic_json(dest/'viewer.json',viewer)


def bootstrap_cached_views(root,coverage,folders):
    root=Path(root);dest=root/'review/rotation'
    if (dest/'viewer.json').is_file():return
    ready=set();(dest/'frames').mkdir(parents=True,exist_ok=True)
    for e in coverage['entries']:
        if e['kind']!='reused':continue
        actual=Path(folders[e['case_id']]);source=actual.parent.parent/'rotation/frames'/actual.name
        receipt=source/'receipt.json'
        if not receipt.is_file():continue
        saved=json.loads(receipt.read_text())
        if saved['row']['postures']['sha256']!=e['postures']['sha256'] or saved['row']['frames']!=360:raise ValueError('Cached rotation posture mismatch')
        target=dest/'frames'/e['case_id']
        if not target.exists():target.symlink_to(source.resolve(),target_is_directory=True)
        ready.add(e['case_id'])
    if ready:publish_rotation(root,ready)

def review(root):
    root=Path(root)
    with (root/'.review.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _review(root)


def _review(root):
    root=Path(root).resolve();coverage=json.loads((root/'coverage_plan.json').read_text());dest=root/'review';dest.mkdir(exist_ok=True)
    (dest/'samples').mkdir(exist_ok=True);jobs=[];rows=[];folders={};first_pass=0
    for entry in coverage['entries']:
        cid=entry['case_id'];folder=None;provisional=False
        if entry['kind']=='reused':folder=Path(entry['result_folder']).resolve()
        elif (root/'final/samples'/cid/'receipt.json').is_file():folder=root/'final/samples'/cid
        elif (root/'v3/samples'/cid/'receipt.json').is_file():folder=root/'v3/samples'/cid;provisional=True
        job={'case_id':cid,'selection':{'dexonomy_object':entry['object']}};jobs.append(job)
        if folder is None:
            rows.append({'case_id':cid,'status':'pending','selected_version':'pending'});continue
        result=json.loads((folder/'result.json').read_text());folders[cid]=str(folder)
        link=dest/'samples'/cid
        if link.is_symlink() and link.resolve()!=folder:link.unlink()
        if not link.exists():link.symlink_to(folder,target_is_directory=True)
        if not link.is_symlink() or link.resolve()!=folder:raise ValueError('Unexpected review sample path')
        rows.append({'case_id':cid,'status':result['status'],'selected_version':result['selected_version'],
            'failure_reasons':result['failure_reasons'],'solver_termination':result['joint_solver']['termination'],
            'provisional_first_pass':provisional})
        first_pass+=provisional
    projection={'schema_version':'review_projection_not_optimizer_plan','assets':coverage['assets'],'jobs':jobs,
        'asset_count':len(coverage['models']),'unique_source_cases':coverage['total_types'],'deferred_assets':[]}
    atomic_json(dest/'plan.json',projection)
    atomic_json(dest/'summary.json',{'results':rows,'completed_source_cases':len(folders)})
    data=build(dest);data['defaultAsset']=coverage['models'][0];data['batchProgressScript']='batch_progress.js'
    diagnostics={r['case_id']:r for r in json.loads((root/'results.json').read_text())['cases']} if (root/'results.json').is_file() else {}
    data['hasContactDiagnostics']=bool(diagnostics)
    if diagnostics:data['contactSummary']='静态通过不等于原接触区域全部保留；其中 '+str(sum(r['status']=='kinematic_candidate' and r.get('required_source_patch_displaced',False) for r in diagnostics.values()))+' 个静态候选有必需手指原区域偏移标记。'
    reference={j['selection']['dexonomy_object']:np.asarray(j['selection']['size_selection']['reference_extents_m']) for j in json.loads((root/'v1/plan.json').read_text())['jobs']}
    family_labels={'can':'罐模型','bottle':'瓶模型','box':'盒模型','mug':'杯模型','bowl':'碗模型',
        'sphere':'球模型','fruit':'水果模型','plate':'盘模型','pen':'笔模型','brush':'刷子模型',
        'keyboard':'键盘模型','mouse':'鼠标模型','shoe':'鞋模型','piano_model':'钢琴模型'}
    families={a['bench_object']:a.get('family') for a in coverage['assets']}
    for e in data['entries']:
        if families.get(e['asset']) in family_labels:e['assetLabel']=family_labels[families[e['asset']]]+' · '+e['asset']
        cid=Path(e['result']).parent.name if e['result'] else None
        if cid in diagnostics:
            d=diagnostics[cid];e['contactFlags']=d['contact_flags'];e['requiredPatchDrift']=d.get('required_source_patch_displaced',False)
            e['contactAudit']=os.path.relpath(Path(d['contact_audit']).resolve(),dest)
        if cid not in folders:continue
        result=json.loads((Path(folders[cid])/'result.json').read_text());selection=result['source_selection']
        scene=load_scene_cfg(selection['scene_path']);obj=scene['scene'][scene['task']['obj_name']]
        path=obj['file_path']
        if path not in _MESH_EXTENTS:_MESH_EXTENTS[path]=trimesh.load(path,force='mesh').extents
        size=_MESH_EXTENTS[path]*np.asarray(obj['scale'])*selection['scene_scale_multiplier']
        e['sourceExtentsMm']=(size*1000).tolist()
        e['sourceReferenceRatio']=float(np.exp(np.mean(np.log(size/reference[e['asset']]))))
    data['coverageNote']='当前已有 44 模型的全部握法类别；来源尺度可能不同，卡片显示实际尺寸。待处理不计为已完成，动力学另行验证。'
    page=Path('tools/shadow_thumb_v3_review.html').read_text().replace('__REVIEW_SCRIPT__',Path('tools/shadow_thumb_v3_review.js').read_text())
    page=page.replace('最终姿态审查','当前物体全部握法类别')
    (dest/'index.html').write_text(page.replace('__DATA__',json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<',r'\u003c')))
    atomic_json(dest/'review.json',data);atomic_json(dest/'case_folders.json',folders)
    bootstrap_cached_views(root,coverage,folders)
    rotation_path=dest/'rotation/viewer.json'
    if rotation_path.is_file():
        rotation=json.loads(rotation_path.read_text());ready={e['caseId'] for e in rotation['entries']}
        data['camera']={k:rotation[k] for k in ['width','height','azimuths','elevations']}
        for e in data['entries']:
            cid=Path(e['result']).parent.name if e.get('result') else None
            if cid in ready:
                e['rotationCase']=cid;e['rotation']='rotation/index.html#'+quote(e['asset']+'::'+e['category'],safe='')
            else:
                e['rotationCase']=None;e['rotation']=None
                if cid is not None:e['image']=None;e['handImage']=None;e['visualPending']=True
        data['coverageNote']+=' 已有旋转视角 '+str(len(ready))+'/'+str(coverage['total_types'])+'，新完成结果可刷新查看。'
        (dest/'index.html').write_text(page.replace('__DATA__',json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<',r'\u003c')))
        atomic_json(dest/'review.json',data)
    counts=Counter(r['status'] for r in rows)
    report={'models':len(coverage['models']),'total_types':coverage['total_types'],'reused_types':coverage['reused_types'],
        'completed_types':len(folders),'pending_types':coverage['total_types']-len(folders),'first_pass_types':first_pass,
        'status_counts':dict(counts),'optimization_complete':(root/'final/plan.json').is_file(),
        'physical_passed':None,'full_task_passed':None}
    atomic_json(root/'coverage_summary.json',report)
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=review/index.html"><a href="review/index.html">当前物体全部握法类别审查</a>')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_all_types/current44_2026-10-16'))
    a=p.parse_args();print(json.dumps(review(a.output),ensure_ascii=False,indent=2))
