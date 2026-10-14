"""Read-only source contact-region audit; diagnostics are not physical labels."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh
import yaml

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.util.file_util import load_scene_cfg
from .common import atomic_json, file_receipt, sha256
from .shadow_batch import digest, verify_completed
from .shadow_retarget import HandGeometry, FINGERS
from .thumb_v3_batch import verify_v3, identity as v3_identity

REGIONS = [*FINGERS, 'palm']
SOURCE_PREFIX = dict(zip(FINGERS, ['rh_th', 'rh_ff', 'rh_mf', 'rh_rf', 'rh_lf']))
CONFIG = {'near_m': .002, 'anchor_drift_m': .005, 'edge_band_m': .003,
          'sharp_angle_deg': 45., 'minimum_edge_length_m': .001}


def segment_distance(point, segments):
    if len(segments) == 0: return None
    a = segments[:, 0]; delta = segments[:, 1] - a
    t = np.clip(np.sum((point - a) * delta, axis=1) / np.sum(delta * delta, axis=1), 0, 1)
    return float(np.linalg.norm(point - (a + t[:, None] * delta), axis=1).min())


def feature_segments(mesh, angle_deg, minimum_length):
    counts = np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique))
    boundary = mesh.edges_unique[counts == 1]
    adjacent = mesh.face_adjacency
    # Absolute normal dot ignores flipped coplanar OBJ faces. This deliberately
    # under-detects acute folds rather than treating every reversed face as a rim.
    dot = np.abs(np.sum(mesh.face_normals[adjacent[:, 0]] * mesh.face_normals[adjacent[:, 1]], axis=1))
    sharp = mesh.face_adjacency_edges[np.arccos(np.clip(dot, 0, 1)) >= np.deg2rad(angle_deg)]
    edges = np.vstack([boundary, sharp]) if len(boundary) + len(sharp) else np.empty((0, 2), int)
    segments = mesh.vertices[edges]
    return segments[np.linalg.norm(segments[:, 1] - segments[:, 0], axis=1) >= minimum_length]


def native_nearest(hand, geoms):
    pairs = []
    for h in geoms:
        for o in hand.object_geoms:
            lower = np.linalg.norm(hand.data.geom_xpos[h] - hand.data.geom_xpos[o]) - hand.model.geom_rbound[h] - hand.model.geom_rbound[o]
            pairs.append((float(lower), h, o))
    best = None
    for lower, h, o in sorted(pairs):
        if best is not None and lower > best['gap_m'] + 1e-10: continue
        points = np.zeros(6)
        distance = float(mujoco.mj_geomDistance(hand.model, hand.data, h, o, 1., points))
        origin = 'distance_query'
        for contact in hand.data.contact:
            if {int(contact.geom1), int(contact.geom2)} != {h, o}: continue
            if contact.dist < distance:
                distance = float(contact.dist)
                normal = np.asarray(contact.frame[:3]) * (1 if contact.geom1 == h else -1)
                points[:3] = contact.pos - .5 * distance * normal
                points[3:] = contact.pos + .5 * distance * normal
                origin = 'kinematic_contact_geometry'
        if best is None or distance < best['gap_m']:
            best = {'gap_m': distance, 'hand_point_world_m': points[:3].tolist(),
                    'object_point_world_m': points[3:].tolist(),
                    'hand_body': hand.model.body(int(hand.model.geom_bodyid[h])).name,
                    'object_geom': hand.model.geom(o).name, 'point_method': origin}
    return best


def point_to_hand(hand, point, geoms):
    best = None
    for bid in sorted({int(hand.model.geom_bodyid[g]) for g in geoms}):
        name = hand.model.body(bid).name
        mesh = hand.env.get_body_mesh(name)
        rotation = hand.data.xmat[bid].reshape(3, 3)
        local = (point - hand.data.xpos[bid]) @ rotation
        closest, distances, _ = trimesh.proximity.closest_point(mesh, local[None])
        if best is None or distances[0] < best['distance_m']:
            best = {'distance_m': float(distances[0]), 'hand_body': name,
                    'hand_point_world_m': (closest[0] @ rotation.T + hand.data.xpos[bid]).tolist()}
    return best


def corresponding_geoms(hand, finger, source_body):
    if finger == 'palm': names = ['hand-right_palm_link']
    else:
        index = FINGERS.index(finger) + 1
        if source_body.endswith('distal'): links = ['link4', 'tip_link']
        elif source_body.endswith('middle'): links = ['link3']
        elif source_body.endswith('proximal'): links = ['link2']
        else: links = ['link1', 'link2']
        names = [f'hand-right_finger{index}_{link}' for link in links]
    return [g for g in hand.hand_geom_list if hand.model.body(int(hand.model.geom_bodyid[g])).name in names]


def classify(source, target, anchor_gap, source_edge, target_edge, reliable, required, cfg):
    flags = []
    if reliable:
        if target['full']['gap_m'] > cfg['near_m']: flags.append('finger_contact_lost')
        if target['full']['gap_m'] < -cfg['near_m']: flags.append('deep_penetration')
        if anchor_gap > cfg['anchor_drift_m']:
            flags.append('source_patch_displaced')
            if abs(target['full']['gap_m']) <= cfg['near_m']: flags.append('touching_another_patch')
        if target['corresponding']['gap_m'] > cfg['near_m'] and abs(target['full']['gap_m']) <= cfg['near_m']:
            flags.append('contact_segment_substitution')
        if source_edge is not None and source_edge <= cfg['edge_band_m']:
            if target['full']['gap_m'] > cfg['near_m'] or (anchor_gap > cfg['anchor_drift_m'] and target_edge is not None and target_edge > cfg['edge_band_m']):
                flags.append('source_edge_not_preserved')
    return flags


def audit_case(job, output, cfg):
    folder = Path(job['folder']); r = json.loads((folder / 'result.json').read_text())
    v2 = json.loads(Path(r['baseline_result']['path']).read_text())
    original = json.loads(Path(v2['baseline_result']['path']).read_text())
    selection = r['source_selection']; scene = load_scene_cfg(selection['scene_path'])
    obj = scene['scene'][scene['task']['obj_name']]
    obj['scale'] = np.asarray(obj['scale']) * selection['scene_scale_multiplier']
    source = HandGeometry(MuJoCo_VisEnv(HandCfg(original['source_hand_model']['path'], freejoint=True), scene, vis_mode='collision'), 'shadow')
    target = HandGeometry(MuJoCo_VisEnv(HandCfg(original['target_model']['path'], freejoint=True), scene, vis_mode='collision'), 'wuji')
    raw_mesh = trimesh.load(obj['file_path'], force='mesh', process=True)
    raw_mesh.vertices *= obj['scale']
    rotation = Rotation.from_quat(np.asarray(obj['pose'])[3:][[1, 2, 3, 0]]).as_matrix()
    raw_mesh.vertices = raw_mesh.vertices @ rotation.T + obj['pose'][:3]
    edges = feature_segments(raw_mesh, cfg['sharp_angle_deg'], cfg['minimum_edge_length_m'])
    annotation = yaml.safe_load(Path('assets/hand/shadow/raw_anno', selection['category'] + '.yaml').read_text())
    source_groups, target_groups = {}, {}
    for finger in REGIONS:
        prefix = 'rh_palm' if finger == 'palm' else SOURCE_PREFIX[finger]
        annotated = [n for n in annotation['contact'] if n.startswith(prefix)]
        source_groups[finger] = [g for g in source.hand_geom_list if source.model.body(int(source.model.geom_bodyid[g])).name.removeprefix('hand-') in annotated]
        if not source_groups[finger]:
            source_groups[finger] = [g for g in source.hand_geom_list if source.model.body(int(source.model.geom_bodyid[g])).name.startswith('hand-' + prefix)]
        prefix = 'hand-right_palm_link' if finger == 'palm' else f'hand-right_finger{FINGERS.index(finger)+1}_'
        target_groups[finger] = [g for g in target.hand_geom_list if target.model.body(int(target.model.geom_bodyid[g])).name.startswith(prefix)]
    with np.load(folder / 'postures.npz', allow_pickle=False) as z:
        poses = {k: z[k].copy() for k in ['source_qpos', 'wuji_v2_qpos', 'wuji_selected_qpos']}
    rows = []
    for pi, phase in [(1, 'grasp'), (2, 'squeeze')]:
        source.set_pose(poses['source_qpos'][pi])
        references = {}
        for finger in REGIONS:
            ref = native_nearest(source, source_groups[finger])
            point = np.asarray(ref['object_point_world_m'])
            closest, distance, face = trimesh.proximity.closest_point(raw_mesh, point[None])
            references[finger] = {**ref, 'raw_object_surface_gap_m': float(distance[0]),
                                  'raw_object_point_world_m': closest[0].tolist(),
                                  'raw_object_normal_world': raw_mesh.face_normals[face[0]].tolist(),
                                  'edge_distance_m': segment_distance(closest[0], edges)}
        for version, key in [('v2', 'wuji_v2_qpos'), ('selected', 'wuji_selected_qpos')]:
            target.set_pose(poses[key][pi])
            for finger in REGIONS:
                ref = references[finger]; required = finger in original['required_fingers'] or finger == 'palm' and 'rh_palm' in annotation['contact']
                mapped = corresponding_geoms(target, finger, ref['hand_body'])
                full = native_nearest(target, target_groups[finger]); corresponding = native_nearest(target, mapped)
                pipeline = mapped if finger == 'palm' else target.allowed[finger]
                if finger != 'palm' and selection['category'] == '13_Precision_Sphere':
                    pipeline = [g for g in pipeline if target.model.body(int(target.model.geom_bodyid[g])).name.endswith('tip_link')]
                anchor = point_to_hand(target, np.asarray(ref['object_point_world_m']), mapped)
                closest, distance, face = trimesh.proximity.closest_point(raw_mesh, np.asarray(full['object_point_world_m'])[None])
                target_edge = segment_distance(closest[0], edges)
                comparison = {'full': full, 'corresponding': corresponding, 'pipeline': native_nearest(target, pipeline),
                              'anchor': anchor, 'raw_object_surface_gap_m': float(distance[0]),
                              'raw_object_point_world_m': closest[0].tolist(), 'edge_distance_m': target_edge,
                              'object_anchor_displacement_m': float(np.linalg.norm(np.asarray(full['object_point_world_m']) - ref['object_point_world_m']))}
                reliable = abs(ref['gap_m']) <= cfg['near_m'] and ref['raw_object_surface_gap_m'] <= cfg['near_m']
                flags = classify(ref, comparison, anchor['distance_m'], ref['edge_distance_m'], target_edge, reliable, required, cfg)
                rows.append({'phase': phase, 'finger': finger, 'version': version, 'required': bool(required),
                             'source_near_reference': bool(reliable), 'source': ref, 'target': comparison, 'flags': flags})
    model = target.model
    obj_bid = target.env._obj_active_bodyid
    readiness = {'gravity_disabled': bool(model.opt.disableflags & int(mujoco.mjtDisableBit.mjDSBL_GRAVITY)),
                 'target_actuators': int(model.nu), 'target_hinges': len(target.names),
                 'object_free_joints': [model.joint(j).name for j in range(model.njnt) if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE and not model.joint(j).name.startswith('hand')],
                 'contact_dimensions': sorted(set(int(model.geom_condim[g]) for g in target.hand_geoms | target.object_geoms)),
                 'object_mass_kg': float(model.body_subtreemass[obj_bid]), 'scene_density_kg_m3': obj.get('density', 1000),
                 'native_joint_effort_range_nm': model.jnt_actfrcrange[[model.joint(n).id for n in target.names]].tolist(),
                 'physical_passed': None}
    report = {'case_id': job['case_id'], 'bench_targets': r['bench_targets'], 'source_selection': selection,
              'original_status': r['status'], 'selected_version': r['selected_version'],
              'gravity_readiness': readiness, 'sharp_edge_segments': len(edges), 'rows': rows,
              'inputs': [job['postures'], job['result']], 'diagnostic_only': True,
              'limitations': ['Near-contact geometry does not establish load-bearing force',
                             'Mapped finger segments approximate different hand anatomy',
                             'Sharp-edge proxy misses rounded rims and requires visual review',
                             'Raw surface and convex decomposition differences are reported']}
    atomic_json(Path(output) / 'cases' / (job['case_id'] + '.json'), report)
    return report


def run(batch, output, workers=4):
    batch, output = Path(batch), Path(output)
    if output.exists(): raise ValueError('Audit output exists; use a new directory')
    base = json.loads((batch / 'plan.json').read_text()); verify_v3(base)
    jobs = []
    for j in base['jobs']:
        folder = batch / 'samples' / j['case_id']
        if verify_completed(folder, v3_identity(base, j)) is None: raise ValueError('Missing verified case')
        jobs.append({'case_id': j['case_id'], 'folder': str(folder), 'postures': file_receipt(folder / 'postures.npz'), 'result': file_receipt(folder / 'result.json')})
    output.mkdir(parents=True)
    plan = {'batch': str(batch), 'base_plan': file_receipt(batch / 'plan.json'), 'config': CONFIG,
            'engine': file_receipt(Path(__file__)), 'jobs': jobs, 'input_plan_identity': base['plan_identity']}
    plan['identity'] = digest(plan); atomic_json(output / 'plan.json', plan)
    reports = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as executor:
        futures = [executor.submit(audit_case, job, str(output), CONFIG) for job in jobs]
        for future in as_completed(futures):
            report = future.result(); reports.append(report)
            print(json.dumps({'completed': len(reports), 'total': len(jobs), 'case_id': report['case_id']}, ensure_ascii=False), flush=True)
    for job in jobs:
        for key in ['postures', 'result']:
            if sha256(job[key]['path']) != job[key]['sha256']: raise ValueError('Original posture/report changed during audit')
    return reports
