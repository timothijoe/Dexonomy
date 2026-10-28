#!/usr/bin/env python3
"""Export before/after repair frames and a separate full selected-result review."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import copy
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import quote
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
os.environ.setdefault('MUJOCO_GL','egl')
os.environ.setdefault('LP_NUM_THREADS','1')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256
from dexonomy.integrations.bench2dex.shadow_batch import digest
from dexonomy.integrations.bench2dex.thumb_v3_rotation import export_case,AZIMUTHS,ELEVATIONS
from tools.repair_current_shadow_contacts import verify,DEFAULT


def rotation_page(dest,data):
    dest.mkdir(parents=True,exist_ok=True)
    page=Path('tools/shadow_thumb_v3_rotation.html').read_text().replace('第三版旋转对照','接触区域修复对照')
    page=page.replace('默认同步比较原 Shadow 与最终 Wuji；展开历史对照可查看 V2。',
        '默认比较原 Shadow 与本轮结果；展开对照可查看对应历史版本。')
    page=page.replace('展开后增加 V2 一列','展开后增加对应历史版本一列')
    page=page.replace('姿态与检查状态沿用已完成第三版。','未采纳修复仅供诊断；静态结果不代表承重通过。')
    (dest/'index.html').write_text(page.replace('__ROTATION_DATA__',json.dumps(data,ensure_ascii=False).replace('<',r'\u003c')))
    shutil.copyfile('tools/shadow_thumb_v3_rotation.js',dest/'app.js');atomic_json(dest/'viewer.json',data)


def render(root,workers=8):
    root=Path(root).resolve();summary=json.loads((root/'summary.json').read_text())
    if not summary['finished']:raise ValueError('Finish the numeric batch before rendering')
    plan=json.loads((root/'plan.json').read_text());verify(plan['inputs']);dest=root/'proposals';dest.mkdir(exist_ok=True)
    config={'width':480,'height':360,'quality':76};jobs=[];done=[]
    for row in summary['rows']:
        verify(row['artifacts']);folder=Path(row['proposal_folder']);cid=row['case_id']
        j={'case_id':cid,'result':file_receipt(folder/'result.json'),'postures':file_receipt(folder/'postures.npz')}
        expected=digest({'job':j,'config':config,'renderer':file_receipt(Path('dexonomy/integrations/bench2dex/thumb_v3_rotation.py'))})
        frame=dest/'frames'/cid;receipt=frame/'receipt.json'
        if receipt.is_file():
            saved=json.loads(receipt.read_text())
            if saved['identity']!=expected:raise ValueError('Cached render identity mismatch')
            verify([{'path':str(frame/x['path']),'sha256':x['sha256']} for x in saved['artifacts']]);done.append(saved['row'])
        elif frame.exists():raise ValueError('Inspect incomplete render output: '+str(frame))
        else:jobs.append((j,str(frame),config,expected))
    atomic_json(dest/'plan.json',{'config':config,'cases':len(summary['rows']),
        'inputs':[r for row in summary['rows'] for r in row['artifacts']]})
    def save():atomic_json(dest/'progress.json',{'completed':len(done),'total':len(summary['rows']),'frames':len(done)*360})
    save()
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as ex:
        for f in as_completed([ex.submit(export_case,*j) for j in jobs]):
            r=f.result();done.append(r);save();print(json.dumps({'case_id':r['case_id'],'frames':r['frames']}),flush=True)
    atomic_json(dest/'summary.json',{'cases':len(done),'frames':sum(r['frames'] for r in done),'rows':done})
    verify(plan['inputs']);return build(root)


def link_folder(target,source):
    target.parent.mkdir(parents=True,exist_ok=True);source=Path(source).resolve()
    if target.is_symlink() and target.resolve()!=source:raise ValueError('Unexpected existing link: '+str(target))
    if not target.exists():target.symlink_to(source,target_is_directory=True)
    if not target.is_symlink() or target.resolve()!=source:raise ValueError('Unexpected output: '+str(target))


def publish_selected(root,repair):
    """Publish only recomputed fields; rendering adapters contain old pipeline history."""
    proposal=Path(repair['proposal_folder']);dest=root/'selected/samples'/repair['case_id']
    dest.mkdir(parents=True,exist_ok=True)
    adapter=json.loads((proposal/'result.json').read_text())
    keys=['source_selection','bench_targets','joint_names','baseline_result','config','calibration','bend_calibration',
        'selected_quality','selected_natural','physical_passed','full_task_passed']
    report={k:adapter[k] for k in keys}
    report.update(schema_version='current_contact_repair_selected_v1',case_id=repair['case_id'],status='kinematic_candidate',
        selected_version='contact_repair',failure_reasons=[],
        comparison_roles={'source_qpos':'Shadow source','wuji_v2_qpos':'pre-repair selected Wuji; historical key',
            'wuji_selected_qpos':'adopted contact repair'},
        pipeline_baseline_note='baseline_result retains the original V2 provenance chain for scene/model loading',
        comparison_baseline=file_receipt(Path(repair['baseline_folder'])/'result.json'),
        repair_report=file_receipt(proposal.parent/'result.json'),fresh_audit=file_receipt(Path(repair['selected_audit'])),
        static_adoption=repair['audit_gate'],
        limitations=['Only geometry/naturalness/contact checks passed; no physical success claim',
            'Source patches reconstructed from geometry; morphology mapping remains approximate'])
    atomic_json(dest/'result.json',report)
    shutil.copyfile(proposal/'postures.npz',dest/'postures.npz')
    return dest


def build(root):
    root=Path(root).resolve();plan=json.loads((root/'plan.json').read_text());base=Path(plan['base'])
    summary=json.loads((root/'summary.json').read_text());data=json.loads((base/'review/review.json').read_text())
    repairs={r['case_id']:r for r in summary['rows']};source_cases={r['case_id']:r for r in json.loads((base/'results.json').read_text())['cases']}
    dest=root/'review';dest.mkdir(exist_ok=True);proposal_entries=[];selected_entries=[];folders={}
    fields=['asset','assetLabel','category','categoryLabel','status','versionLabel','selectedVersion','source','matchLabel','physicalPassed']
    grid={'scope':'full','width':480,'height':360,'azimuths':list(AZIMUTHS),'elevations':list(ELEVATIONS)}
    for e in data['entries']:
        cid=Path(e['result']).parent.name;old=copy.deepcopy(e);repair=repairs.get(cid)
        if repair:
            proposal_entries.append({k:e[k] for k in fields}|{'caseId':cid,'entryId':e['asset']+'::'+e['category'],
                'status':'kinematic_candidate' if repair['adopted'] else 'kinematic_rejected',
                'selectedVersion':'contact_repair' if repair['adopted'] else 'repair_rejected',
                'selectedLabel':'接触修复（已采纳）' if repair['adopted'] else '未采纳修复提案（仅诊断）',
                'versionLabel':'已采纳，原文件保留' if repair['adopted'] else '提案未采纳，最终保留原版'})
            link_folder(dest/'repair_proposals/frames'/cid,root/'proposals/frames'/cid)
        accepted=bool(repair and repair['adopted']);folder=str(publish_selected(root,repair)) if accepted else source_cases[cid]['result_folder']
        folders[cid]=folder;link_folder(dest/'samples'/cid,folder)
        frames=root/'proposals/frames'/cid if accepted else base/'review/rotation/frames'/cid
        link_folder(dest/'rotation/frames'/cid,frames)
        # Old trial/image relative paths resolve through the new local sample links.
        for key in ['image','handImage','proposal','primaryTrial','repairTrial']:e[key]=None
        e['contactAudit']=os.path.relpath((Path(repair['selected_audit']) if repair else Path(source_cases[cid]['contact_audit'])).resolve(),dest)
        if accepted:
            r=json.loads((Path(folder)/'result.json').read_text());g,n=r['selected_quality'],r['selected_natural']
            a=json.loads(Path(repair['selected_audit']).read_text())
            e.update(selectedVersion='contact_repair',versionLabel='采用接触修复；原版保留',selectedLabel='最终 Wuji（接触修复）',
                baselineLabel='修复前 Wuji',shape=g['phases']['grasp']['mean_shape_error'],transition=max(g['transition_errors']),
                penetration=1000*max(max(v['max_hand_object_penetration_m'],v['max_self_penetration_m']) for v in g['phases'].values()),
                maxOrientedAngle=max(max(v['oriented_straight180_deg']) for v in n['phases'].values()),
                maxCombinedBend=max(v['combined_bend_deg'] for v in n['phases'].values()),
                maxBoneError=max(max(v['bone_angle_error_deg']) for v in n['phases'].values()),
                maxPadError=max(v['pad_angle_error_deg'] for v in n['phases'].values()),
                contactFlags=sorted({f for row in a['rows'] if row['version']=='selected' for f in row['flags']}),
                requiredPatchDrift=False,reasons=[],attemptCount=1,terminationLabel='修复通过复审')
            prior=json.loads((Path(repair['baseline_folder'])/'result.json').read_text())['selected_natural']
            for pi,p in enumerate(['pregrasp','grasp','squeeze']):
                e['phaseAngles'][pi]['before']=prior['phases'][p]['oriented_straight180_deg']
                e['phaseAngles'][pi]['after']=n['phases'][p]['oriented_straight180_deg']
        if repair:
            e['repairReview']='repair_proposals/index.html#'+quote(e['asset']+'::'+e['category'],safe='')
        selected_entries.append({k:e[k] for k in fields}|{'caseId':cid,'entryId':e['asset']+'::'+e['category'],
            'selectedLabel':e.get('selectedLabel'),'baselineLabel':e.get('baselineLabel','历史 V2')})
    remaining=sum(e['status']=='kinematic_candidate' and e['requiredPatchDrift'] for e in data['entries'])
    data.pop('batchProgressScript',None);data['historyLabel']='显示修复前／历史对照'
    data['contactSummary']=f"本轮采纳 {summary['adopted']} 个接触修复；仍有 {remaining} 个静态候选存在必需手指原区域偏移。"
    data['coverageNote']='44 模型、1164 个类别代表；采纳结果已复审。未采纳提案在单独对照页，最终保留原版。动力学未验证。'
    page=Path('tools/shadow_thumb_v3_review.html').read_text().replace('最终姿态审查','接触修复后的当前握法')
    page=page.replace('显示历史对照（V2）','显示修复前／历史对照').replace('历史 V2 / 最终 Wuji','对应历史版本 / 最终 Wuji')
    script=Path('tools/shadow_thumb_v3_review.js').read_text()
    script=script.replace("if(e.rotation)links.append", "if(e.repairReview)links.append(link('修复前后与未采纳提案',e.repairReview));if(e.rotation)links.append")
    page=page.replace('__REVIEW_SCRIPT__',script)
    (dest/'index.html').write_text(page.replace('__DATA__',json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<',r'\u003c')))
    atomic_json(dest/'review.json',data);atomic_json(dest/'case_folders.json',folders)
    rotation_page(dest/'rotation',grid|{'caseCount':len(selected_entries),'entries':selected_entries,'back':'../index.html',
        'historyLabel':'显示修复前／历史对照'})
    proposals=grid|{'caseCount':len(proposal_entries),'entries':proposal_entries,'back':'../index.html',
        'historyLabel':'显示修复前对照','baselineLabel':'修复前 Wuji'}
    rotation_page(root/'proposals',proposals);rotation_page(dest/'repair_proposals',proposals)
    atomic_json(root/'selection_summary.json',{'models':44,'types':len(data['entries']),
        'static_candidates':data['candidateEntries'],'static_rejected':data['rejectedEntries'],
        'contact_repairs_adopted':summary['adopted'],'remaining_required_patch_drift':remaining,
        'physical_passed':None,'full_task_passed':None,'selected_folders':folders})
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=review/index.html"><a href="review/index.html">接触修复后完整审查</a>')
    return {'adopted':summary['adopted'],'remaining_required_patch_drift':remaining,'entries':len(data['entries'])}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--workers',type=int,default=8,choices=range(1,9));p.add_argument('--build-only',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.output) if a.build_only else render(a.output,a.workers),ensure_ascii=False))
