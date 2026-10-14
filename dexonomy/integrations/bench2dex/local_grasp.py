"""MuJoCo hand-only grasp generation using original Wuji and task USD geometry.

This module never claims arm reachability, full-task success or Isaac success.
Only reset/geometry optimization sets state; execution uses physical actuators.
"""
from __future__ import annotations

from copy import deepcopy
import json
import hashlib
from pathlib import Path
import re
import shutil
from time import monotonic
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
import trimesh
import yaml

from .catalog import object_relative_path
from .common import atomic_json, file_receipt, sha256
from .coordinates import delta_pose, matrix_pose, pose_matrix


def load_grasp_config(path, _parents=()):
    path = Path(path).resolve()
    if path in _parents or len(_parents) >= 8:
        raise ValueError('Cyclic or excessively deep grasp configuration inheritance')
    cfg = yaml.safe_load(Path(path).read_text())
    sources = []
    if 'base_config' in cfg:
        parent = (Path(path).parent / cfg['base_config']).resolve()
        base = load_grasp_config(parent, (*_parents, path))
        sources = base.pop('configuration_sources')
        base.pop('config_sha256')
        for group, changes in cfg['overrides'].items():
            base[group].update(changes)
        cfg = base
    if cfg.get('schema_version') != 1:
        raise ValueError('Unsupported grasp configuration')
    sources = [*sources, {'name': path.name, 'sha256': sha256(path)}]
    effective = json.dumps({'settings': cfg, 'sources': sources}, sort_keys=True, allow_nan=False)
    cfg['config_sha256'] = hashlib.sha256(effective.encode()).hexdigest()
    cfg['configuration_sources'] = sources
    physics, control = cfg['controller']['physics_dt_s'], cfg['controller']['control_dt_s']
    if physics <= 0 or control <= 0 or not np.isclose(control / physics, round(control / physics)):
        raise ValueError('Control period must be an integer number of positive physics steps')
    if 'execution' in cfg:
        for key in ['settle_s', 'approach_s', 'close_s', 'lift_s', 'hold_s', 'disturbance_s', 'recovery_s', 'timeout_s']:
            if not np.isfinite(cfg['execution'][key]) or cfg['execution'][key] <= 0:
                raise ValueError(f'{key} must be positive and finite')
        if cfg['collision']['solref'][0] < 2 * physics:
            raise ValueError('Contact time constant must cover at least two physics steps')
    return cfg


def usd_object_mesh(path, scale, destination):
    from pxr import Usd, UsdGeom, UsdPhysics
    stage = Usd.Stage.Open(str(path))
    root = stage.GetDefaultPrim()
    if not root:
        raise ValueError('Object USD has no default root')
    cache = UsdGeom.XformCache()
    root_inv = cache.GetLocalToWorldTransform(root).GetInverse()
    meshes = [p for p in Usd.PrimRange(root, Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Mesh)]
    collision_meshes = [p for p in meshes if p.HasAPI(UsdPhysics.CollisionAPI)]
    meshes = collision_meshes or meshes
    vertices, faces, geometries = [], [], []
    offset = 0
    scale = np.asarray(scale, dtype=float)
    if scale.shape != (3,) or not np.isfinite(scale).all() or np.any(scale <= 0):
        raise ValueError('Object scale must be three positive finite multipliers')
    for prim in meshes:
        mesh = UsdGeom.Mesh(prim)
        points = np.asarray(mesh.GetPointsAttr().Get(), dtype=float)
        # USD uses row-vector transforms; root placement is excluded.
        T = np.asarray(cache.GetLocalToWorldTransform(prim) * root_inv)
        points = (points @ T[:3, :3] + T[3, :3]) * scale * UsdGeom.GetStageMetersPerUnit(stage)
        idx = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
        counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int64)
        triangles, start = [], 0
        for count in counts:
            face = idx[start:start + count]; start += count
            triangles.extend([face[0], face[j], face[j + 1]] for j in range(1, count - 1))
        vertices.append(points); faces.append(np.asarray(triangles) + offset); offset += len(points)
        geometries.append({'prim': str(prim.GetPath()), 'collision_approximation': str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()) if prim.HasAPI(UsdPhysics.MeshCollisionAPI) else None})
    if not vertices:
        raise ValueError('USD object contains no mesh geometry')
    mesh = trimesh.Trimesh(np.concatenate(vertices), np.concatenate(faces), process=True)
    masses = [float(UsdPhysics.MassAPI(p).GetMassAttr().Get()) for p in Usd.PrimRange(root, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.MassAPI) and UsdPhysics.MassAPI(p).GetMassAttr().Get() > 0]
    if len(masses) != 1:
        raise ValueError('Local free-object experiment needs one explicit authored USD mass')
    mesh.export(destination)
    return {'source': file_receipt(Path(path)), 'mesh': file_receipt(Path(destination)),
            'scale_xyz': scale.tolist(), 'bounds_object_m': mesh.bounds.tolist(),
            'center_object_m': mesh.bounds.mean(axis=0).tolist(), 'mass_kg': masses[0],
            'mass_policy': 'authored_USD_mass_unchanged_by_scene_scale', 'geometries': geometries,
            'collision_profile': 'mujoco_single_convex_hull',
            'limitations': ['PhysX convex decomposition is not copied into MuJoCo', 'Mass/geometry cross-simulator validation remains pending']}


def collision_exclusions(model, side, palm, cfg):
    pairs = set()
    if cfg['collision']['exclude_parent_child']:
        pairs.update(frozenset([i, int(model.body_parentid[i])]) for i in range(1, model.nbody))
    for finger in range(1, 6):
        for link in cfg['collision']['exclude_palm_finger_root_links']:
            pairs.add(frozenset([model.body(palm).id, model.body(f'{side}_finger{finger}_{link}').id]))
    return pairs


