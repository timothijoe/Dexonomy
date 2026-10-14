"""Source-guided thumb refinement with geometric bend constraints.

These constraints are robot retargeting policy, not clinical human ROM limits.
Old results and native models remain unchanged.
"""
import json
from pathlib import Path
from time import monotonic

import numpy as np
from scipy.spatial.transform import Rotation
import yaml

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.util.file_util import load_scene_cfg
from .common import atomic_json, file_receipt, sha256
from .shadow_retarget import (HandGeometry, PHASES, budgeted_solve,
                             pose_variables, variables_pose,
                             render_comparison, render_hand_only)
from .shadow_thumb_v2 import (unit, pad_calibration, thumb_features, thumb_metrics,
                            closest_source_thumb_region, geometry_quality,
                            choose_refinement)


def projected_turn(incoming, outgoing, axis):
    axis = unit(axis)
    incoming = unit(incoming - axis * np.dot(axis, incoming))
    outgoing = unit(outgoing - axis * np.dot(axis, outgoing))
    return float(np.arctan2(np.dot(axis, np.cross(incoming, outgoing)),
                           np.dot(incoming, outgoing)))


def hinge_turns(hand, pose):
    hand.set_pose(pose)
    if hand.kind == 'wuji':
        specs = [('right_finger1_joint3', 'right_finger1_link2',
                  'right_finger1_link3', 'right_finger1_link4'),
                 ('right_finger1_joint4', 'right_finger1_link3',
                  'right_finger1_link4', 'right_finger1_tip_link')]
    else:
        specs = [('rh_THJ2', 'rh_thproximal', 'rh_thmiddle', 'rh_thdistal'),
                 ('rh_THJ1', 'rh_thmiddle', 'rh_thdistal', None)]
    values = []
    for joint, previous, current, following in specs:
        p = hand.data.xpos
        previous, current = [hand.model.body('hand-' + n).id for n in (previous, current)]
        end = p[hand.model.body('hand-' + following).id] if following else hand.points('thumb')[-1]
        axis = hand.data.xaxis[hand.model.joint('hand-' + joint).id]
        values.append(projected_turn(p[current] - p[previous], end - p[current], axis))
    return np.asarray(values)


def bone_directions(hand, pose):
    hand.set_pose(pose)
    # Three anatomical chain segments; skip the target's short base assembly.
    points = hand.points('thumb')[1:]
    vectors = np.diff(points, axis=0)
    return np.asarray([unit(v) for v in vectors]) @ hand.frame()


def calibrate_bends(hand, pad_normal_local):
    zero = np.r_[0, 0, 0, 1, 0, 0, 0, np.zeros(len(hand.names))]
    offsets = hinge_turns(hand, zero)
    hand.set_pose(zero)
    tip = hand.points('thumb')[-1].copy()
    normal = hand.data.xmat[hand.tip_bodies['thumb']].reshape(3, 3) @ pad_normal_local
    names = (['right_finger1_joint3', 'right_finger1_joint4'] if hand.kind == 'wuji'
             else ['rh_THJ2', 'rh_THJ1'])
    indices = [hand.names.index('hand-' + name) for name in names]
    signs, derivatives = [], []
    for index in indices:
        moved = zero.copy()
        moved[7 + index] += 1e-4
        hand.set_pose(moved)
        response = float((hand.points('thumb')[-1] - tip) @ normal / 1e-4)
        if abs(response) < 1e-5:
            raise ValueError('Ambiguous flexion/pad-side calibration')
        signs.append(float(np.sign(response)))
        derivatives.append(response)
    return {'joint_names': names, 'joint_indices': indices,
            'zero_turn_rad': offsets.tolist(), 'flexion_sign': signs,
            'positive_q_tip_derivative_dot_pad_m_per_rad': derivatives,
            'definition': 'Positive flexion approaches the neutral geometric pad side; native hinge-plane turns'}


