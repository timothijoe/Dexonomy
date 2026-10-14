#!/usr/bin/env python3
"""Offline Source / selected V2 / constrained V3 review with explicit rejects."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json
from tools.review_shadow_wuji_batch import PAGE, ASSET_NAMES, CATEGORY_NAMES, reason_label


def policy_reason(reason):
    labels = {'thumb_reverse_bend': '拇指末端反折', 'thumb_bend_upper': '拇指弯曲超过范围',
              'thumb_combined_bend': '拇指组合弯曲超过范围',
              'thumb_bone_direction': '拇指指段方向与来源差异过大',
              'thumb_pad_direction': '参考指腹朝向与来源差异过大'}
    for phase, label in [('pregrasp', '预抓取'), ('grasp', '抓取'), ('squeeze', '收紧')]:
        prefix = phase + '_'
        if reason.startswith(prefix) and reason[len(prefix):] in labels:
            return label + '：' + labels[reason[len(prefix):]]
    return reason_label(reason)


def build(root):
    root = Path(root); plan = json.loads((root / 'plan.json').read_text())
    summary = json.loads((root / 'summary.json').read_text())
    rows = {r['case_id']: r for r in summary['results']}
    jobs = {j['case_id']: j for j in plan['jobs']}
    entries = []
    match_labels = {'same_ycb_id_and_name': '同 YCB 编号/名称，网格等价待核查',
                    'same_named_category': '同名类别候选', 'similar_geometry_family': '相近几何家族候选'}
    version_labels = {'v3': '采用第三版', 'v3_rejected': '第三版待修正', 'v2_retained': '保留已通过新检查的旧版'}
    md = ['# 拇指第三版逐目标对照', '',
          '| 资产 | 握法 | 选用版本 | 几何检查 | 弯曲与朝向检查 | 状态 |', '| --- | --- | --- | --- | --- | --- |']
    for asset in plan['assets']:
        for grasp in asset['entries']:
            cid = grasp['case_id']; row = rows.get(cid, {}); job = jobs[cid]
            folder = root / 'samples' / cid
            r = json.loads((folder / 'result.json').read_text()) if (folder / 'result.json').is_file() else None
            def relative(name):
                p = folder / name
                return p.relative_to(root).as_posix() if p.is_file() else None
            geometry = r['selected_quality'] if r else None
            natural = r['selected_natural'] if r else None
            version = row.get('selected_version', 'pending')
            name = asset['bench_object']; prefix = name.split('_')[0].split('-')[0]
            entry = {'asset': name, 'assetLabel': ASSET_NAMES.get(prefix, name) + ' · ' + name,
                     'category': grasp['category'],
                     'categoryLabel': CATEGORY_NAMES.get(grasp['category'].split('_')[0], grasp['category']) + ' · ' + grasp['category'],
                     'source': job['selection']['dexonomy_object'], 'status': row.get('status', 'pending'),
                     'matchLabel': match_labels.get(asset['match_level'], asset['match_level']), 'image': relative('comparison.png'),
                     'handImage': relative('hand_only/comparison.png'), 'result': relative('result.json') or relative('failure.json'),
                     'postures': relative('postures.npz'), 'proposal': relative('proposal/comparison.png'),
                     'primaryTrial': relative('primary_trial/comparison.png'),
                     'repairTrial': relative('geometry_repair_trial/comparison.png'),
                     'attemptCount': len(r.get('refinement_attempts', [])) if r else 0,
                     'shape': geometry['phases']['grasp']['mean_shape_error'] if geometry else None,
                     'transition': max(geometry['transition_errors']) if geometry else None,
                     'penetration': max(max(v['max_hand_object_penetration_m'], v['max_self_penetration_m']) for v in geometry['phases'].values()) * 1000 if geometry else None,
                     'terminationLabel': {'converged': '收敛', 'evaluation_limit': '达到迭代预算', 'time_budget_checkpoint': '时间预算检查点'}.get(row.get('solver_termination'), '—'),
                     'reasons': [policy_reason(v) for v in row.get('failure_reasons', [])], 'error': row.get('error'),
                     'selectedVersion': version, 'versionLabel': version_labels.get(version, '处理中'),
                     'geometryPassed': geometry['passed'] if geometry else None,
                     'policyPassed': natural['passed'] if natural else None,
                     'maxOrientedAngle': max(max(v['oriented_straight180_deg']) for v in natural['phases'].values()) if natural else None,
                     'maxCombinedBend': max(v['combined_bend_deg'] for v in natural['phases'].values()) if natural else None,
                     'maxBoneError': max(max(v['bone_angle_error_deg']) for v in natural['phases'].values()) if natural else None,
                     'maxPadError': max(v['pad_angle_error_deg'] for v in natural['phases'].values()) if natural else None}
            entry['phaseAngles'] = [{'phase': {'pregrasp': '预抓取', 'grasp': '抓取', 'squeeze': '收紧'}[p],
                                     'before': r['baseline_natural']['phases'][p]['oriented_straight180_deg'],
                                     'after': natural['phases'][p]['oriented_straight180_deg']}
                                    for p in ['pregrasp', 'grasp', 'squeeze']] if r else []
            entries.append(entry)
            md.append(f'| {name} | {grasp["category"]} | {version} | {entry["geometryPassed"]} | {entry["policyPassed"]} | {entry["status"]} |')
    data = {'assetCount': plan['asset_count'], 'uniqueCases': plan['unique_source_cases'],
            'completedCases': summary['completed_source_cases'],
            'candidateEntries': sum(e['status'] == 'kinematic_candidate' for e in entries),
            'rejectedEntries': sum(e['status'] == 'kinematic_rejected' for e in entries),
            'deferredCount': len(plan['deferred_assets']), 'entries': entries}
    page = PAGE.replace('全资产姿态审查', '拇指 V2 / V3 对照')
    page = page.replace('顶行 Shadow 来源，中行 Wuji 迁移初值，底行 Wuji 联合优化',
                        '顶行 Shadow 来源，中行第二版最终选用姿态，底行本次选用姿态')
    page = page.replace('当前使用 Dexonomy 来源物体与尺度，目标是 Wuji 一代右手。',
                        '末端两关节禁止反折，并限制组合弯曲。通过表示原静态几何与新增弯曲/朝向检查均满足；新旧均不合格则明确标为待修正。该范围是机器人迁移约定，不是人体活动范围认证。')
    page = page.replace('手型和阶段动作误差按指长归一化，无单位；穿透使用毫米。',
                        '末端有向夹角按伸直 180° 计算；两关节组合弯曲上限 130°。指段及指腹方向误差上限 90°，指腹为几何代理。手型/动作误差无单位；穿透为毫米。')
    page = page.replace('<input id="search"', '<select id="version"><option value="">全部选用版本</option><option value="v3">采用第三版</option><option value="v2_retained">保留合格旧版</option><option value="v3_rejected">第三版待修正</option></select><input id="search"')
    page = page.replace("const entries=data.entries.filter(e=>", "const entries=data.entries.filter(e=>(!$('version').value||e.selectedVersion===$('version').value)&&")
    page = page.replace("['asset','status','search']", "['asset','status','version','search']")
    page = page.replace("title.append(elem('span',labels[e.status],`badge ${e.status}`));", "title.append(elem('span',labels[e.status],`badge ${e.status}`));title.append(elem('span',' · '+e.versionLabel));")
    page = page.replace("if(e.shape!==null){", "if(e.maxOrientedAngle!==null){const n=elem('div',undefined,'metrics');n.append(elem('div','末端最大有向夹角：'+e.maxOrientedAngle.toFixed(1)+'°'),elem('div','最大组合弯曲：'+e.maxCombinedBend.toFixed(1)+'°'),elem('div','最大指段方向误差：'+e.maxBoneError.toFixed(1)+'°'),elem('div','最大参考指腹方向误差：'+e.maxPadError.toFixed(1)+'°'));d.append(n)}if(e.shape!==null){")
    page = page.replace("const links=elem('div',undefined,'links');", "if(e.phaseAngles.length){const angles=elem('details');angles.append(elem('summary','三阶段夹角：第二版 → 本次选用（伸直 180°）'));for(const p of e.phaseAngles)angles.append(elem('div',p.phase+'：关节3 '+p.before[0].toFixed(1)+'° → '+p.after[0].toFixed(1)+'°；关节4 '+p.before[1].toFixed(1)+'° → '+p.after[1].toFixed(1)+'°'));d.append(angles)}const links=elem('div',undefined,'links');")
    page = page.replace('d.append(links);card.append(d);', "if(e.proposal)links.append(link('未采用的第三版提案',e.proposal));if(e.primaryTrial)links.append(link('首轮结果',e.primaryTrial));if(e.repairTrial)links.append(link('几何修复尝试',e.repairTrial));d.append(links);card.append(d);")
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', r'\u003c')
    (root / 'index.html').write_text(page.replace('__DATA__', payload), encoding='utf-8')
    atomic_json(root / 'review.json', data)
    (root / 'summary.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    args = parser.parse_args(); r = build(args.batch)
    print(json.dumps({k: v for k, v in r.items() if k != 'entries'}, ensure_ascii=False))
