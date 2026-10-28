#!/usr/bin/env python3
"""Publish all 1164 selected cases with fresh contact labels and repair metrics."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from dexonomy.integrations.bench2dex.common import atomic_json
from tools.repair_current_shadow_contacts import DEFAULT,verify


def summarize(root):
    root=Path(root);plan=json.loads((root/'plan.json').read_text());verify(plan['inputs'])
    baseline=json.loads((Path(plan['base'])/'results.json').read_text());s=json.loads((root/'summary.json').read_text())
    selected=json.loads((root/'selection_summary.json').read_text());repairs={r['case_id']:r for r in s['rows']}
    before=[];after=[];cases=[];model_counts=Counter()
    for old in baseline['cases']:
        case=copy.deepcopy(old);cid=case['case_id'];repair=repairs.get(cid);case['contact_repair_adopted']=bool(repair and repair['adopted'])
        if case['contact_repair_adopted']:
            case['contact_audit']=repair['selected_audit'];case['result_folder']=selected['selected_folders'][cid]
            audit=json.loads(Path(case['contact_audit']).read_text());rows=[r for r in audit['rows'] if r['version']=='selected']
            case['contact_flags']=sorted({f for r in rows for f in r['flags']})
            case['required_contact_flags']=sorted({f for r in rows if r['required'] and r['finger']!='palm' for f in r['flags']})
            case['required_source_patch_displaced']='source_patch_displaced' in case['required_contact_flags']
            report=json.loads((Path(repair['proposal_folder']).parent/'result.json').read_text())
            for d in report['details']:
                if d['focus']:before.append(d['reference_gap_before_m']);after.append(d['reference_gap_after_m'])
            model_counts[case['object']]+=1
        cases.append(case)
    def stats(values):
        a=1000*np.array(values);return {'median_mm':float(np.median(a)),'mean_mm':float(a.mean()),'max_mm':float(a.max())}
    data={'models':baseline['models'],'model_category_pairs':len(cases),'repair_cases':s['total'],
        'repairs_adopted':s['adopted'],'repair_baselines_retained':s['baseline_retained'],
        'status_counts':dict(Counter(r['status'] for r in cases)),
        'static_candidates_with_required_patch_drift':sum(r['status']=='kinematic_candidate' and r['required_source_patch_displaced'] for r in cases),
        'adopted_focus_references':len(before),'adopted_focus_gap_before':stats(before),'adopted_focus_gap_after':stats(after),
        'models_with_adopted_repairs':len(model_counts),'adopted_repairs_per_model':dict(model_counts),
        'contact_cases_by_flag':dict(Counter(f for r in cases for f in r['contact_flags'])),
        'repair_rejection_reason_observations':dict(Counter(f for r in s['rows'] if not r['adopted'] for f in r['failure_reasons'])),
        'cases':cases,'physical_passed':None,'full_task_passed':None,
        'limitations':['Static contact patch reconstruction; not source contact forces or all source records',
            'Unresolved contact drift retains baseline; original static rejects remain rejected',
            'No batch gravity/close/lift verification; no human-ROM certification']}
    atomic_json(root/'results.json',data)
    md=['# 当前握法接触修复结果','',f"44 模型 / {len(cases)} 个模型×类别代表，静态候选 {data['status_counts']['kinematic_candidate']}、静态拒绝 {data['status_counts']['kinematic_rejected']}。",
        '',f"原 507 个必需手指原区域偏移候选，本轮采纳 {s['adopted']} 个修复，{s['baseline_retained']} 个保留原版。",
        '',f"采纳修复涉及 {len(before)} 个阶段×手指参考，原区域距离中位数 {stats(before)['median_mm']:.3f} → {stats(after)['median_mm']:.3f} mm，修复后最大 {stats(after)['max_mm']:.3f} mm。",
        '',f"仍有 {data['static_candidates_with_required_patch_drift']} 个静态候选存在必需手指原区域偏移；动力学未验证。",
        '', '| 模型 | 采纳修复数 |','| --- | --- |']
    md += [f'| {k} | {v} |' for k,v in model_counts.items()]
    md += ['', '未采纳提案的失败观测可能重叠：','', '| 原因 | 观测数 |','| --- | --- |']
    md += [f'| {k} | {v} |' for k,v in data['repair_rejection_reason_observations'].items()]
    (root/'results.md').write_text('\n'.join(md)+'\n');return {k:v for k,v in data.items() if k!='cases'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=DEFAULT);a=p.parse_args()
    print(json.dumps(summarize(a.output),ensure_ascii=False,indent=2))
