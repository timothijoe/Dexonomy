#!/usr/bin/env python3
"""Export rotatable source / original V3 / edge-repair proposal comparisons."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sys
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
os.environ.setdefault('MUJOCO_GL','egl')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256
from dexonomy.integrations.bench2dex.shadow_batch import digest
from dexonomy.integrations.bench2dex.thumb_v3_rotation import export_case,AZIMUTHS,ELEVATIONS
from tools.review_shadow_wuji_batch import ASSET_NAMES,CATEGORY_NAMES


def build(batch,repair,output,workers=2):
    batch,repair,output=map(Path,(batch,repair,output))
    if output.exists():raise ValueError('Use fresh comparison output')
    output.mkdir(parents=True);jobs=[];entries=[];inputs=[]
    gravity=json.loads((repair/'gravity/summary.json').read_text()) if (repair/'gravity/summary.json').is_file() else None
    for path in sorted((repair/'samples').glob('*/result.json')):
        report=json.loads(path.read_text());cid=report['case_id'];base=batch/'samples'/cid
        original=json.loads((base/'result.json').read_text());selection=original['source_selection']
        folder=output/'inputs'/cid;folder.mkdir(parents=True)
        with np.load(path.parent/'postures.npz',allow_pickle=False) as z:
            np.savez_compressed(folder/'postures.npz',source_qpos=z['source_qpos'],wuji_v2_qpos=z['baseline_qpos'],wuji_selected_qpos=z['proposed_qpos'])
        original['status']='kinematic_candidate' if report['static_proposal_passed'] else 'kinematic_rejected'
        original['selected_version']='edge_repair' if report['static_proposal_passed'] else 'v3_rejected'
        atomic_json(folder/'result.json',original)
        job={'case_id':cid,'result':file_receipt(folder/'result.json'),'postures':file_receipt(folder/'postures.npz')}
        jobs.append(job);inputs.extend([file_receipt(path),file_receipt(path.parent/'postures.npz'),file_receipt(base/'postures.npz'),file_receipt(base/'result.json')])
        name=selection['bench_object'];category=selection['category'];prefix=name.split('_')[0].split('-')[0]
        tested=[r for r in gravity['rows'] if r['case_id']==cid and r['version']=='repaired'] if gravity else []
        entries.append({'asset':name,'assetLabel':ASSET_NAMES.get(prefix,name)+' · '+name,'category':category,
            'categoryLabel':CATEGORY_NAMES.get(category.split('_')[0],category)+' · '+category,
            'entryId':name+'::'+category,'caseId':cid,'source':selection['dexonomy_object'],
            'matchLabel':'原 Dexonomy 来源几何；接触参考为几何重建','status':original['status'],
            'selectedVersion':original['selected_version'],
            'selectedLabel':'接触修复提案（静态合格）' if report['static_proposal_passed'] else '修复提案（未通过，原 V3 保留）',
            'versionLabel':'仅提案；原 V3 未替换','physicalPassed':any(r['passed'] for r in tested) if tested else None})
    config={'width':480,'height':360,'quality':76}
    plan={'jobs':jobs,'inputs':inputs,'renderer':file_receipt(Path('dexonomy/integrations/bench2dex/thumb_v3_rotation.py')),'config':config}
    plan['identity']=digest(plan);atomic_json(output/'plan.json',plan);rows=[]
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as ex:
        futures=[ex.submit(export_case,j,str(output/'frames'/j['case_id']),config,digest({'plan':plan['identity'],'case':j['case_id']})) for j in jobs]
        for f in as_completed(futures):
            r=f.result();rows.append(r);print(json.dumps({'case_id':r['case_id'],'frames':r['frames']}),flush=True)
    for p in inputs:
        if sha256(p['path'])!=p['sha256']:raise ValueError('Original comparison input changed')
    data={'caseCount':len(jobs),'scope':'pilot','entries':entries,**config,'azimuths':list(AZIMUTHS),'elevations':list(ELEVATIONS),
        'baselineLabel':'原 V3 基线','historyLabel':'显示修复前对照（原 V3）',
        'back':Path(os.path.relpath(batch/'index.html',output)).as_posix()}
    template=Path('tools/shadow_thumb_v3_rotation.html').read_text().replace('第三版旋转对照','边缘接触修复对照')
    template=template.replace('默认同步比较原 Shadow 与最终 Wuji；展开历史对照可查看 V2。','默认比较原 Shadow 与修复提案；展开查看修复前 V3。未通过提案仅供诊断，原 V3 未被替换。')
    template=template.replace('显示历史对照（V2）','显示修复前对照（原 V3）').replace('展开后增加 V2 一列','展开后增加原 V3 一列')
    template=template.replace('姿态与检查状态沿用已完成第三版。','状态按本轮修复检查；重力结果仅为声明参数下的悬空保持诊断。')
    (output/'index.html').write_text(template.replace('__ROTATION_DATA__',json.dumps(data,ensure_ascii=False).replace('<',r'\u003c')))
    shutil.copyfile('tools/shadow_thumb_v3_rotation.js',output/'app.js');atomic_json(output/'viewer.json',data)
    atomic_json(output/'summary.json',{'completed':len(rows),'frames':sum(r['frames'] for r in rows),'rows':rows})
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    p.add_argument('--repair',type=Path,default=Path('output/shadow_wuji_v4/edge_repair_2026-10-15'))
    p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_v4/edge_repair_2026-10-15/rotation'))
    p.add_argument('--workers',type=int,default=2,choices=range(1,5));a=p.parse_args();build(a.batch,a.repair,a.output,a.workers)