def build_scene(hand_path, object_path, object_info, side, palm, gcfg, output):
    root = ET.parse(hand_path).getroot()
    compiler = root.find('compiler')
    original_meshdir = Path(compiler.get('meshdir', '.'))
    compiler.set('strippath', 'false')
    compiler.set('meshdir', '')
    # A self-contained relative-path scene can be copied to the RTX machine.
    meshdir = output / 'meshes'; meshdir.mkdir(parents=True, exist_ok=True)
    for el in root.find('asset').findall('mesh'):
        source = Path(el.get('file'))
        if not source.is_absolute():
            source = original_meshdir / source
        target = meshdir / source.name
        if target.exists() and sha256(target) != sha256(source):
            raise ValueError('Two source meshes have conflicting portable names')
        if not target.exists():
            shutil.copyfile(source, target)
        el.set('file', 'meshes/' + target.name)
    obj_target = meshdir / 'object.obj'
    if Path(object_path).resolve() != obj_target.resolve():
        shutil.copyfile(object_path, obj_target)
    ET.SubElement(root.find('asset'), 'mesh', name='target_object_mesh', file='meshes/object.obj')
    option = root.find('option')
    if option is None:
        option = ET.SubElement(root, 'option')
    option.set('timestep', str(gcfg['controller']['physics_dt_s']))
    option.set('integrator', 'implicitfast')
    option.set('gravity', '0 0 -9.81')
    option.set('cone', gcfg['collision']['cone'])
    option.set('noslip_iterations', str(gcfg['collision']['noslip_iterations']))
    for geom in root.iter('geom'):
        if geom.get('contype') != '0':
            geom.set('friction', ' '.join(map(str, gcfg['collision']['friction_hand'])))
            geom.set('condim', str(gcfg['collision']['contact_dim']))
            geom.set('solref', ' '.join(map(str, gcfg['collision']['solref'])))
            geom.set('solimp', ' '.join(map(str, gcfg['collision']['solimp'])))
    obj = ET.SubElement(root.find('worldbody'), 'body', name='target_object')
    ET.SubElement(obj, 'freejoint', name='object_free')
    ET.SubElement(obj, 'geom', name='target_object_collision', type='mesh', mesh='target_object_mesh', mass=str(object_info['mass_kg']), rgba='.8 .65 .2 1', condim=str(gcfg['collision']['contact_dim']), friction=' '.join(map(str, gcfg['collision']['friction_object'])))
    obj.find('geom').set('solref', ' '.join(map(str, gcfg['collision']['solref'])))
    obj.find('geom').set('solimp', ' '.join(map(str, gcfg['collision']['solimp'])))
    output.mkdir(parents=True, exist_ok=True)
    static = output / 'geometry.xml'
    ET.ElementTree(root).write(static, encoding='unicode')
    model = mujoco.MjModel.from_xml_path(str(static))
    pairs = collision_exclusions(model, side, palm, gcfg)
    contact = ET.SubElement(root, 'contact')
    exclusions = []
    for pair in sorted(pairs, key=lambda p: sorted(p)):
        if len(pair) != 2 or 0 in pair:
            continue
        a, b = sorted(pair)
        if model.body(a).name == 'target_object' or model.body(b).name == 'target_object':
            continue
        ET.SubElement(contact, 'exclude', body1=model.body(a).name, body2=model.body(b).name)
        exclusions.append([model.body(a).name, model.body(b).name])
    ET.ElementTree(root).write(static, encoding='unicode')
    return root, exclusions


def geometric_measurements(model, data, hand_geoms, object_geom):
    distances = [signed_distance(model, data, gid, object_geom) for gid in hand_geoms]
    self_contacts = [c for c in data.contact if c.geom1 in hand_geoms and c.geom2 in hand_geoms]
    return {'max_hand_object_penetration_m': max([max(0, -d) for d in distances], default=0),
            'max_self_penetration_m': max([max(0, -float(c.dist)) for c in self_contacts], default=0),
            'distance_method': 'minimum of mj_geomDistance and actual mj_forward contact depth; filtered self contacts'}


def signed_distance(model, data, geom, object_geom):
    """Use real penetration depths when convex distance queries return zero."""
    distance = float(mujoco.mj_geomDistance(model, data, geom, object_geom, .25, None))
    for contact in data.contact:
        if (contact.geom1 == geom and contact.geom2 == object_geom) or (contact.geom2 == geom and contact.geom1 == object_geom):
            distance = min(distance, float(contact.dist))
    return distance


def contact_normal(model, data, geom, object_geom):
    active = [c for c in data.contact if (c.geom1 == geom and c.geom2 == object_geom) or (c.geom2 == geom and c.geom1 == object_geom)]
    if active:
        c = min(active, key=lambda x: x.dist)
        return np.asarray(c.frame[:3]) * (1 if c.geom1 == geom else -1)
    points = np.zeros(6)
    mujoco.mj_geomDistance(model, data, geom, object_geom, .25, points)
    normal = points[3:] - points[:3]
    length = np.linalg.norm(normal)
    return normal / length if length > 1e-10 else np.zeros(3)


