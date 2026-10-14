"""Offline camera-grid export for the frozen V3 poses; no optimization."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
import json
import multiprocessing
from pathlib import Path
from time import monotonic

import mujoco
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.util.file_util import load_scene_cfg
from .common import atomic_json, file_receipt, sha256
from .shadow_batch import digest, verify_completed
from .shadow_retarget import HandGeometry, PHASES
from .thumb_v3_batch import verify_v3, identity as v3_identity

AZIMUTHS = tuple((135 + 30 * step) % 360 for step in range(12))
ELEVATIONS = (-65, -45, -25, -5, 15)
MODES = ('scene', 'hand')
ROLES = ('source', 'v2', 'selected')


def aligned_pose(hand, pose):
    hand.set_pose(pose)
    frame = hand.frame(); palm = hand.data.xpos[hand.palm].copy()
    result = pose.copy()
    result[:3] = frame.T @ (pose[:3] - palm)
    matrix = frame.T @ Rotation.from_quat(pose[3:7][[1, 2, 3, 0]]).as_matrix()
    result[3:7] = Rotation.from_matrix(matrix).as_quat()[[3, 0, 1, 2]]
    return result


def bounds_for(hands, poses, include_object):
    bounds = []
    for hand, sequence in zip(hands, poses):
        meshes = [(hand.env.get_body_id(name), hand.env.get_body_mesh(name))
                  for name in hand.env.get_all_body_names()
                  if include_object or name.startswith('hand-')]
        for pose in sequence:
            hand.set_pose(pose)
            for bid, mesh in meshes:
                points = mesh.vertices @ hand.data.xmat[bid].reshape(3, 3).T + hand.data.xpos[bid]
                bounds.extend([points.min(axis=0), points.max(axis=0)])
    lo, hi = np.min(bounds, axis=0), np.max(bounds, axis=0)
    return {'lookat': ((lo + hi) / 2).tolist(), 'distance': max(.3, float((hi - lo).max()) * 2.1)}


def frame_name(phase, mode, pitch, yaw):
    return f'{phase}_{mode}_p{pitch:02d}_y{yaw:02d}.webp'


def export_case(job, folder, config, expected):
    folder = Path(folder)
    if folder.exists(): raise ValueError('Use verified resume or a fresh rotation case')
    folder.mkdir(parents=True)
    started = monotonic()
    result = json.loads(Path(job['result']['path']).read_text())
    v2 = json.loads(Path(result['baseline_result']['path']).read_text())
    original = json.loads(Path(v2['baseline_result']['path']).read_text())
    selection = result['source_selection']; scene = load_scene_cfg(selection['scene_path'])
    obj = scene['scene'][scene['task']['obj_name']]
    obj['scale'] = np.asarray(obj['scale']) * selection['scene_scale_multiplier']
    hands = [HandGeometry(MuJoCo_VisEnv(HandCfg(original[key]['path'], freejoint=True), scene,
                          vis_mode='collision'), kind) for key, kind in
             [('source_hand_model', 'shadow'), ('target_model', 'wuji'), ('target_model', 'wuji')]]
    with np.load(job['postures']['path'], allow_pickle=False) as z:
        poses = [z[key].copy() for key in ['source_qpos', 'wuji_v2_qpos', 'wuji_selected_qpos']]
    hand_poses = [np.asarray([aligned_pose(hand, q) for q in sequence])
                  for hand, sequence in zip(hands, poses)]
    bounds = {'scene': bounds_for(hands, poses, True), 'hand': bounds_for(hands, hand_poses, False)}
    colors = ([.8, .3, .15, 1], [.2, .45, .75, 1], [.12, .65, .72, 1])
    width, height = config['width'], config['height']
    for hand, color in zip(hands, colors):
        hand.model.vis.global_.offwidth = width; hand.model.vis.global_.offheight = height
        for gid in range(hand.model.ngeom):
            hand.model.geom_group[gid] = 0 if gid in hand.hand_geoms else 2 if gid in hand.object_geoms else 1
            if gid in hand.hand_geoms: hand.model.geom_rgba[gid] = color
            elif gid in hand.object_geoms: hand.model.geom_rgba[gid] = [.8, .7, .2, 1]
    option = mujoco.MjvOption(); option.geomgroup[1] = 0
    camera = mujoco.MjvCamera()
    image = np.empty((height, width * 3, 3), dtype=np.uint8)
    with ExitStack() as stack:
        renderers = [stack.enter_context(mujoco.Renderer(hand.model, height=height, width=width)) for hand in hands]
        for mode in MODES:
            option.geomgroup[2] = int(mode == 'scene')
            camera.lookat[:] = bounds[mode]['lookat']; camera.distance = bounds[mode]['distance']
            for phase_index, phase in enumerate(PHASES):
                for hand, sequence in zip(hands, poses if mode == 'scene' else hand_poses):
                    hand.set_pose(sequence[phase_index])
                for pitch, elevation in enumerate(ELEVATIONS):
                    camera.elevation = elevation
                    for yaw, azimuth in enumerate(AZIMUTHS):
                        camera.azimuth = azimuth
                        for role, (hand, renderer) in enumerate(zip(hands, renderers)):
                            renderer.update_scene(hand.data, camera=camera, scene_option=option)
                            image[:, role * width:(role + 1) * width] = renderer.render()
                        Image.fromarray(image).save(folder / frame_name(phase, mode, pitch, yaw),
                                                   quality=config['quality'], method=3)
    artifacts = [{'path': p.name, 'sha256': sha256(p), 'bytes': p.stat().st_size}
                 for p in sorted(folder.glob('*.webp'))]
    if len(artifacts) != 360: raise ValueError('Incomplete three-phase camera grid')
    row = {'case_id': job['case_id'], 'frames': len(artifacts), 'bounds': bounds,
           'bytes': sum(p['bytes'] for p in artifacts), 'seconds': monotonic() - started,
           'postures': job['postures'], 'status': result['status'], 'selected_version': result['selected_version']}
    atomic_json(folder / 'receipt.json', {'identity': expected, 'row': row, 'artifacts': artifacts})
    return row


def prepare(batch, output, ids=None, width=480, height=360, quality=76):
    batch, output = Path(batch), Path(output)
    if output.exists(): raise ValueError('Rotation output exists; use resume or a new directory')
    base = json.loads((batch / 'plan.json').read_text()); verify_v3(base)
    summary = json.loads((batch / 'summary.json').read_text())
    if not summary['all_cases_terminal']: raise ValueError('V3 batch is incomplete')
    if width < 160 or height < 120 or not 1 <= quality <= 100: raise ValueError('Invalid image dimensions/quality')
    selected = set(ids) if ids else {j['case_id'] for j in base['jobs']}
    known = {j['case_id'] for j in base['jobs']}
    if not selected <= known or ids and len(ids) != len(selected): raise ValueError('Unknown or duplicate case ID')
    jobs = []
    for job in base['jobs']:
        if job['case_id'] not in selected: continue
        folder = batch / 'samples' / job['case_id']
        row = verify_completed(folder, v3_identity(base, job))
        if row is None or row['status'] == 'error': raise ValueError('Missing verified V3 case')
        jobs.append({'case_id': job['case_id'], 'postures': file_receipt(folder / 'postures.npz'),
                     'result': file_receipt(folder / 'result.json'), 'receipt': file_receipt(folder / 'receipt.json')})
    plan = {'schema_version': 1, 'batch': str(batch), 'base_plan': file_receipt(batch / 'plan.json'),
            'base_plan_identity': base['plan_identity'], 'jobs': jobs,
            'config': {'width': width, 'height': height, 'quality': quality},
            'azimuths': list(AZIMUTHS), 'elevations': list(ELEVATIONS), 'phases': PHASES,
            'inputs': {'engine': file_receipt(Path(__file__)),
                       'geometry': file_receipt(Path(__file__).with_name('shadow_retarget.py'))},
            'scope': 'full' if selected == known else 'pilot', 'postures_modified': False}
    plan['plan_identity'] = digest(plan)
    output.mkdir(parents=True); atomic_json(output / 'plan.json', plan)
    return plan


def verify(plan):
    copy = dict(plan); expected = copy.pop('plan_identity')
    if digest(copy) != expected: raise ValueError('Rotation plan changed')
    for receipt in [plan['base_plan'], *plan['inputs'].values(),
                    *[j[k] for j in plan['jobs'] for k in ['postures', 'result', 'receipt']]]:
        if sha256(receipt['path']) != receipt['sha256']: raise ValueError('Rotation input changed: ' + receipt['path'])
    verify_v3(json.loads(Path(plan['base_plan']['path']).read_text()))


def identity(plan, job):
    return digest({'plan': plan['plan_identity'], 'case': job['case_id']})


def run(plan, output, workers=4):
    if not 1 <= workers <= 4: raise ValueError('Use one to four CPU workers')
    verify(plan); output = Path(output); rows, pending = {}, []
    for job in plan['jobs']:
        folder = output / 'frames' / job['case_id']; expected = identity(plan, job)
        row = verify_completed(folder, expected)
        if row: rows[job['case_id']] = row
        elif folder.exists(): raise ValueError('Incomplete export cannot be silently reused: ' + str(folder))
        else: pending.append((job, folder, expected))
    def save():
        summary = {'completed_cases': len(rows), 'total_cases': len(plan['jobs']),
                   'all_complete': len(rows) == len(plan['jobs']), 'scope': plan['scope'],
                   'frames': sum(r['frames'] for r in rows.values()), 'bytes': sum(r['bytes'] for r in rows.values()),
                   'rows': [rows[j['case_id']] for j in plan['jobs'] if j['case_id'] in rows]}
        atomic_json(output / 'summary.json', summary)
        return summary
    save()
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as executor:
        futures = [executor.submit(export_case, job, str(folder), plan['config'], expected) for job, folder, expected in pending]
        for future in as_completed(futures):
            row = future.result(); rows[row['case_id']] = row; save()
            print(json.dumps({'completed': len(rows), 'total': len(plan['jobs']), **row}, ensure_ascii=False), flush=True)
    return save()
