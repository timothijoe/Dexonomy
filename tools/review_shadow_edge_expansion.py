#!/usr/bin/env python3
"""Summarize edge trials and a bounded native-model expansion without promoting labels."""
from html import escape
import json
from pathlib import Path
import sys
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.asset_matching import object_tokens
from dexonomy.integrations.bench2dex.common import atomic_json


def build(root=Path('output/shadow_wuji_v4')):
    inventory=json.loads((root/'expansion_inventory_2026-10-15/inventory.json').read_text())
    edge=root/'edge_repair_2026-10-15';expansion=root/'expansion_pilot_2026-10-15'
    edge_audit=json.loads((edge/'edge_shift_audit.json').read_text())
    repairs=[json.loads(p.read_text()) for p in sorted((edge/'samples').glob('*/result.json'))]
    gravity=json.loads((edge/'gravity/summary.json').read_text())
    plan=json.loads((expansion/'final/plan.json').read_text());summary=json.loads((expansion/'final/summary.json').read_text())
    by_case={r['case_id']:r for r in summary['results']};model_rows=[]
    for a in plan['assets']:
        model_rows.append({'model':a['dexonomy_object'],'family':a['family'],'outputs':len(a['entries']),
            'static_candidates':sum(by_case[e['case_id']]['status']=='kinematic_candidate' for e in a['entries'])})
    selected={p['object'] for p in inventory['pilot']};queues={}
    for family in ['can','bottle','box','mug','bowl']:
        queues[family]=[o for o in inventory['objects'] if not o['already_mapped'] and o['object'] not in selected and family in object_tokens(o['object']) and len(o['categories'])>=3]
    next_models=[]
    for i in range(4):
        for family,objects in queues.items():
            if i<len(objects):next_models.append({'model':objects[i]['object'],'family':family,'dataset':objects[i]['dataset'],
                'available_categories':objects[i]['categories'],'status':'planned_only_scene_scale_and_quality_not_validated'})
    atomic_json(root/'next_20_model_candidates.json',{'models':next_models,'scope':'20 proposed source models; no new transfer run or Bench2Dex identity claim'})
    report={'edge_audit_cases':edge_audit['cases'],'edge_audit_candidate_cases':edge_audit['candidate_cases'],
        'edge_audit_observations':len(edge_audit['rows']),'edge_trials':len(repairs),
        'edge_static_proposals_passed':sum(r['static_proposal_passed'] for r in repairs),
        'hold_conditions':len(gravity['rows']),'hold_conditions_passed':sum(r['passed'] for r in gravity['rows']),
        'installed_meshes_with_shadow':inventory['objects_with_shadow'],'previous_source_meshes':inventory['already_mapped_source_meshes'],
        'new_available_source_meshes':inventory['new_objects_with_shadow'],'models':model_rows,
        'new_mapping_static_candidates':summary['status_counts'].get('kinematic_candidate',0),
        'new_mapping_rejected':summary['status_counts'].get('kinematic_rejected',0),'new_mapping_physical_passed':None,
        'next_models_planned':len(next_models)}
    atomic_json(root/'summary_2026-10-15.json',report)
    md=['# 边缘修复与更多模型映射结果','',
        f"原批次：{edge_audit['cases']} 个来源出现内侧→边缘漂移候选，其中 {edge_audit['candidate_cases']} 个为原静态候选；共 {len(edge_audit['rows'])} 条阶段/手指观测。",'',
        '| 修复来源 | 阶段/区域 | 原区域偏离 mm | 修复后 mm | 目标最近点距边缘 mm | 采用状态 |',
        '| --- | --- | ---: | ---: | --- | --- |']
    for r in repairs:
        for d in r['details']:
            if not d['focus']:continue
            before=d['target_edge_before_m'];after=d['target_edge_after_m']
            edge_text=f'{before*1000:.2f} → {after*1000:.2f}' if before is not None and after is not None else '—'
            md.append(f"| {r['case_id']} | {d['phase']} / {d['finger']} | {d['reference_gap_before_m']*1000:.2f} | {d['reference_gap_after_m']*1000:.2f} | {edge_text} | {'静态合格提案' if r['static_proposal_passed'] else '提案未通过，保留原版'} |")
    md+=['',f"两例静态合格提案与原版共 {len(gravity['rows'])} 次原力矩重力对照，全部未通过；不是最终抓取成功。",'',
        '| 新来源模型 | 类别 | 输出握法 | 静态候选 |','| --- | --- | ---: | ---: |']
    for r in model_rows:md.append(f"| {r['model']} | {r['family']} | {r['outputs']} | {r['static_candidates']} |")
    md+=['',f"本地 {inventory['objects_with_shadow']} 个带 Shadow 来源的网格，原已使用 {inventory['already_mapped_source_meshes']} 个不同来源；新增可选来源 {inventory['new_objects_with_shadow']} 个。资源存在不代表场景/尺寸、接触或物理检查通过。",'',
        '新模型没有减少 Bench2Dex 18 个未匹配资产缺口；接触审计和实际承重仍需逐项检查。',
        '下一批只准备了 20 个模型候选清单，尚未运行；原 V3 姿态及标签均未覆盖。']
    (root/'summary_2026-10-15.md').write_text('\n'.join(md)+'\n')
    table=[]
    for r in repairs:
        ds=[d for d in r['details'] if d['focus'] and d['phase']=='squeeze']
        values='；'.join(f"{d['finger']}: {d['reference_gap_before_m']*1000:.2f} → {d['reference_gap_after_m']*1000:.2f} mm" for d in ds)
        base=json.loads((Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/samples')/r['case_id']/'result.json').read_text())['source_selection']
        href='edge_repair_2026-10-15/rotation/index.html#'+quote(base['bench_object']+'::'+base['category'],safe='')
        table.append(f"<tr><td>{escape(base['bench_object'])}</td><td>{escape(values)}</td><td>{'静态合格提案；重力未通过' if r['static_proposal_passed'] else '提案未通过，保留原版'}</td><td><a href='{href}'>旋转查看</a></td></tr>")
    models=''.join(f"<tr><td>{escape(r['model'])}</td><td>{r['family']}</td><td>{r['outputs']}</td><td>{r['static_candidates']}</td></tr>" for r in model_rows)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>边缘修复与新增模型映射</title><style>body{font:16px system-ui;margin:28px;background:#10151e;color:#e7ecf5;line-height:1.65}a{color:#91d5ff}table{border-collapse:collapse;width:100%;margin:18px 0}td,th{border:1px solid #42516b;padding:10px;text-align:left;overflow-wrap:anywhere}p{max-width:1000px}.table{overflow:auto}h1{font-size:26px}</style><h1>边缘接触修复与新增模型映射</h1><p>默认两列比较，历史基线按需展开；旋转页顶部直接提供 Yaw / Pitch / Roll。下列合格项指静态检查，实际承重单独判定。</p><h2>边缘修复</h2><p>25 条观测来自 15 个来源，其中 10 个为原静态候选。四例修复有两例通过静态检查，八次重力对照全部未通过。模型估计质量约 0.98 / 3.61 kg，来源尺度尚未按真实目标校准。原 V3 未覆盖。</p><div class="table"><table><tr><th>物体</th><th>收紧原区域偏离：前 → 后</th><th>状态</th><th>查看</th></tr>__REPAIRS__</table></div><h2>更多模型</h2><p>三个新来源模型各三种握法，七条静态候选、两条待修正；这些新模型未做重力验证。</p><p><a href="expansion_pilot_2026-10-15/final/index.html">新增模型总览（含三轴控件）</a> · <a href="expansion_pilot_2026-10-15/final/rotation/index.html">新增模型旋转页</a></p><div class="table"><table><tr><th>模型</th><th>类别</th><th>输出握法</th><th>静态候选</th></tr>__MODELS__</table></div><p>本地 5699 个带 Shadow 来源的网格，原批次用了 41 个不同来源；其余 5658 个是资源候选，尚不能直接算作迁移成功。新来源不代表补齐 Bench2Dex 原模型缺口。</p><p><a href="summary_2026-10-15.md">完整数值记录</a> · <a href="next_20_model_candidates.json">下一批 20 个模型候选（尚未运行）</a></p></html>'''
    (root/'index.html').write_text(page.replace('__REPAIRS__',''.join(table)).replace('__MODELS__',models))
    return report


if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False,indent=2))