def optimize_candidate(cfg, gcfg, hand_path, object_usd, scale, side, category, seed, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    semantics = yaml.safe_load(cfg['semantics'].read_text())['sides'][side]
    category_cfg = gcfg['categories'][category]
    info = usd_object_mesh(object_usd, scale, output / 'object.obj')
    root, exclusions = build_scene(hand_path, output / 'object.obj', info, side, semantics['palm_link'], gcfg, output)
    model = mujoco.MjModel.from_xml_path(str(output / 'geometry.xml')); data = mujoco.MjData(model)
    names = [j['urdf_name'] for j in semantics['joints']]
    joints = [model.joint(name).id for name in names]; qidx = [int(model.jnt_qposadr[j]) for j in joints]
    limits = model.jnt_range[joints]; ranges = np.ptp(limits, axis=1)
    rng = np.random.default_rng(seed)
    initial = np.r_[gcfg['optimizer']['initial_thumb_qpos_rad'], np.tile(gcfg['optimizer']['initial_other_finger_qpos_rad'], 4)]
    initial += rng.normal(0, .02, 20) * ranges
    initial = np.clip(initial, limits[:, 0] + .001, limits[:, 1] - .001)
    center = np.asarray(info['center_object_m'])
    guess_center = np.array([.055, 0 if side == 'right' else -.005, .135])
    seed_x = np.r_[initial, guess_center]
    objid = model.geom('target_object_collision').id
    hand_geoms = {i for i in range(model.ngeom) if model.geom_contype[i] and i != objid}
    regions = [[model.geom(f'{side}_finger{i}_{link}_collision_0').id for link in category_cfg['contact_links']] for i in range(1, 6)]
    target_normals = np.asarray(gcfg['optimizer']['contact_normal_targets_right'], dtype=float)
    target_normals /= np.linalg.norm(target_normals, axis=1)[:, None]
    if side == 'left':
        target_normals[:, 1] *= -1
    object_qidx = int(model.joint('object_free').qposadr[0])
    start, calls = monotonic(), 0
    def forward(x):
        data.qpos[qidx] = x[:20]
        data.qpos[object_qidx:object_qidx + 7] = np.r_[x[20:] - center, 1, 0, 0, 0]
        mujoco.mj_forward(model, data)
    def residual(x):
        nonlocal calls
        calls += 1
        if monotonic() - start > gcfg['optimizer']['timeout_s']:
            raise TimeoutError('Single-candidate optimization exceeded timeout')
        forward(x)
        gaps = np.asarray([min(signed_distance(model, data, gid, objid) for gid in region) for region in regions])
        distances = np.asarray([signed_distance(model, data, gid, objid) for gid in hand_geoms])
        self_pen = max([max(0, -float(c.dist) - .0005) for c in data.contact if c.geom1 in hand_geoms and c.geom2 in hand_geoms], default=0)
        actual_normals = np.array([contact_normal(model, data, min(region, key=lambda gid: signed_distance(model, data, gid, objid)), objid) for region in regions])
        return np.r_[(gaps - gcfg['optimizer']['contact_gap_m']) / .002,
                     3 * np.maximum(0, -distances - gcfg['optimizer']['penetration_soft_m']) / .001,
                     gcfg['optimizer']['contact_normal_weight'] * (actual_normals - target_normals).reshape(-1),
                     3 * self_pen / .001, .015 * (x[:20] - initial) / ranges, .05 * (x[20:] - guess_center) / .03]
    result = least_squares(residual, seed_x, bounds=(np.r_[limits[:, 0] + .001, [.015, -.06, .07]], np.r_[limits[:, 1] - .001, [.16, .06, .21]]), max_nfev=gcfg['optimizer']['max_nfev'], diff_step=1e-4)
    forward(result.x)
    measure = geometric_measurements(model, data, hand_geoms, objid)
    gaps = [float(min(signed_distance(model, data, gid, objid) for gid in region)) for region in regions]
    margin = float(np.min(np.minimum(result.x[:20] - limits[:, 0], limits[:, 1] - result.x[:20])))
    passed = max(abs(gap) for gap in gaps) <= gcfg['optimizer']['contact_tolerance_m'] and max(measure['max_hand_object_penetration_m'], measure['max_self_penetration_m']) <= cfg['validation']['penetration_tolerance_m']
    contacts = []
    for finger, region in enumerate(regions, 1):
        gid = min(region, key=lambda i: signed_distance(model, data, i, objid))
        points = np.zeros(6); gap = float(mujoco.mj_geomDistance(model, data, gid, objid, .25, points))
        normal = points[3:] - points[:3]
        if np.linalg.norm(normal) > 1e-10:
            normal /= np.linalg.norm(normal)
        else:
            active = [c for c in data.contact if (c.geom1 == gid and c.geom2 == objid) or (c.geom2 == gid and c.geom1 == objid)]
            if active:
                contact = min(active, key=lambda c: c.dist)
                normal = np.asarray(contact.frame[:3]) * (1 if contact.geom1 == gid else -1)
                gap = float(contact.dist)
                points = np.r_[np.asarray(contact.pos) - .5 * gap * normal, np.asarray(contact.pos) + .5 * gap * normal]
        contacts.append({'finger': finger, 'hand_body': model.body(int(model.geom_bodyid[gid])).name,
                         'point_hand_world_m': points[:3].tolist(), 'point_object_world_m': points[3:].tolist(),
                         'normal_hand_toward_object_world': normal.tolist(), 'gap_m': gap,
                         'method': 'closest actual collision hull surfaces; not tip sites'})
    object_pose = np.r_[result.x[20:] - center, 1, 0, 0, 0]
    pregrasp = np.clip(np.zeros(20), limits[:, 0] + .001, limits[:, 1] - .001)
    pregrasp[:4] = np.clip([result.x[0], -.12, 0., .04], limits[:4, 0] + .001, limits[:4, 1] - .001)
    def pregrasp_residual(q):
        if monotonic() - start > gcfg['optimizer']['timeout_s']:
            raise TimeoutError('Pregrasp optimization exceeded timeout')
        forward(np.r_[q, result.x[20:]])
        gaps = np.array([min(signed_distance(model, data, gid, objid) for gid in region) for region in regions])
        all_distances = np.array([signed_distance(model, data, gid, objid) for gid in hand_geoms])
        self_pen = max([max(0, -float(c.dist) - .0005) for c in data.contact if c.geom1 in hand_geoms and c.geom2 in hand_geoms], default=0)
        return np.r_[(gaps - gcfg['optimizer']['pregrasp_gap_m']) / .001, 3 * np.maximum(0, .002 - all_distances) / .001,
                     3 * self_pen / .001, .025 * (q - result.x[:20]) / ranges]
    opened = least_squares(pregrasp_residual, pregrasp, bounds=(limits[:, 0] + .001, limits[:, 1] - .001), max_nfev=gcfg['optimizer']['pregrasp_max_nfev'], diff_step=1e-4)
    pregrasp = opened.x
    if gcfg['optimizer']['pregrasp_mode'] == 'neutral_fingers_opposed_thumb':
        pregrasp = np.clip(np.zeros(20), limits[:, 0] + .001, limits[:, 1] - .001)
        pregrasp[:4] = np.clip([result.x[0], -.12, 0., .04], limits[:4, 0] + .001, limits[:4, 1] - .001)
    squeeze = result.x[:20].copy()
    def squeeze_residual(q):
        if monotonic() - start > gcfg['optimizer']['timeout_s']:
            raise TimeoutError('Squeeze optimization exceeded timeout')
        forward(np.r_[q, result.x[20:]])
        ds = np.array([signed_distance(model, data, gid, objid) for gid in hand_geoms])
        contact_ds = np.array([min(signed_distance(model, data, gid, objid) for gid in region) for region in regions])
        self_pen = max([max(0, -float(c.dist) - .0005) for c in data.contact if c.geom1 in hand_geoms and c.geom2 in hand_geoms], default=0)
        return np.r_[(contact_ds + gcfg['optimizer']['squeeze_penetration_target_m']) / .001,
                     3 * np.maximum(0, -ds - .0015) / .001, 3 * self_pen / .001, .025 * (q - result.x[:20]) / ranges]
    squeezed = least_squares(squeeze_residual, squeeze, bounds=(limits[:, 0] + .001, limits[:, 1] - .001), max_nfev=gcfg['optimizer']['squeeze_max_nfev'], diff_step=1e-4)
    squeeze = squeezed.x
    squeeze_measure = geometric_measurements(model, data, hand_geoms, objid)
    record = {'schema_version': 1, 'side': side, 'category': category, 'seed': seed, 'joint_names': names,
              'hand_model': file_receipt(Path(hand_path)), 'object': info, 'grasp_config_sha256': gcfg['config_sha256'],
              'object_pose_in_palm_wxyz': object_pose.tolist(),
              'T_object_from_wrist': matrix_pose(np.linalg.inv(pose_matrix(object_pose))).tolist(),
              'pregrasp_qpos_rad': pregrasp.tolist(), 'grasp_qpos_rad': result.x[:20].tolist(), 'squeeze_target_qpos_rad': squeeze.tolist(),
              'squeeze_optimization': {'converged': bool(squeezed.success), 'nfev': squeezed.nfev, 'cost': float(squeezed.cost),
                                       'geometry': squeeze_measure, 'method': 'collision-surface closure; not uniform joint-angle addition'},
              'pregrasp_optimization': {'converged': bool(opened.success), 'nfev': opened.nfev, 'cost': float(opened.cost), 'method': 'collision-surface clearance; no assumption about which joint is flexion'},
              'contacts': contacts, 'collision_exclusions': exclusions, 'collision_exclusion_basis': gcfg['collision']['exclusion_basis'],
              'geometry': {**measure, 'contact_gaps_m': gaps, 'joint_margin_rad': margin, 'passed': passed},
              'optimizer': {'converged': bool(result.success), 'termination': result.message, 'nfev': result.nfev, 'residual_calls': calls, 'seconds': monotonic() - start, 'cost': float(result.cost)},
              'status': 'geometry_valid' if passed else 'rejected', 'validation_scope': 'mujoco_hand_only',
              'isaaclab_passed': None, 'full_task_passed': None}
    atomic_json(output / 'candidate.json', record)
    return record, root


def execute_candidate(cfg, gcfg, record, geometry_root, output, table_z):
    """Actual free-wrist Cartesian PD + finger position-control lift/hold test."""
    output = Path(output)
    root = deepcopy(geometry_root)
    palm_name = yaml.safe_load(cfg['semantics'].read_text())['sides'][record['side']]['palm_link']
    palm = next(b for b in root.find('worldbody').findall('body') if b.get('name') == palm_name)
    palm.insert(0, ET.Element('freejoint', name='wrist_free'))
    vertices = trimesh.load(output / 'object.obj', force='mesh').vertices
    R, table_orientation = choose_table_rotation(output, record, gcfg)
    atomic_json(output / 'table_orientation.json', table_orientation)
    qrot = Rotation.from_matrix(R).as_quat()[[3, 0, 1, 2]]
    object_in_palm = np.asarray(record['object_pose_in_palm_wxyz'])
    object_local = vertices + object_in_palm[:3]
    palm_world = np.array([0., 0., table_z - (object_local @ R.T)[:, 2].min() + .0005])
    object_world = palm_world + R @ object_in_palm[:3]
    palm.set('pos', ' '.join(map(str, palm_world)))
    palm.set('quat', ' '.join(map(str, qrot)))
    obj = next(b for b in root.find('worldbody').findall('body') if b.get('name') == 'target_object')
    obj.set('pos', ' '.join(map(str, object_world)))
    obj.set('quat', ' '.join(map(str, qrot)))
    ET.SubElement(root.find('worldbody'), 'geom', name='table', type='plane', pos=f'0 0 {table_z}', size='1 1 .02', rgba='.25 .28 .3 1', friction='.5 .005 .0001', solref=' '.join(map(str,gcfg['collision']['solref'])), solimp=' '.join(map(str,gcfg['collision']['solimp'])))
    ET.SubElement(root.find('worldbody'), 'light', pos='0 -.3 1.8', dir='0 0 -1')
    actuators = ET.SubElement(root, 'actuator')
    for name in record['joint_names']:
        joint = next(j for j in root.iter('joint') if j.get('name') == name)
        if gcfg['controller']['effort_limits'] == 'bench2dex_override':
            effort = gcfg['controller']['finger_effort_limit_nm']
            joint.set('actuatorfrcrange', f'{-effort} {effort}')
            joint.set('armature', str(gcfg['controller']['finger_armature']))
        ET.SubElement(actuators, 'position', name='drive_' + name, joint=name, kp=str(gcfg['controller']['finger_kp']), kv=str(gcfg['controller']['finger_kv']))
    dynamic_path = output / 'execution.xml'
    ET.ElementTree(root).write(dynamic_path, encoding='unicode')
    model = mujoco.MjModel.from_xml_path(str(dynamic_path)); data = mujoco.MjData(model)
    names = record['joint_names']
    qidx = [int(model.joint(n).qposadr[0]) for n in names]
    limits = np.array([model.jnt_range[model.joint(n).id] for n in names])
    wrist_idx = int(model.joint('wrist_free').qposadr[0])
    object_idx = int(model.joint('object_free').qposadr[0])
    pb, ob = model.body(palm_name).id, model.body('target_object').id
    og = model.geom('target_object_collision').id; tg = model.geom('table').id
    hand_geoms = {i for i in range(model.ngeom) if model.geom_contype[i] and i not in (og, tg)}
    data.qpos[qidx] = record['pregrasp_qpos_rad']
    approach_direction, approach_plan = choose_approach(output, record, gcfg, table_orientation['table_up_normal_palm'])
    atomic_json(output / 'approach_plan.json', approach_plan)
    approach_delta = R @ approach_direction * gcfg['execution']['approach_offset_m']
    data.qpos[wrist_idx:wrist_idx + 7] = np.r_[palm_world + approach_delta, qrot]
    data.qpos[object_idx:object_idx + 7] = np.r_[object_world, qrot]
    mujoco.mj_forward(model, data)
    initial_object_z = float(data.xipos[ob, 2])
    initial_object_center = data.xipos[ob].copy()
    hand_mass = float(model.body_mass.sum() - model.body_mass[ob])
    hand_bodies = np.asarray([i for i in range(1, model.nbody) if i != ob])
    control = gcfg['controller']; execution = gcfg['execution']
    substeps = int(round(control['control_dt_s'] / control['physics_dt_s']))
    frames, physics_frames, snapshots, violations = [], [], {}, set()
    reference_relative = None
    max_hold_translation, max_hold_angle = 0., 0.
    hold_contact_frames, hold_frames, max_lift, disturbance_ok = 0, 0, 0., True
    start = monotonic()
    pre, grasp = np.asarray(record['pregrasp_qpos_rad']), np.asarray(record['squeeze_target_qpos_rad'])
    raised = palm_world + [0, 0, execution['lift_m']]
    phases = [('settle', execution['settle_s'], palm_world + approach_delta, pre, np.zeros(3)),
              ('approach', execution['approach_s'], palm_world, pre, np.zeros(3)),
              ('close', execution['close_s'], palm_world, grasp, np.zeros(3)),
              ('lift', execution['lift_s'], raised, grasp, np.zeros(3)),
              ('hold', execution['hold_s'], raised, grasp, np.zeros(3))]
    for i, direction in enumerate(execution['disturbance_directions']):
        load = np.asarray(direction) * record['object']['mass_kg'] * 9.81 * execution['disturbance_force_weight_fraction']
        phases += [(f'disturbance_{i}', execution['disturbance_s'], raised, grasp, load),
                   (f'recovery_{i}', execution['recovery_s'], raised, grasp, np.zeros(3))]
    previous_wrist = data.qpos[wrist_idx:wrist_idx + 3].copy()
    previous_fingers = pre.copy()
    latched = {}
    latch_absence = {}
    latched_targets = None
    frozen_alignment = np.zeros(3)
    squeeze_direction = np.asarray(record['squeeze_target_qpos_rad']) - np.asarray(record['grasp_qpos_rad'])
    for phase, duration, end_wrist, end_fingers, object_force in phases:
        ticks = max(1, int(round(duration / control['control_dt_s'])))
        for tick in range(ticks):
            if monotonic() - start > execution['timeout_s']:
                raise TimeoutError('Single grasp execution exceeded timeout')
            fraction = (tick + 1) / ticks
            blend = fraction * fraction * (3 - 2 * fraction)
            wrist_target = previous_wrist + blend * (end_wrist - previous_wrist)
            wrist_velocity_target = 6 * fraction * (1 - fraction) / duration * (end_wrist - previous_wrist)
            if control['object_center_alignment_before_lift']:
                if phase in ('approach', 'close'):
                    frozen_alignment = data.xipos[ob] - initial_object_center
                    object_velocity = np.zeros(6)
                    mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, ob, object_velocity, 0)
                    wrist_velocity_target += object_velocity[3:]
                if phase != 'settle':
                    wrist_target = wrist_target + frozen_alignment
            finger_target = previous_fingers + blend * (end_fingers - previous_fingers)
            nominal_finger_target = finger_target.copy()
            if control['contact_latched_closure'] and phase == 'close':
                for contact in data.contact:
                    gid = contact.geom2 if contact.geom1 == og else contact.geom1 if contact.geom2 == og else None
                    if gid is None or gid not in hand_geoms:
                        continue
                    body_name = model.body(int(model.geom_bodyid[gid])).name
                    match = re.search(r'_finger([1-5])_', body_name)
                    if match and int(match.group(1)) not in latched:
                        finger = int(match.group(1))
                        latched[finger] = data.qpos[np.asarray(qidx)[4 * (finger - 1):4 * finger]].copy()
                pressure = control['initial_contact_pressure_fraction'] if len(latched) < control['pressure_ready_contact_count'] else blend
                for finger, state in latched.items():
                    sl = slice(4 * (finger - 1), 4 * finger)
                    finger_target[sl] = state + pressure * squeeze_direction[sl]
                latched_targets = finger_target.copy()
            elif control['contact_latched_closure'] and latched_targets is not None and phase not in ('settle', 'approach'):
                finger_target = latched_targets.copy()
            # Save pre-step observation and the actual command used below.
            current_object = matrix_pose(_body_matrix(data, ob))
            relative = matrix_pose(np.linalg.inv(_body_matrix(data, pb)) @ _body_matrix(data, ob))
            frame = {'phase': phase, 'sim_step': int(round(data.time / control['physics_dt_s'])),
                     'qpos': np.r_[data.qpos[wrist_idx:wrist_idx + 7], data.qpos[qidx]].copy(),
                     'object_pose': current_object.copy(), 'relative_pose': relative.copy(),
                     'finger_command': finger_target.copy(), 'wrist_command': np.r_[wrist_target, qrot],
                     'object_force': object_force.copy()}
            frames.append(frame)
            data.ctrl[:] = finger_target
            peak_ho, peak_self, peak_table = 0., 0., 0.
            supported_entire_tick = True
            for _ in range(substeps):
                if control['contact_latched_closure'] and phase == 'close':
                    active_fingers = set()
                    for contact in data.contact:
                        gid = contact.geom2 if contact.geom1 == og else contact.geom1 if contact.geom2 == og else None
                        if gid is None or gid not in hand_geoms:
                            continue
                        body_name = model.body(int(model.geom_bodyid[gid])).name
                        match = re.search(r'_finger([1-5])_', body_name)
                        if match:
                            finger = int(match.group(1)); active_fingers.add(finger)
                            if finger not in latched:
                                sl = slice(4 * (finger - 1), 4 * finger)
                                latched[finger] = data.qpos[np.asarray(qidx)[sl]].copy()
                    for finger in list(latched):
                        latch_absence[finger] = 0. if finger in active_fingers else latch_absence.get(finger, 0.) + control['physics_dt_s']
                        if latch_absence[finger] >= control['latch_release_after_s']:
                            del latched[finger]
                            sl = slice(4 * (finger - 1), 4 * finger)
                            data.ctrl[sl] = nominal_finger_target[sl]
                    pressure = control['initial_contact_pressure_fraction'] if len(latched) < control['pressure_ready_contact_count'] else blend
                    for finger, state in latched.items():
                        sl = slice(4 * (finger - 1), 4 * finger)
                        data.ctrl[sl] = state + pressure * squeeze_direction[sl]
                    latched_targets = data.ctrl.copy()
                data.xfrc_applied[:] = 0
                velocity = np.zeros(6)
                mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_XBODY, pb, velocity, 0)
                desired_velocity = wrist_velocity_target if control['wrist_velocity_feedforward'] else np.zeros(3)
                force = control['wrist_position_kp'] * (wrist_target - data.xpos[pb]) + control['wrist_position_kd'] * (desired_velocity - velocity[3:])
                if control['hand_gravity_compensation']:
                    force -= hand_mass * model.opt.gravity
                torque_error = Rotation.from_matrix(R @ data.xmat[pb].reshape(3, 3).T).as_rotvec()
                torque = control['wrist_rotation_kp'] * torque_error - control['wrist_rotation_kd'] * velocity[:3]
                if control['hand_gravity_compensation']:
                    gravity_torque = np.cross(data.xipos[hand_bodies] - data.xipos[pb], model.body_mass[hand_bodies, None] * model.opt.gravity).sum(axis=0)
                    torque -= gravity_torque
                data.xfrc_applied[pb, :3] = np.clip(force, -control['wrist_force_limit_n'], control['wrist_force_limit_n'])
                data.xfrc_applied[pb, 3:] = np.clip(torque, -control['wrist_torque_limit_nm'], control['wrist_torque_limit_nm'])
                data.xfrc_applied[ob, :3] = object_force
                before_qpos = data.qpos.copy()
                applied_wrist = data.xfrc_applied[pb].copy()
                sim_step = int(round(data.time / control['physics_dt_s']))
                mujoco.mj_step(model, data)
                if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                    violations.add('nonfinite_state'); break
                # Align kinematics/contact queries with the integrated state.
                mujoco.mj_forward(model, data)
                step_contacts = [c for c in data.contact if (c.geom1 == og and c.geom2 in hand_geoms) or (c.geom2 == og and c.geom1 in hand_geoms)]
                step_table_contact = any((c.geom1 == og and c.geom2 == tg) or (c.geom2 == og and c.geom1 == tg) for c in data.contact)
                peak_ho = max(peak_ho, max([max(0, -float(c.dist)) for c in step_contacts], default=0))
                peak_self = max(peak_self, max([max(0, -float(c.dist)) for c in data.contact if c.geom1 in hand_geoms and c.geom2 in hand_geoms], default=0))
                peak_table = max(peak_table, max([max(0, -float(c.dist)) for c in data.contact if (c.geom1 == tg and c.geom2 in hand_geoms) or (c.geom2 == tg and c.geom1 in hand_geoms)], default=0))
                physics_lift = float(data.xipos[ob, 2] - initial_object_z)
                max_lift = max(max_lift, physics_lift)
                supported_entire_tick &= bool(step_contacts) and not step_table_contact and physics_lift >= cfg['validation']['lift_height_m']
                if reference_relative is not None and (phase == 'hold' or phase.startswith(('disturbance', 'recovery'))):
                    trans, angle = delta_pose(reference_relative, matrix_pose(np.linalg.inv(_body_matrix(data, pb)) @ _body_matrix(data, ob)))
                    max_hold_translation = max(max_hold_translation, trans); max_hold_angle = max(max_hold_angle, angle)
                    if phase != 'hold':
                        disturbance_ok &= supported_entire_tick and trans <= cfg['validation']['hold_translation_m'] and np.rad2deg(angle) <= cfg['validation']['hold_angle_deg']
                physics_frames.append((sim_step, before_qpos, data.qpos.copy(), data.ctrl.copy(), applied_wrist,
                                       object_force.copy(), physics_lift, len(step_contacts), peak_ho, peak_self, peak_table))
                if np.any(data.qpos[qidx] < limits[:, 0] - cfg['validation']['joint_tolerance_rad']) or np.any(data.qpos[qidx] > limits[:, 1] + cfg['validation']['joint_tolerance_rad']):
                    violations.add('joint_limit_violation')
            contacts = [c for c in data.contact if (c.geom1 == og and c.geom2 in hand_geoms) or (c.geom2 == og and c.geom1 in hand_geoms)]
            table_contact = any((c.geom1 == og and c.geom2 == tg) or (c.geom2 == og and c.geom1 == tg) for c in data.contact)
            frame['hand_object_contacts'] = len(contacts)
            frame['table_contact'] = table_contact
            penetration = geometric_measurements(model, data, hand_geoms, og)
            frame['hand_object_penetration_m'] = max(peak_ho, penetration['max_hand_object_penetration_m'])
            frame['self_penetration_m'] = max(peak_self, penetration['max_self_penetration_m'])
            hand_table_pen = max([max(0, -float(c.dist)) for c in data.contact if (c.geom1 == tg and c.geom2 in hand_geoms) or (c.geom2 == tg and c.geom1 in hand_geoms)], default=0)
            frame['hand_table_penetration_m'] = max(peak_table, hand_table_pen)
            if max(frame['hand_object_penetration_m'], frame['self_penetration_m'], frame['hand_table_penetration_m']) > cfg['validation']['penetration_tolerance_m']:
                violations.add('penetration_tolerance_exceeded')
            lift = float(data.xipos[ob, 2] - initial_object_z)
            max_lift = max(max_lift, lift)
            if phase == 'close' and tick == ticks - 1:
                reference_relative = matrix_pose(np.linalg.inv(_body_matrix(data, pb)) @ _body_matrix(data, ob))
            if phase == 'hold' or phase.startswith(('disturbance', 'recovery')):
                now_relative = matrix_pose(np.linalg.inv(_body_matrix(data, pb)) @ _body_matrix(data, ob))
                trans, angle = delta_pose(reference_relative, now_relative)
                max_hold_translation = max(max_hold_translation, trans); max_hold_angle = max(max_hold_angle, angle)
                supported = supported_entire_tick
                if phase == 'hold':
                    hold_frames += 1; hold_contact_frames += int(supported)
                else:
                    disturbance_ok &= supported and trans <= cfg['validation']['hold_translation_m'] and np.rad2deg(angle) <= cfg['validation']['hold_angle_deg']
            if 'nonfinite_state' in violations:
                break
        previous_wrist, previous_fingers = np.asarray(end_wrist), np.asarray(end_fingers)
        if phase == 'settle':
            initial_object_z = float(data.xipos[ob, 2])
        if phase in ('approach', 'close', 'lift', 'hold'):
            snapshots[phase] = data.qpos.copy()
        if 'nonfinite_state' in violations:
            break
    held = hold_frames > 0 and hold_contact_frames == hold_frames and hold_frames * control['control_dt_s'] >= cfg['validation']['hold_duration_s']
    if max_lift < cfg['validation']['lift_height_m']:
        violations.add('insufficient_lift')
    if not held:
        violations.add('not_hand_supported_during_hold')
    if max_hold_translation > cfg['validation']['hold_translation_m'] or np.rad2deg(max_hold_angle) > cfg['validation']['hold_angle_deg']:
        violations.add('relative_pose_drift')
    if not disturbance_ok:
        violations.add('disturbance_failed')
    trajectory = output / 'execution_trace.npz'
    np.savez_compressed(trajectory, phase=np.asarray([f['phase'] for f in frames]), sim_step=np.asarray([f['sim_step'] for f in frames]),
                        qpos=np.asarray([f['qpos'] for f in frames]), object_pose_world_wxyz=np.asarray([f['object_pose'] for f in frames]),
                        object_pose_relative_wxyz=np.asarray([f['relative_pose'] for f in frames]),
                        commanded_finger_qpos=np.asarray([f['finger_command'] for f in frames]), commanded_wrist_pose_world_wxyz=np.asarray([f['wrist_command'] for f in frames]),
                        applied_disturbance_n=np.asarray([f['object_force'] for f in frames]),
                        hand_object_contacts=np.asarray([f['hand_object_contacts'] for f in frames]),
                        hand_object_penetration_m=np.asarray([f['hand_object_penetration_m'] for f in frames]),
                        self_penetration_m=np.asarray([f['self_penetration_m'] for f in frames]),
                        hand_table_penetration_m=np.asarray([f['hand_table_penetration_m'] for f in frames]))
    physics_trace = output / 'physics_trace.npz'
    np.savez_compressed(physics_trace, sim_step=np.asarray([f[0] for f in physics_frames]),
                        qpos_before=np.asarray([f[1] for f in physics_frames]), qpos_after=np.asarray([f[2] for f in physics_frames]),
                        commanded_finger_qpos=np.asarray([f[3] for f in physics_frames]),
                        applied_wrist_force_torque_world=np.asarray([f[4] for f in physics_frames]),
                        applied_object_force_world=np.asarray([f[5] for f in physics_frames]),
                        object_com_lift_m=np.asarray([f[6] for f in physics_frames]), hand_object_contacts=np.asarray([f[7] for f in physics_frames]),
                        hand_object_penetration_peak_m=np.asarray([f[8] for f in physics_frames]), self_penetration_peak_m=np.asarray([f[9] for f in physics_frames]),
                        hand_table_penetration_peak_m=np.asarray([f[10] for f in physics_frames]))
    passed = not violations
    report = {'schema_version': 1, 'simulator': 'mujoco', 'mujoco_version': mujoco.__version__, 'validation_scope': 'hand_only_cartesian_wrist_control',
              'passed': passed, 'failure_reasons': sorted(violations), 'lift_m': max_lift, 'hold_seconds': hold_frames * control['control_dt_s'],
              'supported_hold_frames': hold_contact_frames, 'hold_frames': hold_frames, 'max_relative_translation_m': max_hold_translation,
              'max_relative_angle_deg': float(np.rad2deg(max_hold_angle)), 'disturbance_passed': bool(disturbance_ok),
              'physics_dt_s': control['physics_dt_s'], 'control_dt_s': control['control_dt_s'],
              'controllers': control, 'execution_config': execution, 'criteria': cfg['validation'],
              'table_orientation': table_orientation,
              'approach_plan': approach_plan,
              'trace': file_receipt(trajectory), 'model': file_receipt(dynamic_path), 'seconds': monotonic() - start,
              'physics_trace': file_receipt(physics_trace), 'physics_steps': len(physics_frames),
              'trace_convention': 'pre-step observation + actual applied command + post-step integrated state',
              'object_alignment': 'COM feedback only during approach/close; frozen during lift/hold/disturbance; object state never written after reset',
              'contact_latch_fingers_at_lift': sorted(latched),
              'collision_profile': gcfg['collision'],
              'lift_reference': 'world center of mass relative to settled object; not off-center USD root origin',
              'isaaclab_passed': None, 'full_task_passed': None,
              'limitations': ['No UR5 arm/IK or other hand in this local scene', 'Cartesian wrist controller is local validation only', 'Collision exclusions and hull approximation require review in target simulator']}
    atomic_json(output / 'execution_report.json', report)
    if snapshots:
        try:
            _render_execution(model, snapshots, output, palm_world, record['side'])
        except Exception as exc:
            report['render_error'] = f'{type(exc).__name__}: {exc}'
            atomic_json(output / 'execution_report.json', report)
    return report