class BendDomain:
    """Two normalized coordinates enforce both bends and their sum exactly."""
    def __init__(self, limits, calibration, combined_cap):
        self.limits = np.asarray(limits, dtype=float)
        self.offsets = np.asarray(calibration['zero_turn_rad'])
        self.signs = np.asarray(calibration['flexion_sign'])
        self.cap = float(combined_cap)
        endpoints = self.signs[:, None] * (self.limits + self.offsets[:, None])
        self.lower = np.maximum(endpoints.min(axis=1), 0.)
        self.upper = np.minimum(endpoints.max(axis=1), self.cap - self.lower[::-1])
        if np.any(self.upper <= self.lower) or self.lower.sum() >= self.cap:
            raise ValueError('Empty geometric bend domain')

    def angles(self, joints):
        return self.signs * (np.asarray(joints) + self.offsets)

    def decode(self, coordinates):
        u, v = np.asarray(coordinates)
        a = self.lower[0] + u * (self.upper[0] - self.lower[0])
        upper_b = min(self.upper[1], self.cap - a)
        b = self.lower[1] + v * (upper_b - self.lower[1])
        return self.signs * np.array([a, b]) - self.offsets

    def encode(self, joints):
        a, b = self.angles(joints)
        a = np.clip(a, self.lower[0], self.upper[0])
        upper_b = min(self.upper[1], self.cap - a)
        b = np.clip(b, self.lower[1], upper_b)
        return np.array([(a - self.lower[0]) / (self.upper[0] - self.lower[0]),
                         (b - self.lower[1]) / max(upper_b - self.lower[1], 1e-12)])


def natural_quality(hand, poses, source_bones, source_thumb, calibration, domain, cfg):
    phases, failures = {}, []
    for i, (phase, pose) in enumerate(zip(PHASES, poses)):
        bends = np.asarray(calibration['flexion_sign']) * hinge_turns(hand, pose)
        bones = bone_directions(hand, pose)
        angles = np.rad2deg(np.arccos(np.clip(np.sum(bones * source_bones[i], axis=1), -1, 1)))
        thumb = thumb_features(hand, pose, cfg['_pad_normal'])[0]
        pad_angle = thumb_metrics(source_thumb[i], thumb)['pad_angle_deg']
        phases[phase] = {'bend_deg': np.rad2deg(bends).tolist(),
                         'oriented_straight180_deg': (180 - np.rad2deg(bends)).tolist(),
                         'combined_bend_deg': float(np.rad2deg(bends.sum())),
                         'bone_angle_error_deg': angles.tolist(), 'pad_angle_error_deg': pad_angle}
        if np.any(bends < -1e-6): failures.append(phase + '_thumb_reverse_bend')
        if np.any(bends > domain.upper + 1e-6): failures.append(phase + '_thumb_bend_upper')
        if bends.sum() > domain.cap + 1e-6: failures.append(phase + '_thumb_combined_bend')
        if angles.max() > cfg['max_bone_angle_error_deg']: failures.append(phase + '_thumb_bone_direction')
        if pad_angle > cfg['max_pad_angle_error_deg']: failures.append(phase + '_thumb_pad_direction')
    return {'passed': not failures, 'phases': phases, 'failure_reasons': failures,
            'definition': 'Declared geometric policy; not human-rated naturalness or physical success'}


def select_candidate(old_geometry, new_geometry, old_natural, new_natural,
                     old_metrics, new_metrics, cfg):
    old_pass = old_geometry['passed'] and old_natural['passed']
    new_pass = new_geometry['passed'] and new_natural['passed']
    if new_pass and not old_pass:
        return True, 'v3', 'geometric_thumb_constraints_repaired'
    if old_pass and new_pass:
        adopt, reason = choose_refinement(old_geometry, new_geometry, old_metrics, new_metrics, cfg)
        return adopt, 'v3' if adopt else 'v2_retained', reason
    if old_pass:
        return False, 'v2_retained', 'valid_baseline_preserved'
    # No fallback to a baseline with reverse bends as an accepted result.
    return True, 'v3_rejected', 'no_pose_passes_geometry_and_thumb_policy'


