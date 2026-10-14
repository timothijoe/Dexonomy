#!/usr/bin/env python3
"""Publish contact diagnostics and representative repair/hold comparisons."""
from collections import Counter
import csv
import html
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json

LABELS={'source_edge_not_preserved':'原边缘接触未保留','source_patch_displaced':'原表面区域偏离',
        'touching_another_patch':'仍碰物体但接触位置改变','contact_segment_substitution':'指段接触替换',
        'finger_contact_lost':'手指/掌心接近丢失','deep_penetration':'深穿透'}


def build():
    root=Path('output/shadow_wuji_v3/contact_region_audit_2026-10-14')
    reports=[json.loads(p.read_text()) for p in sorted((root/'cases').glob('*.json'))]
    if len(reports)!=172:raise ValueError('Full contact audit required')
    rows=[];summary={}
    for flag in LABELS:
        old={r['case_id'] for r in reports if any(x['version']=='v2' and flag in x['flags'] for x in r['rows'])}
        new={r['case_id'] for r in reports if any(x['version']=='selected' and flag in x['flags'] for x in r['rows'])}
        summary[flag]={'v2_cases':len(old),'selected_cases':len(new),
                       'selected_static_candidates':sum(r['case_id'] in new and r['original_status']=='kinematic_candidate' for r in reports),
                       'introduced_vs_v2':sorted(new-old),'cleared_vs_v2':sorted(old-new)}
    for r in reports:
        for x in r['rows']:
            if x['version']!='selected' or not x['flags']:continue
            row={'case_id':r['case_id'],'asset':r['source_selection']['bench_object'],'targets':r['bench_targets'],
                 'category':r['source_selection']['category'],'status':r['original_status'],'phase':x['phase'],'finger':x['finger'],
                 'required_by_v3':bool(x['required'] and x['finger']!='palm'),
                 'source_region':x['source']['hand_body'],'target_region':x['target']['full']['hand_body'],
                 'source_gap_mm':x['source']['gap_m']*1000,'target_full_gap_mm':x['target']['full']['gap_m']*1000,
                 'target_mapped_gap_mm':x['target']['corresponding']['gap_m']*1000,
                 'source_patch_gap_mm':x['target']['anchor']['distance_m']*1000,
                 'source_edge_mm':None if x['source']['edge_distance_m'] is None else x['source']['edge_distance_m']*1000,
                 'target_edge_mm':None if x['target']['edge_distance_m'] is None else x['target']['edge_distance_m']*1000,
                 'flags':x['flags']}
            row['rotation']='../all_matched_thumb_v3_final/rotation/index.html#'+quote(row['asset']+'::'+row['category'],safe='')
            rows.append(row)
    rows.sort(key=lambda x:(not ('source_edge_not_preserved' in x['flags']),x['status']!='kinematic_candidate',not x['required_by_v3'],-x['source_patch_gap_mm']))
    with (root/'observations.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=[k for k in rows[0] if k not in ['targets','flags','rotation']]+['flags']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:writer.writerow({k:';'.join(row[k]) if k=='flags' else row[k] for k in fields})
    gravity=json.loads(Path('output/shadow_wuji_v3/contact_gravity_comparison/summary.json').read_text())
    assert gravity['completed']==24
    record={'cases_audited':172,'source_contacts_reconstructed_geometrically':True,'diagnostic_thresholds_not_adoption_gates':True,
            'flags':summary,'observations':rows,
            'gravity_readiness':{'gravity_disabled_cases':sum(r['gravity_readiness']['gravity_disabled'] for r in reports),
                'zero_actuator_cases':sum(r['gravity_readiness']['target_actuators']==0 for r in reports),
                'normal_only_contact_cases':sum(r['gravity_readiness']['contact_dimensions']==[1] for r in reports)},
            'gravity_test_count':24,'gravity_passed_runs':sum(r['passed'] for r in gravity['rows']),
            'original_poses_unchanged':True,'physical_labels_not_written_to_original_batch':True}
    atomic_json(root/'summary.json',record)
    md=['# 第三版接触与承重诊断','',
        '172 个来源的静态诊断已完成。自动标记是待审查候选，不能一概视为抓取失败。', '',
        '| 类型 | 来源数 | 原静态候选中 | 第二版来源数 |','| --- | ---: | ---: | ---: |']
    for flag,value in summary.items():md.append(f'| {LABELS[flag]} | {value["selected_cases"]} | {value["selected_static_candidates"]} | {value["v2_cases"]} |')
    md+=['','## 悬空承重代表测试','','固定腕、自由物体；原 URDF 力矩限制，PD 20 / 0.2；摩擦 0.5 / 1.0，额外关节压力 0 / 0.025 rad；质量沿用源场景估计。没有桌面闭手、抬升或扰动验证。','',
         '| 来源 | 版本 | 摩擦 | 压力 rad | 保持检查 | 最大滑移 mm | 最大转动 ° |','| --- | --- | ---: | ---: | --- | ---: | ---: |']
    for r in sorted(gravity['rows'],key=lambda r:(r['case_id'],r['version'],r['friction'],r['pressure_rad'])):
        md.append(f'| {r["case_id"]} | {r["version"]} | {r["friction"]} | {r["pressure_rad"]} | {r["passed"]} | {r["max_translation_m"]*1000:.2f} | {r["max_rotation_deg"]:.2f} |')
    (root/'summary.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    def esc(value):return html.escape(str(value))
    headers=['资产/握法','阶段/区域','原静态状态','标记','原间隙 mm','目标间隙 mm','原区域偏离 mm','对照']
    table=[]
    for x in rows:
        cells=[x['asset']+' · '+x['category'],x['phase']+' / '+x['finger'],x['status'],
               '；'.join(LABELS[f] for f in x['flags']),f'{x["source_gap_mm"]:.2f}',f'{x["target_full_gap_mm"]:.2f}',f'{x["source_patch_gap_mm"]:.2f}']
        table.append('<tr data-status="'+x['status']+'" data-edge="'+str('source_edge_not_preserved' in x['flags']).lower()+'">'+''.join('<td>'+esc(v)+'</td>' for v in cells)+f'<td><a href="{esc(x["rotation"])}" target="_blank">旋转查看</a></td></tr>')
    examples=[]
    for cid in ['case_0091__24_Tip_Pinch','case_0038__10_Power_Disk','case_0041__1_Large_Diameter']:
        folder=Path('output/shadow_wuji_v3/contact_repair_pilot')/cid
        r=json.loads((folder/'result.json').read_text())
        path=Path(os.path.relpath(folder/'closeup_yaw135.png',root)).as_posix()
        extra=' · '.join(f'{d["phase"]}：{d["reference_gap_before_m"]*1000:.2f}→{d["reference_gap_after_m"]*1000:.2f} mm' for d in r['details'])
        examples.append(f'<article><h3>{esc(cid)} · {esc(r["finger"])}</h3><p>{esc(extra)}</p><a href="{esc(path)}" target="_blank"><img src="{esc(path)}" loading="lazy"></a></article>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>接触区域与承重诊断</title><style>body{background:#10151e;color:#e7ecf5;font:15px system-ui;margin:24px}a{color:#91d5ff}p{line-height:1.6}select{background:#1c2635;color:#fff;padding:9px;margin-right:12px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #344056;padding:8px;text-align:left}img{max-width:100%}article{border:1px solid #344056;padding:14px;margin:18px 0}.table{overflow:auto}</style>
<h1>第三版接触区域与承重诊断</h1><p>12 个边缘未保留候选，其中 5 个原静态通过。原接触位置重建自所标注区域的几何最近点，并非保存的原承力点。指段映射是两种手结构之间的近似；“掌心”属于原掌心/小指掌骨支持组，不能自动视为必需掌心接触。</p><p>代表接触修复都通过静态检查，但两种杯子在本轮力矩/质量/摩擦设置下仍掉落；碗只在较高摩擦时满足本次悬空保持门槛。结果不是原 Bench2Dex 桌面任务或真机成功。<a href="summary.md">完整统计与 24 次测试结果</a> · <a href="observations.csv">逐项 CSV</a></p>
<select id="status"><option value="">全部原静态状态</option><option value="kinematic_candidate">原静态通过</option><option value="kinematic_rejected">原待修正</option></select><select id="edge"><option value="true">先看边缘候选</option><option value="">全部接触问题</option></select><div class="table"><table><thead>__HEAD__</thead><tbody>__ROWS__</tbody></table></div><h2>代表修复对照：左 Shadow，中原 V3，右接触修复</h2><p>绿色是原物体表面参考位置，红色是对应目标指段最近位置；抓取和收紧各一行。单击放大。</p>__EXAMPLES__<script>function filter(){for(const r of document.querySelectorAll('tbody tr'))r.hidden=(document.getElementById('status').value&&r.dataset.status!==document.getElementById('status').value)||(document.getElementById('edge').value&&r.dataset.edge!==document.getElementById('edge').value)}for(const id of ['status','edge'])document.getElementById(id).onchange=filter;filter()</script></html>'''
    page=page.replace('__HEAD__','<tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr>').replace('__ROWS__',''.join(table)).replace('__EXAMPLES__',''.join(examples))
    (root/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps({'cases':172,'observations':len(rows),'edge_cases':summary['source_edge_not_preserved'],'gravity_passed_runs':record['gravity_passed_runs']},ensure_ascii=False))


if __name__=='__main__':build()