def _collision_vertices(model, data, gid):
    mesh = int(model.geom_dataid[gid])
    start, count = int(model.mesh_vertadr[mesh]), int(model.mesh_vertnum[mesh])
    return model.mesh_vert[start:start + count] @ data.geom_xmat[gid].reshape(3, 3).T + data.geom_xpos[gid]


def choose_table_rotation(output, record, gcfg):
    """Choose a support-plane orientation safe for pregrasp/grasp/squeeze hulls."""
    model = mujoco.MjModel.from_xml_path(str(Path(output) / 'geometry.xml'))
    data = mujoco.MjData(model)
    og = model.geom('target_object_collision').id
    qidx = [int(model.joint(name).qposadr[0]) for name in record['joint_names']]
    object_idx = int(model.joint('object_free').qposadr[0])
    data.qpos[object_idx:object_idx + 7] = record['object_pose_in_palm_wxyz']
    preferred = Rotation.from_euler('y', gcfg['execution']['palm_rotation_y_deg'], degrees=True).as_matrix()
    normal_preferred = preferred.T @ [0, 0, 1]
    rng = np.random.default_rng(0)
    normals = rng.normal(size=(gcfg['execution']['table_orientation_samples'], 3))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    normals = np.vstack([normal_preferred, normals, np.eye(3), -np.eye(3)])
    gaps = np.full(len(normals), np.inf)
    for posture in ['pregrasp_qpos_rad', 'grasp_qpos_rad', 'squeeze_target_qpos_rad']:
        data.qpos[qidx] = record[posture]; mujoco.mj_forward(model, data)
        hand = np.concatenate([_collision_vertices(model, data, i) for i in range(model.ngeom) if model.geom_contype[i] and i != og])
        obj = _collision_vertices(model, data, og)
        gaps = np.minimum(gaps, (hand @ normals.T).min(axis=0) - (obj @ normals.T).min(axis=0))
    feasible = gaps >= gcfg['execution']['table_clearance_m']
    if not np.any(feasible):
        raise ValueError('No sampled support-plane orientation clears all planned hand postures')
    scores = normals @ normal_preferred
    scores[~feasible] = -np.inf
    index = int(np.argmax(scores)); normal = normals[index]
    correction, _ = Rotation.align_vectors(np.array([[0., 0., 1.]]), np.asarray([preferred @ normal]))
    R = correction.as_matrix() @ preferred
    return R, {'table_up_normal_palm': normal.tolist(), 'R_world_from_palm': R.tolist(),
               'minimum_planned_clearance_m': float(gaps[index]), 'sample_count': len(normals),
               'method': 'exact convex-hull support extrema of original collision mesh vertices at three declared postures',
               'path_validation': 'static endpoints only; continuous physics execution separately checked'}


