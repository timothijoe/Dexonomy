#!/usr/bin/env python3
"""Audit mechanical limits and signed thumb bends; no anatomical pass labels."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.integrations.bench2dex.common import atomic_json
from dexonomy.integrations.bench2dex.shadow_retarget import HandGeometry, PHASES


def signed_turns(hand, pose):
    """Project adjacent origin-to-origin segments onto each hinge plane.

    Positive is the model's positive hinge direction. Origin offsets mean
    q=0 does not necessarily give a geometric turn of zero. These are robot
    geometry measurements, not human MCP/IP measurements.
    """
    hand.set_pose(pose)
    positions = hand.data.xpos
    values = []
    for joint in (3, 4):
        previous = hand.model.body(f'hand-right_finger1_link{joint-1}').id
        current = hand.model.body(f'hand-right_finger1_link{joint}').id
        following = hand.model.body('hand-right_finger1_tip_link' if joint == 4
                                    else f'hand-right_finger1_link{joint+1}').id
        axis = hand.data.xaxis[hand.model.joint(f'hand-right_finger1_joint{joint}').id]
        incoming = positions[current] - positions[previous]
        outgoing = positions[following] - positions[current]
        incoming = incoming - axis * np.dot(axis, incoming)
        outgoing = outgoing - axis * np.dot(axis, outgoing)
        if min(np.linalg.norm(incoming), np.linalg.norm(outgoing)) < 1e-9:
            raise ValueError('Degenerate projected thumb segment')
        incoming /= np.linalg.norm(incoming)
        outgoing /= np.linalg.norm(outgoing)
        values.append(np.rad2deg(np.arctan2(np.dot(axis, np.cross(incoming, outgoing)),
                                          np.dot(incoming, outgoing))))
    return np.asarray(values)


def audit(batch, output):
    batch = Path(batch)
    plan = json.loads((batch / 'plan.json').read_text())
    baseline = json.loads(Path(plan['baseline_plan']['path']).read_text())
    model_path = baseline['inputs']['target_model']['path']
    hand = HandGeometry(MuJoCo_VisEnv(HandCfg(model_path, freejoint=True),
                                   vis_mode='collision'), 'wuji')
    zero = np.r_[0, 0, 0, 1, 0, 0, 0, np.zeros(20)]
    zero_turns = signed_turns(hand, zero)
    old_angles, selected_angles, geometry, rows = [], [], [], []
    for job in plan['jobs']:
        folder = batch / 'samples' / job['case_id']
        result = json.loads((folder / 'result.json').read_text())
        with np.load(folder / 'postures.npz', allow_pickle=False) as stored:
            old = stored['wuji_v1_qpos']
            selected = stored['wuji_selected_qpos']
            if selected.shape != (3, 27) or not np.isfinite(selected).all():
                raise ValueError('Invalid selected pose: ' + job['case_id'])
            if np.any(selected[:, 7:] < hand.limits[:, 0] - 1e-9) or np.any(
                    selected[:, 7:] > hand.limits[:, 1] + 1e-9):
                raise ValueError('Mechanical limit violation: ' + job['case_id'])
            turns = np.asarray([signed_turns(hand, pose) for pose in selected])
            # Check sign and zero offsets against actual hinge rotations.
            delta = (turns - zero_turns + 180) % 360 - 180
            np.testing.assert_allclose(delta, np.rad2deg(selected[:, 9:11]), atol=1e-4)
            old_angles.append(np.rad2deg(old[:, 7:11]))
            selected_angles.append(np.rad2deg(selected[:, 7:11]))
            geometry.append(turns)
        rows.append({'case_id': job['case_id'],
                     'bench_object': result['source_selection']['bench_object'],
                     'selected_version': result['selected_version'],
                     'selected_thumb_joint_deg': selected_angles[-1].tolist(),
                     'signed_turn_deg_j3_j4': turns.tolist(),
                     'oriented_straight180_angle_deg_j3_j4': (180 - turns).tolist()})
    old_angles, selected_angles, geometry = map(np.asarray,
                                               (old_angles, selected_angles, geometry))
    report = {'cases': len(rows), 'phases': PHASES, 'target_model': model_path,
              'mechanical_limit_violations': 0,
              'mechanical_ranges_deg': np.rad2deg(hand.limits[:4]).tolist(),
              'selected_joint_min_deg': selected_angles.min(axis=(0, 1)).tolist(),
              'selected_joint_max_deg': selected_angles.max(axis=(0, 1)).tolist(),
              'zero_pose_signed_turn_deg_j3_j4': zero_turns.tolist(),
              'v1_q_below_minus5_cases_by_phase_j3_j4': (old_angles[:, :, 2:] < -5).sum(axis=0).tolist(),
              'selected_q_below_minus5_cases_by_phase_j3_j4': (selected_angles[:, :, 2:] < -5).sum(axis=0).tolist(),
              'selected_signed_turn_below_minus5_cases_by_phase_j3_j4': (geometry < -5).sum(axis=0).tolist(),
              'signed_turn_min_deg_j3_j4': geometry.min(axis=(0, 1)).tolist(),
              'signed_turn_max_deg_j3_j4': geometry.max(axis=(0, 1)).tolist(),
              'interpretation': '180 - signed turn is an oriented angle; unsigned arccos angles cannot exceed 180 degrees.',
              'limitations': ['5 degrees is a diagnostic reporting threshold, not a human ROM limit',
                             'Positive direction follows native robot hinge axes',
                             'Robot joints have not been calibrated to human anatomical joints',
                             'No optimizer or previous batch output modified'],
              'cases_detail': rows}
    atomic_json(Path(output), report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/shadow_wuji_v2/all_matched_thumb_v2'))
    parser.add_argument('--output', type=Path, default=Path('output/shadow_wuji_v2/thumb_angle_audit_2026-10-14.json'))
    args = parser.parse_args()
    report = audit(args.batch, args.output)
    print(json.dumps({key: value for key, value in report.items() if key != 'cases_detail'}, ensure_ascii=False, indent=2))
