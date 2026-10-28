#!/usr/bin/env python3
"""Reconcile full type coverage, static gates, source scales and cached contact audits."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json,sha256
from dexonomy.integrations.bench2dex.current_grasp_types import PARENTS


def summarize(root):
    root=Path(root);plan=json.loads((root/'coverage_plan.json').read_text())
    folders=json.loads((root/'review/case_folders.json').read_text());view=json.loads((root/'review/review.json').read_text())
    displays={(e['asset'],e['category']):e for e in view['entries']}
    old_audits={str(PARENTS[0].resolve()):Path('output/shadow_wuji_v3/contact_region_audit_2026-10-14/cases'),
        str(PARENTS[1].resolve()):Path('output/shadow_wuji_v4/expansion_pilot_2026-10-15/contact_audit/cases')}
    flags=defaultdict(set);rows=[];reasons=Counter();records=set()
    for e in plan['entries']:
        cid=e['case_id'];folder=Path(folders[cid]);r=json.loads((folder/'result.json').read_text())
        if e['kind']=='new':audit=root/'contact_audit/cases'/(cid+'.json')
        else:audit=old_audits[str(folder.parent.parent.resolve())]/(folder.name+'.json')
        d=json.loads(audit.read_text());pins={p['sha256'] for p in d['inputs']}
        if sha256(folder/'result.json') not in pins or sha256(folder/'postures.npz') not in pins:
            raise ValueError('Contact audit does not match selected posture: '+cid)
        current_flags=set();required_flags=set()
        for region in d['rows']:
            if region['version']=='selected':
                for flag in region['flags']:
                    flags[flag].add(cid);current_flags.add(flag)
                    if region['required'] and region['finger']!='palm':required_flags.add(flag)
        for reason in r['failure_reasons']:reasons[reason]+=1
        selection=r['source_selection'];records.add((e['object'],e['category'],selection['source']['sha256'],selection['source_index']))
        if r['physical_passed'] is not None or r['full_task_passed'] is not None:raise ValueError('Unexpected physical promotion')
        display=displays[e['object'],e['category']]
        rows.append({'case_id':cid,'object':e['object'],'category':e['category'],'kind':e['kind'],'status':r['status'],
            'failure_reasons':r['failure_reasons'],'contact_flags':sorted(current_flags),'required_contact_flags':sorted(required_flags),
            'required_source_patch_displaced':'source_patch_displaced' in required_flags,'source_extents_mm':display.get('sourceExtentsMm'),
            'source_reference_ratio':display.get('sourceReferenceRatio'),'result_folder':str(folder),
            'contact_audit':str(audit),'object_mass_estimate_kg':d['gravity_readiness']['object_mass_kg']})
    if len(rows)!=plan['total_types']:raise ValueError('Incomplete category coverage')
    models=[]
    for name in plan['models']:
        items=[r for r in rows if r['object']==name]
        models.append({'object':name,'available_types':len(items),'static_candidates':sum(r['status']=='kinematic_candidate' for r in items),
            'rejected':sum(r['status']=='kinematic_rejected' for r in items),'contact_flagged':sum(bool(r['contact_flags']) for r in items)})
    summary={'models':len(models),'taxonomy_categories':len({r['category'] for r in rows}),
        'available_model_category_pairs':plan['total_types'],'generated_model_category_pairs':len(rows),
        'status_counts':dict(Counter(r['status'] for r in rows)),
        'reused_types':plan['reused_types'],'new_or_retried_types':plan['new_types'],
        'static_candidates_with_required_patch_drift':sum(r['status']=='kinematic_candidate' and r['required_source_patch_displaced'] for r in rows),
        'selected_source_records':len(records),'three_phase_postures':3*len(rows),
        'contact_cases_by_flag':{k:len(v) for k,v in flags.items()},'failure_reason_observations':dict(reasons),
        'models_with_all_types_static_passed':sum(m['static_candidates']==m['available_types'] for m in models),
        'models_with_at_least_one_static_candidate':sum(m['static_candidates']>0 for m in models),
        'models_summary':models,'cases':rows,'physical_passed':None,'full_task_passed':None,
        'limitations':['One representative per available category; not all 55235 source rows',
            'Source object scales may differ between categories; actual extents are recorded',
            'Contact flags overlap and are geometric diagnostics, not physical failure labels',
            'No new objects introduced; static coverage does not certify gravity or task success']}
    atomic_json(root/'results.json',summary)
    md=['# 当前 44 个物体的全部握法类别结果','',
        f"模型 {len(models)}；握法大类 {summary['taxonomy_categories']}；类别组合 {len(rows)}/{plan['total_types']}；三阶段姿态 {3*len(rows)}。",'',
        f"静态状态：{summary['status_counts']}。复用 {plan['reused_types']} 类，新做/重试 {plan['new_types']} 类。",'',
        '每类一个代表姿态；来源尺度可能不同。接触诊断另列，尚无本批动力学或完整任务成功标签。','',
        '| 模型 | 已有类别 | 静态候选 | 待修正 | 有接触诊断标记 |','| --- | ---: | ---: | ---: | ---: |']
    for m in models:md.append(f"| {m['object']} | {m['available_types']} | {m['static_candidates']} | {m['rejected']} | {m['contact_flagged']} |")
    md+=['','## 接触诊断（类型重叠）','']
    for flag,names in sorted(flags.items()):md.append(f'- {flag}：{len(names)} 个类别组合。')
    (root/'results.md').write_text('\n'.join(md)+'\n')
    return {k:v for k,v in summary.items() if k not in ['cases','models_summary','limitations','failure_reason_observations']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_all_types/current44_2026-10-16'))
    p.add_argument('--wait',action='store_true');a=p.parse_args()
    if a.wait:
        while True:
            f=a.output/'progress.json'
            if f.is_file() and json.loads(f.read_text()).get('stage')=='complete':break
            time.sleep(15)
    print(json.dumps(summarize(a.output),ensure_ascii=False,indent=2),flush=True)