def refine_case(baseline_folder, config_path, output, render=True):
    baseline_folder, output = Path(baseline_folder), Path(output)
    if output.exists(): raise ValueError('V3 output exists; use a fresh directory')
    output.mkdir(parents=True)
    started = monotonic()
    cfg = yaml.safe_load(Path(config_path).read_text())
    if cfg.get('schema_version') != 3: raise ValueError('Expected V3 configuration')
    baseline = json.loads((baseline_folder / 'result.json').read_text())
    original = json.loads(Path(baseline['baseline_result']['path']).read_text())
    for key in ['target_model', 'source_hand_model']:
        if sha256(original[key]['path']) != original[key]['sha256']: raise ValueError('Hand model changed')
    selection = baseline['source_selection']
    if sha256(selection['source']['path']) != selection['source']['sha256']: raise ValueError('Source changed')
    scene = load_scene_cfg(selection['scene_path'])
    obj = scene['scene'][scene['task']['obj_name']]
    obj['scale'] = np.asarray(obj['scale']) * selection['scene_scale_multiplier']
    sh = HandGeometry(MuJoCo_VisEnv(HandCfg(original['source_hand_model']['path'], freejoint=True), scene, vis_mode='collision'), 'shadow')
    w = HandGeometry(MuJoCo_VisEnv(HandCfg(original['target_model']['path'], freejoint=True), scene, vis_mode='collision'), 'wuji')
    pad = pad_calibration(sh, w, cfg['source_pad_annotation'])
    source_cal = calibrate_bends(sh, pad['source_normal_local'])
    target_cal = calibrate_bends(w, pad['target_normal_local'])
    source_limits = sh.limits[source_cal['joint_indices']]
    # Positive source rotations toward the pad determine the source policy cap.
    source_positive_max = np.max(np.asarray(source_cal['flexion_sign'])[:, None] * source_limits, axis=1)
    cap = min(float(np.maximum(source_positive_max, 0).sum()), np.deg2rad(cfg['maximum_combined_bend_deg']))
    domain = BendDomain(w.limits[2:4], target_cal, cap)
    with np.load(baseline_folder / 'postures.npz', allow_pickle=False) as stored:
        source_poses = stored['source_qpos'].copy()
        anchor = stored['wuji_selected_qpos'].copy()
        v1 = stored['wuji_v1_qpos'].copy()
    source_thumb, source_shapes, source_tips, source_bones, source_bends = [], [], [], [], []
    for pose in source_poses:
        descriptor, shape, tips = thumb_features(sh, pose, pad['source_normal_local'])
        source_thumb.append(descriptor); source_shapes.append(shape); source_tips.append(tips)
        source_bones.append(bone_directions(sh, pose))
        delta = (hinge_turns(sh, pose) - source_cal['zero_turn_rad'] + np.pi) % (2 * np.pi) - np.pi
        source_bends.append(np.asarray(source_cal['flexion_sign']) * delta)
    source_shapes, source_tips = np.asarray(source_shapes), np.asarray(source_tips)
    bend_goals = []
    for bends in source_bends:
        clipped = np.clip(bends, domain.lower, domain.upper)
        if clipped.sum() > cap: clipped *= cap / clipped.sum()
        bend_goals.append(clipped)
    required = np.array([f in original['required_fingers'] for f in ['thumb', 'index', 'middle', 'ring', 'pinky']])
    region_distance, region_point = closest_source_thumb_region(sh, source_poses[1])
    contact_pin = bool(required[0] and region_distance <= .002)
    deadline = started + cfg['timeout_s_per_case']
    shape_weights = np.ones((5, 1, 1)); shape_weights[0] = cfg['thumb_shape_multiplier']
    action_weights = np.ones((5, 1, 1)); action_weights[0] = cfg['thumb_action_multiplier']
    def residual(poses):
        terms, shapes, thumbs, bends_all = [], [], [], []
        for i, pose in enumerate(poses):
            th, shape, tips = thumb_features(w, pose, pad['target_normal_local'])
            bones = bone_directions(w, pose)
            bends = np.asarray(target_cal['flexion_sign']) * hinge_turns(w, pose)
            thumbs.append(th); shapes.append(shape); bends_all.append(bends)
            ho, hh, _ = w.collision()
            margin = np.minimum(pose[7:11] - w.limits[:4, 0], w.limits[:4, 1] - pose[7:11])
            terms.extend([(cfg['shape_weight'] * shape_weights * (shape - source_shapes[i])).ravel(),
                (cfg['action_weight'] * action_weights * ((shape - w.neutral_shape) - (source_shapes[i] - sh.neutral_shape))).ravel(),
                (cfg['thumb_palm_weight'] * (th['palm'] - source_thumb[i]['palm'])).ravel(),
                (cfg['thumb_opposition_weight'] * (th['opposition'] - source_thumb[i]['opposition'])).ravel(),
                (cfg['thumb_direction_weight'] * (th['directions'] - source_thumb[i]['directions'])).ravel(),
                cfg['thumb_pad_weight'] * (th['pad_normal'] - source_thumb[i]['pad_normal']),
                (cfg['bone_direction_weight'] * (bones - source_bones[i]) / np.sqrt(3)).ravel(),
                cfg['bend_weight'] * (bends - bend_goals[i]) / np.deg2rad(cfg['bend_scale_deg']),
                cfg['thumb_margin_weight'] * np.maximum(cfg['thumb_margin_rad'] - margin, 0) / cfg['thumb_margin_rad'],
                ((tips - source_tips[i]) / cfg['world_tip_scale_m']).ravel(),
                (pose[:3] - anchor[i, :3]) / cfg['wrist_translation_scale_m'],
                cfg['wrist_rotation_weight'] * (Rotation.from_quat(pose[3:7][[1, 2, 3, 0]]) * Rotation.from_quat(anchor[i, 3:7][[1, 2, 3, 0]]).inv()).as_rotvec(),
                cfg['other_joint_prior_weight'] * (pose[11:] - anchor[i, 11:]) / cfg['other_joint_prior_scale_rad'],
                np.maximum(ho - .0005, 0) / cfg['collision_scale_m'],
                np.array([max(hh - .0005, 0) / cfg['collision_scale_m']])])
            if i:
                target_gap = cfg['target_grasp_gap_m'] if i == 1 else cfg['target_squeeze_gap_m']
                terms.append((w.distances(selection['category'])[required] - target_gap) / cfg['contact_scale_m'])
                if contact_pin:
                    bid = w.tip_bodies['thumb']
                    point = w.data.xpos[bid] + w.data.xmat[bid].reshape(3, 3) @ pad['target_patch_local']
                    terms.append(cfg['contact_patch_weight'] * (point - region_point) / cfg['contact_patch_scale_m'])
        for i in [1, 2]:
            terms.append((cfg['transition_weight'] * ((shapes[i] - shapes[i-1]) - (source_shapes[i] - source_shapes[i-1]))).ravel())
            terms.append(cfg['bend_transition_weight'] * ((bends_all[i] - bends_all[i-1]) - (bend_goals[i] - bend_goals[i-1])) / np.deg2rad(cfg['bend_scale_deg']))
            for key in ['palm', 'opposition', 'pad_normal']:
                terms.append((cfg['thumb_transition_weight'] * ((thumbs[i][key] - thumbs[i-1][key]) - (source_thumb[i][key] - source_thumb[i-1][key]))).ravel())
        return np.concatenate(terms)
    def decode_thumb(values):
        poses = anchor.copy()
        for i, value in enumerate(values.reshape(3, 4)):
            poses[i, 7:9] = value[:2]
            poses[i, 9:11] = domain.decode(value[2:])
        return poses
    initial = np.array([np.r_[q[7:9], domain.encode(q[9:11])] for q in anchor])
    lower_thumb = np.tile(np.r_[w.limits[:2, 0] + 1e-5, 0, 0], 3)
    upper_thumb = np.tile(np.r_[w.limits[:2, 1] - 1e-5, 1, 1], 3)
    initial = np.clip(initial.ravel(), lower_thumb + 1e-10, upper_thumb - 1e-10)
    feasible_start = decode_thumb(initial)
    solved_thumb, thumb_solver = budgeted_solve(lambda v: residual(decode_thumb(v)), initial,
        (lower_thumb, upper_thumb), cfg['thumb_only_nfev'], deadline)
    initialized = decode_thumb(solved_thumb)
    variables = np.asarray([pose_variables(q) for q in initialized])
    reference = np.asarray([pose_variables(q) for q in anchor])
    lower, upper = [], []
    for i, ref in enumerate(reference):
        lo = np.r_[ref[:3] - cfg['max_wrist_translation_change_m'], ref[3:6] - cfg['max_wrist_rotvec_change_rad'], w.limits[:, 0] + 1e-5]
        hi = np.r_[ref[:3] + cfg['max_wrist_translation_change_m'], ref[3:6] + cfg['max_wrist_rotvec_change_rad'], w.limits[:, 1] - 1e-5]
        variables[i, 8:10] = domain.encode(initialized[i, 9:11])
        lo[8:10], hi[8:10] = 0, 1
        lower.append(lo); upper.append(hi)
    lower, upper = np.asarray(lower), np.asarray(upper)
    variables = np.clip(variables, lower + 1e-10, upper - 1e-10)
    def decode_all(values):
        poses = []
        for value in values.reshape(3, 26):
            value = value.copy(); value[8:10] = domain.decode(value[8:10])
            poses.append(variables_pose(value))
        return np.asarray(poses)
    solved, joint_solver = budgeted_solve(lambda v: residual(decode_all(v)), variables.ravel(),
        (lower.ravel(), upper.ravel()), cfg['joint_nfev'], deadline)
    proposed = decode_all(solved)
    old_geometry = geometry_quality(w, anchor, source_shapes, source_tips, sh.neutral_shape, required, selection['category'], cfg)
    new_geometry = geometry_quality(w, proposed, source_shapes, source_tips, sh.neutral_shape, required, selection['category'], cfg)
    eval_cfg = {**cfg, '_pad_normal': pad['target_normal_local']}
    old_natural = natural_quality(w, anchor, source_bones, source_thumb, target_cal, domain, eval_cfg)
    new_natural = natural_quality(w, proposed, source_bones, source_thumb, target_cal, domain, eval_cfg)
    def evaluate_thumb(poses):
        return [thumb_metrics(source_thumb[i], thumb_features(w, q, pad['target_normal_local'])[0]) for i, q in enumerate(poses)]
    old_thumb, new_thumb = evaluate_thumb(anchor), evaluate_thumb(proposed)
    select_new, version, reason = select_candidate(old_geometry, new_geometry, old_natural, new_natural, old_thumb, new_thumb, cfg)
    selected = proposed if select_new else anchor.copy()
    selected_geometry, selected_natural = ((new_geometry, new_natural) if select_new else (old_geometry, old_natural))
    passed = selected_geometry['passed'] and selected_natural['passed']
    np.savez_compressed(output / 'postures.npz', source_qpos=source_poses, wuji_v1_qpos=v1,
                        wuji_v2_qpos=anchor, wuji_v3_feasible_start_qpos=feasible_start,
                        wuji_v3_initialized_qpos=initialized, wuji_v3_proposed_qpos=proposed,
                        wuji_selected_qpos=selected, phase=PHASES)
    report = {'schema_version': 3, 'status': 'kinematic_candidate' if passed else 'kinematic_rejected',
              'selected_version': version, 'selection_reason': reason,
              'source_selection': selection, 'bench_targets': baseline['bench_targets'], 'joint_names': w.names,
              'baseline_result': file_receipt(baseline_folder / 'result.json'),
              'baseline_postures': file_receipt(baseline_folder / 'postures.npz'),
              'config': file_receipt(Path(config_path)), 'implementation': file_receipt(Path(__file__)),
              'calibration': {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in pad.items()},
              'bend_calibration': {'source': source_cal, 'target': target_cal,
                  'combined_cap_deg': float(np.rad2deg(cap)), 'bend_upper_deg': np.rad2deg(domain.upper).tolist(),
                  'source_raw_bends_deg': np.rad2deg(source_bends).tolist(),
                  'projected_bend_goals_deg': np.rad2deg(bend_goals).tolist(),
                  'source_goal_projection_count': int(np.count_nonzero(np.abs(np.asarray(source_bends) - bend_goals) > 1e-7))},
              'source_thumb_contact_region': {'enabled': contact_pin, 'source_gap_m': region_distance, 'point_world_m': region_point.tolist()},
              'baseline_quality': old_geometry, 'proposed_quality': new_geometry, 'selected_quality': selected_geometry,
              'baseline_natural': old_natural, 'proposed_natural': new_natural, 'selected_natural': selected_natural,
              'baseline_thumb': dict(zip(PHASES, old_thumb)), 'proposed_thumb': dict(zip(PHASES, new_thumb)),
              'selected_thumb': dict(zip(PHASES, new_thumb if select_new else old_thumb)),
              'failure_reasons': selected_geometry['failure_reasons'] + selected_natural['failure_reasons'],
              'thumb_solver': thumb_solver, 'joint_solver': joint_solver, 'seconds': monotonic() - started,
              'physical_passed': None, 'full_task_passed': None,
              'limitations': ['Static poses only', 'Geometric bend policy is not human clinical ROM',
                             'Thumb pad is a geometry proxy', 'Native model and older results unchanged']}
    atomic_json(output / 'result.json', report)
    if render:
        render_comparison(sh, w, source_poses, anchor, selected, output)
        render_hand_only(sh, w, source_poses, anchor, selected, output / 'hand_only')
        label = {'v3': 'Wuji V3 constrained candidate', 'v3_rejected': 'Wuji V3 - NEEDS ADJUSTMENT',
                 'v2_retained': 'Wuji V2 retained - policy passed'}[version]
        label_comparison(output / 'comparison.png', label)
        label_comparison(output / 'hand_only/comparison.png', label)
        if not select_new:
            (output / 'proposal').mkdir()
            render_comparison(sh, w, source_poses, anchor, proposed, output / 'proposal')
            label_comparison(output / 'proposal/comparison.png', 'Wuji V3 proposal - not selected')
    return report


def label_comparison(path, last_row):
    from PIL import Image, ImageDraw
    image = Image.open(path).convert('RGB'); draw = ImageDraw.Draw(image)
    for row, label in enumerate(['Shadow source', 'Wuji V2 selected baseline', last_row]):
        for column, phase in enumerate(PHASES):
            x, y = column * 640, row * 480
            draw.rectangle((x, y, x + 639, y + 45), fill=(15, 20, 28))
            draw.text((x + 10, y + 10), label + ' | ' + phase, fill='white')
            draw.text((x + 10, y + 28), 'STATIC GEOMETRIC POLICY - physical execution not tested', fill='white')
    image.save(path)