def choose_approach(output, record, gcfg, table_normal):
    model = mujoco.MjModel.from_xml_path(str(Path(output) / 'geometry.xml')); data = mujoco.MjData(model)
    qidx = [int(model.joint(name).qposadr[0]) for name in record['joint_names']]
    data.qpos[qidx] = record['pregrasp_qpos_rad']
    objidx = int(model.joint('object_free').qposadr[0]); object_pose = np.asarray(record['object_pose_in_palm_wxyz'])
    og = model.geom('target_object_collision').id
    hand = [i for i in range(model.ngeom) if model.geom_contype[i] and i != og]
    preferred = np.asarray(gcfg['execution']['approach_direction_palm'], dtype=float)
    preferred /= np.linalg.norm(preferred)
    rng = np.random.default_rng(1)
    directions = np.vstack([preferred, np.eye(3), -np.eye(3), rng.normal(size=(32, 3))])
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    order = np.argsort(-(directions @ preferred))
    examined = []
    for index in order:
        direction = directions[index]
        if direction @ np.asarray(table_normal) < -1e-8:
            continue
        clearance = np.inf
        for distance in np.linspace(0, gcfg['execution']['approach_offset_m'], gcfg['execution']['approach_path_samples']):
            data.qpos[objidx:objidx + 7] = object_pose
            data.qpos[objidx:objidx + 3] -= direction * distance
            mujoco.mj_forward(model, data)
            clearance = min(clearance, min(signed_distance(model, data, gid, og) for gid in hand))
        examined.append({'direction_palm': direction.tolist(), 'minimum_clearance_m': float(clearance)})
        if clearance >= gcfg['execution']['approach_path_clearance_m']:
            return direction, {'direction_palm': direction.tolist(), 'minimum_clearance_m': float(clearance), 'samples': gcfg['execution']['approach_path_samples'],
                               'method': 'sampled straight wrist path with open hand; convex distance and real penetration checks', 'examined': examined}
    raise ValueError('No sampled collision-free approach corridor; candidate rejected before execution')


