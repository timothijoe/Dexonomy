#!/usr/bin/env python3
"""Verify every V3 artifact and independently measure actual geometric bends."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.integrations.bench2dex.common import atomic_json, sha256
from dexonomy.integrations.bench2dex.shadow_retarget import HandGeometry, PHASES
from dexonomy.integrations.bench2dex.shadow_batch import verify_completed
from dexonomy.integrations.bench2dex.thumb_v3_batch import verify_v3, identity
from tools.audit_shadow_thumb_angles import signed_turns


def audit(root):
    root = Path(root); plan = json.loads((root / 'plan.json').read_text()); verify_v3(plan)
    summary = json.loads((root / 'summary.json').read_text())
    if not summary['all_cases_terminal']: raise ValueError('Batch is incomplete')
    base_v2 = json.loads(Path(plan['baseline_plan']['path']).read_text())
    base_v1 = json.loads(Path(base_v2['baseline_plan']['path']).read_text())
    hand = HandGeometry(MuJoCo_VisEnv(HandCfg(base_v1['inputs']['target_model']['path'], freejoint=True),
                                   vis_mode='collision'), 'wuji')
    rows, before_bends, after_bends, old_scores, new_scores = [], [], [], [], []
    png_count = 0
    primary_plan = json.loads(Path(plan['inputs']['primary_plan']['path']).read_text()) if plan.get('published_comparison') else None
    repair_plan = json.loads(Path(plan['inputs']['repair_plan']['path']).read_text()) if plan.get('published_comparison') else None
    for job in plan['jobs']:
        folder = root / 'samples' / job['case_id']
        row = verify_completed(folder, identity(plan, job))
        if row['status'] == 'error': raise ValueError('Execution error: ' + job['case_id'])
        r = json.loads((folder / 'result.json').read_text())
        if len(r.get('refinement_attempts', [])) == 2:
            assert primary_plan is not None and repair_plan is not None
            for local, parent, attempt in [('primary_trial', primary_plan, r['refinement_attempts'][0]),
                                           ('geometry_repair_trial', repair_plan, r['refinement_attempts'][1])]:
                trial = folder / local
                assert verify_completed(trial, identity(parent, job)) is not None
                if attempt['result'] is not None:
                    assert sha256(trial / 'result.json') == attempt['result']['sha256']
        with np.load(folder / 'postures.npz', allow_pickle=False) as z, np.load(
                Path(job['baseline_folder']) / 'postures.npz', allow_pickle=False) as old:
            np.testing.assert_array_equal(z['source_qpos'], old['source_qpos'])
            np.testing.assert_array_equal(z['wuji_v2_qpos'], old['wuji_selected_qpos'])
            np.testing.assert_array_equal(z['wuji_v1_qpos'], old['wuji_v1_qpos'])
            for key in ['wuji_v1_qpos', 'wuji_v2_qpos', 'wuji_v3_feasible_start_qpos',
                        'wuji_v3_initialized_qpos', 'wuji_v3_proposed_qpos', 'wuji_selected_qpos']:
                q = z[key]
                assert q.shape == (3, 27) and np.isfinite(q).all()
                np.testing.assert_allclose(np.linalg.norm(q[:, 3:7], axis=1), 1, atol=1e-10)
                assert np.all(q[:, 7:] >= hand.limits[:, 0] - 1e-9)
                assert np.all(q[:, 7:] <= hand.limits[:, 1] + 1e-9)
                if key.startswith('wuji_v3') or key == 'wuji_selected_qpos':
                    bends = np.asarray([signed_turns(hand, pose) for pose in q]) * r['bend_calibration']['target']['flexion_sign']
                    assert bends.min() >= -1e-5
                    assert bends.sum(axis=1).max() <= r['bend_calibration']['combined_cap_deg'] + 1e-5
            if r['selected_version'] == 'v2_retained':
                np.testing.assert_array_equal(z['wuji_selected_qpos'], z['wuji_v2_qpos'])
                assert r['baseline_quality']['passed'] and r['baseline_natural']['passed']
            old_turns = np.asarray([signed_turns(hand, q) for q in z['wuji_v2_qpos']])
            new_turns = np.asarray([signed_turns(hand, q) for q in z['wuji_selected_qpos']])
        recorded = np.asarray([r['selected_natural']['phases'][p]['bend_deg'] for p in PHASES])
        np.testing.assert_allclose(recorded, new_turns * r['bend_calibration']['target']['flexion_sign'], atol=1e-5)
        passed = r['selected_quality']['passed'] and r['selected_natural']['passed']
        assert (r['status'] == 'kinematic_candidate') == passed
        if r['selected_version'] == 'v3_rejected': assert not passed
        if r['baseline_quality']['passed'] and r['baseline_natural']['passed']: assert passed
        assert r['physical_passed'] is None and r['full_task_passed'] is None
        before_bends.append(old_turns); after_bends.append(new_turns)
        old_scores.append(np.mean([m['score'] for m in r['baseline_thumb'].values()]))
        new_scores.append(np.mean([m['score'] for m in r['selected_thumb'].values()]))
        for path in folder.rglob('*.png'):
            with Image.open(path) as im: im.verify()
            png_count += 1
        assert (folder / 'comparison.png').is_file() and (folder / 'hand_only/comparison.png').is_file()
        rows.append({'case_id': job['case_id'], 'status': r['status'], 'selected_version': r['selected_version'],
                     'baseline_geometry_passed': r['baseline_quality']['passed'],
                     'baseline_policy_passed': r['baseline_natural']['passed'],
                     'selected_geometry_passed': r['selected_quality']['passed'],
                     'selected_policy_passed': r['selected_natural']['passed'],
                     'failure_reasons': r['failure_reasons'],
                     'score_before': float(old_scores[-1]), 'score_selected': float(new_scores[-1]),
                     'attempt_count': len(r.get('refinement_attempts', [])) or 1,
                     'geometry_repair_selected': r.get('geometry_repair_selected', False),
                     'source_goal_projection_count': r['bend_calibration']['source_goal_projection_count']})
    by_case = {r['case_id']: r for r in rows}
    before, after = np.asarray(before_bends), np.asarray(after_bends)
    report = {'cases_verified': len(rows), 'asset_count': plan['asset_count'], 'coverage_entries': plan['coverage_entries'],
              'status_counts': dict(Counter(r['status'] for r in rows)),
              'selection_counts': dict(Counter(r['selected_version'] for r in rows)),
              'coverage_status_counts': dict(Counter(by_case[e['case_id']]['status'] for a in plan['assets'] for e in a['entries'])),
              'coverage_selection_counts': dict(Counter(by_case[e['case_id']]['selected_version'] for a in plan['assets'] for e in a['entries'])),
              'baseline_policy_passed_cases': sum(r['baseline_policy_passed'] for r in rows),
              'selected_policy_passed_cases': sum(r['selected_policy_passed'] for r in rows),
              'reverse_bend_below_minus5_before_by_phase_j3_j4': (before < -5).sum(axis=0).tolist(),
              'reverse_bend_below_minus5_selected_by_phase_j3_j4': (after < -5).sum(axis=0).tolist(),
              'selected_reverse_bend_count_tolerance_1e_minus5_deg': int((after < -1e-5).sum()),
              'max_combined_selected_bend_deg': float(after.sum(axis=2).max()),
              'max_selected_oriented_straight180_angle_deg': float((180 - after).max()),
              'mean_thumb_score_before': float(np.mean(old_scores)), 'mean_thumb_score_selected': float(np.mean(new_scores)),
              'valid_baseline_regressions': sum(r['baseline_geometry_passed'] and r['baseline_policy_passed'] and r['status'] != 'kinematic_candidate' for r in rows),
              'previous_geometry_candidates_now_rejected': sum(r['baseline_geometry_passed'] and r['status'] == 'kinematic_rejected' for r in rows),
              'source_projection_cases': sum(r['source_goal_projection_count'] > 0 for r in rows),
              'attempt_counts': dict(Counter(r['attempt_count'] for r in rows)),
              'total_batch_attempts': sum(r['attempt_count'] for r in rows),
              'geometry_repair_selected_cases': sum(r['geometry_repair_selected'] for r in rows),
              'assets_with_candidates': sum(any(by_case[e['case_id']]['status'] == 'kinematic_candidate' for e in a['entries']) for a in plan['assets']),
              'assets_with_at_least_three_candidates': sum(sum(by_case[e['case_id']]['status'] == 'kinematic_candidate' for e in a['entries']) >= 3 for a in plan['assets']),
              'assets_without_candidates': [a['bench_object'] for a in plan['assets'] if not any(by_case[e['case_id']]['status'] == 'kinematic_candidate' for e in a['entries'])],
              'png_verified': png_count, 'all_sources_models_and_artifacts_verified': True,
              'physical_passed': None, 'full_task_passed': None,
              'limitations': ['Declared bend/axis policy is not a human ROM certification',
                             'Thumb scores need not improve when repairing hard-policy violations'],
              'cases': rows}
    atomic_json(root / 'paired_check.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    args = parser.parse_args(); report = audit(args.batch)
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, ensure_ascii=False, indent=2))
