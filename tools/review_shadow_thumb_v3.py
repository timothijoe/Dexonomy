#!/usr/bin/env python3
"""Offline Source / final Wuji review with optional V2 history and explicit rejects."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json
from tools.review_shadow_wuji_batch import ASSET_NAMES, CATEGORY_NAMES, reason_label


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
    rotation_path = root / 'rotation' / 'viewer.json'
    rotation = json.loads(rotation_path.read_text()) if rotation_path.is_file() else None
    rotation_cases = {e['caseId'] for e in rotation['entries']} if rotation else set()
    match_labels = {'same_ycb_id_and_name': '同 YCB 编号/名称，网格等价待核查',
                    'native_dexonomy_model': 'Dexonomy 原模型映射；不代表 Bench2Dex 同模型',
                    'same_named_category': '同名类别候选', 'similar_geometry_family': '相近几何家族候选'}
    version_labels = {'v3': '采用第三版', 'v3_rejected': '第三版待修正', 'v2_retained': '沿用 V2，满足当前静态约束'}
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
            label = {'can':'罐模型','bottle':'瓶模型','box':'盒模型'}.get(asset.get('family'),name) if asset['match_level']=='native_dexonomy_model' else ASSET_NAMES.get(prefix,name)
            entry = {'asset': name, 'assetLabel': label + ' · ' + name,
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
                     'physicalPassed': r.get('physical_passed') if r else None,
                     'maxOrientedAngle': max(max(v['oriented_straight180_deg']) for v in natural['phases'].values()) if natural else None,
                     'maxCombinedBend': max(v['combined_bend_deg'] for v in natural['phases'].values()) if natural else None,
                     'maxBoneError': max(max(v['bone_angle_error_deg']) for v in natural['phases'].values()) if natural else None,
                     'maxPadError': max(v['pad_angle_error_deg'] for v in natural['phases'].values()) if natural else None}
            entry['phaseAngles'] = [{'phase': {'pregrasp': '预抓取', 'grasp': '抓取', 'squeeze': '收紧'}[p],
                                     'before': r['baseline_natural']['phases'][p]['oriented_straight180_deg'],
                                     'after': natural['phases'][p]['oriented_straight180_deg']}
                                    for p in ['pregrasp', 'grasp', 'squeeze']] if r else []
            entry['rotationCase'] = cid if cid in rotation_cases else None
            entry['rotation'] = 'rotation/index.html#' + quote(name + '::' + grasp['category'], safe='') if cid in rotation_cases else None
            entries.append(entry)
            md.append(f'| {name} | {grasp["category"]} | {version} | {entry["geometryPassed"]} | {entry["policyPassed"]} | {entry["status"]} |')
    data = {'assetCount': plan['asset_count'], 'uniqueCases': plan['unique_source_cases'],
            'completedCases': summary['completed_source_cases'],
            'candidateEntries': sum(e['status'] == 'kinematic_candidate' for e in entries),
            'rejectedEntries': sum(e['status'] == 'kinematic_rejected' for e in entries),
            'deferredCount': len(plan['deferred_assets']), 'entries': entries,
            'camera': {k: rotation[k] for k in ['width', 'height', 'azimuths', 'elevations']} if rotation else None}
    page = Path(__file__).with_name('shadow_thumb_v3_review.html').read_text()
    script = Path(__file__).with_name('shadow_thumb_v3_review.js').read_text()
    page = page.replace('__REVIEW_SCRIPT__', script)
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