def _body_matrix(data, body):
    T = np.eye(4); T[:3, :3] = data.xmat[body].reshape(3, 3); T[:3, 3] = data.xpos[body]
    return T


def _render_execution(model, snapshots, output, palm_world, side):
    from PIL import Image, ImageDraw
    model.vis.global_.offwidth = 640; model.vis.global_.offheight = 480
    data = mujoco.MjData(model)
    bounds = []
    for qpos in snapshots.values():
        data.qpos[:] = qpos; mujoco.mj_forward(model, data)
        for gid in range(model.ngeom):
            if model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_MESH:
                points = _collision_vertices(model, data, gid)
                bounds.extend([points.min(axis=0), points.max(axis=0)])
    lower, upper = np.min(bounds, axis=0), np.max(bounds, axis=0)
    camera = mujoco.MjvCamera(); camera.lookat[:] = (lower + upper) / 2; camera.distance = max(.4, float(np.max(upper-lower)) * 2.4); camera.azimuth = 130; camera.elevation = -25
    for gid in range(model.ngeom):
        if model.geom_bodyid[gid] != model.body('target_object').id and model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_MESH:
            model.geom_rgba[gid] = [.15, .55, .8, 1] if side == 'right' else [.2, .7, .4, 1]
    data = mujoco.MjData(model); images = []
    with mujoco.Renderer(model, height=480, width=640) as renderer:
        for phase, qpos in snapshots.items():
            data.qpos[:] = qpos; mujoco.mj_forward(model, data); renderer.update_scene(data, camera=camera)
            image = Image.fromarray(renderer.render()); ImageDraw.Draw(image).text((15, 15), f'{side} Wuji v1 / actual MuJoCo execution / {phase}', fill='white')
            image.save(output / f'{phase}.png'); images.append(image)
    combined = Image.new('RGB', (640 * len(images), 480))
    for i, image in enumerate(images):
        combined.paste(image, (i * 640, 0))
    combined.save(output / 'execution.png')


def generate_grasp(cfg, args):
    gcfg = load_grasp_config(args.grasp_config)
    if args.category not in gcfg['categories']:
        raise ValueError('Unsupported grasp category')
    scene_path = cfg['bench2dex_root'] / 'scenes' / f'{args.task}.yaml'
    scene = yaml.safe_load(scene_path.read_text())
    desc = scene['assets'][args.asset]
    rel = object_relative_path(desc['path'])
    if rel.parts[1] not in ('053_mini_soccer_ball', '056_tennis_ball', '058_golf_ball', '144_table-tennis'):
        raise ValueError('First generator supports the four task-27 spheres; other roles are explicitly pending')
    object_usd = cfg['asset_root'] / rel
    hand_path = Path(args.models) / args.side / 'hand.xml'
    if not object_usd.is_file() or not hand_path.is_file():
        raise FileNotFoundError('Original object USD or converted hand is missing')
    model_report_path = hand_path.parent / 'model_report.json'
    if not model_report_path.is_file():
        raise ValueError('Converted hand must have its original model_report.json')
    model_report = json.loads(model_report_path.read_text())
    if model_report['mjcf']['sha256'] != sha256(hand_path) or model_report['source']['source']['sha256'] != sha256(cfg['asset_root'] / cfg['hand_urdf'][args.side]):
        raise ValueError('Converted hand or source URDF identity mismatch')
    if not model_report['urdf_mujoco_fk_passed']:
        raise ValueError('Converted hand failed its original fixed-posture FK checks')
    mesh_root = ET.parse(hand_path).getroot()
    meshdir = Path(mesh_root.find('compiler').get('meshdir', '.'))
    source_meshes = []
    for mesh in mesh_root.find('asset').findall('mesh'):
        path = Path(mesh.get('file'))
        source_meshes.append({'name': mesh.get('name'), 'sha256': sha256(path if path.is_absolute() else meshdir / path)})
    identity = {'generator_version': gcfg['generator_version'], 'generator_sha256': sha256(Path(__file__)),
                'hand_sha256': sha256(hand_path), 'object_sha256': sha256(object_usd),
                'semantics_sha256': sha256(cfg['semantics']), 'grasp_config_sha256': gcfg['config_sha256'],
                'scene_sha256': sha256(scene_path), 'criteria': cfg['validation'],
                'task': args.task, 'asset': args.asset, 'side': args.side, 'category': args.category, 'seed': args.seed, 'execute': args.execute}
    identity['source_meshes'] = source_meshes
    identity['original_urdf_sha256'] = model_report['source']['source']['sha256']
    output = Path(args.output)
    receipt = output / 'result.json'
    if args.check_only:
        return {'status': 'check_only', 'identity': identity, 'output_exists': output.exists()}
    if output.exists() and any(output.iterdir()):
        if args.resume and receipt.is_file():
            prior = json.loads(receipt.read_text())
            if prior['identity'] != identity:
                raise ValueError('Resume identity mismatch; use a separate output for changed settings')
            for artifact in prior['artifacts']:
                if sha256(output / artifact['path']) != artifact['sha256']:
                    raise ValueError('Resume artifact checksum mismatch')
            return {'status': prior['status'], 'resumed': True, 'output': str(output)}
        failure_path = output / 'failure.json'
        if args.resume and failure_path.is_file():
            failure = json.loads(failure_path.read_text())
            if failure['identity'] != identity:
                raise ValueError('Rejected-run resume identity mismatch')
            return {'status': 'rejected', 'resumed': True, 'failure_reason': failure['failure_reason'], 'output': str(output)}
        raise ValueError('Output exists; use --resume for an identical completed run')
    try:
        record, root = optimize_candidate(cfg, gcfg, hand_path, object_usd, desc['scale'], args.side, args.category, args.seed, output)
        status = record['status']
        if args.execute and record['geometry']['passed']:
            physical = execute_candidate(cfg, gcfg, record, root, output, scene['table']['height'])
            status = 'dynamic_valid' if physical['passed'] else 'rejected'
        result = {'schema_version': 1, 'identity': identity, 'status': status, 'validation_scope': 'mujoco_hand_only',
                  'isaaclab_passed': None, 'full_task_passed': None,
                  'artifacts': [{'path': p.relative_to(output).as_posix(), 'sha256': sha256(p)} for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'result.json']}
        atomic_json(receipt, result)
        return {'status': status, 'geometry_passed': record['geometry']['passed'], 'output': str(output), 'isaaclab_passed': None}
    except (ValueError, TimeoutError, RuntimeError) as exc:
        output.mkdir(parents=True, exist_ok=True)
        atomic_json(output / 'failure.json', {'identity': identity, 'status': 'rejected', 'failure_reason': str(exc), 'type': type(exc).__name__})
        raise
