#!/usr/bin/env python3
"""Replay local grasp commands and expose height, load-bearing contacts and video.

Original sample files remain unchanged. Video state reconstruction is separate
from the force audit, which integrates every step from the initial state only.
"""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL', 'egl')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mujoco
import numpy as np

from dexonomy.integrations.bench2dex.artifacts import verify_sample
from dexonomy.integrations.bench2dex.common import atomic_json, file_receipt
from dexonomy.integrations.bench2dex.local_grasp import _collision_vertices


def object_contact_forces(model, data, object_geom, table_geom):
    """World force on the object; contact frame rows are its basis vectors."""
    hand_force, table_force = np.zeros(3), np.zeros(3)
    loaded_links, points = set(), []
    for cid, contact in enumerate(data.contact):
        if object_geom not in (contact.geom1, contact.geom2):
            continue
        force = np.zeros(6)
        mujoco.mj_contactForce(model, data, cid, force)
        if contact.efc_address < 0 or force[0] <= 1e-8:
            continue
        # MuJoCo contact force points from geom1 toward geom2.
        world = contact.frame.reshape(3, 3).T @ force[:3]
        world *= 1 if contact.geom2 == object_geom else -1
        other = contact.geom1 if contact.geom2 == object_geom else contact.geom2
        if other == table_geom:
            table_force += world
        else:
            hand_force += world
            loaded_links.add(model.body(int(model.geom_bodyid[other])).name)
            points.append(contact.pos.copy())
    return hand_force, table_force, sorted(loaded_links), points


def audit(folder, output, render=False):
    folder, output = folder.resolve(), output.resolve()
    if output == folder or output.is_relative_to(folder):
        raise ValueError('Audit output must be separate from the immutable sample')
    verify_sample(folder)
    output.mkdir(parents=True, exist_ok=True)
    with np.load(folder / 'physics_trace.npz', allow_pickle=False) as stored:
        trace = {k: stored[k] for k in stored.files}
    with np.load(folder / 'execution_trace.npz', allow_pickle=False) as stored:
        controls = {k: stored[k] for k in stored.files}
    record = json.loads((folder / 'candidate.json').read_text())
    model = mujoco.MjModel.from_xml_path(str(folder / 'execution.xml'))
    data = mujoco.MjData(model)
    obj, palm = model.body('target_object').id, model.body(f'{record["side"]}_palm_link').id
    og, tg = model.geom('target_object_collision').id, model.geom('table').id
    data.qpos[:] = trace['qpos_before'][0]
    mujoco.mj_forward(model, data)
    control_indices = np.searchsorted(controls['sim_step'], trace['sim_step'], side='right') - 1
    phases = controls['phase'][control_indices]
    rows, maximum_error = [], 0.
    for i in range(len(trace['sim_step'])):
        data.ctrl[:] = trace['commanded_finger_qpos'][i]
        data.xfrc_applied[:] = 0
        data.xfrc_applied[palm] = trace['applied_wrist_force_torque_world'][i]
        data.xfrc_applied[obj, :3] = trace['applied_object_force_world'][i]
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        maximum_error = max(maximum_error, float(np.max(np.abs(data.qpos - trace['qpos_after'][i]))))
        if maximum_error > 1e-8 or not np.isfinite(data.qpos).all():
            raise ValueError(f'Physical replay diverged at step {i}: {maximum_error}')
        hand, table, links, points = object_contact_forces(model, data, og, tg)
        rows.append({'time_s': float(data.time), 'phase': str(phases[i]),
                     'object_com_z_m': float(data.xipos[obj, 2]),
                     'object_bottom_z_m': float(_collision_vertices(model, data, og)[:, 2].min()),
                     'wrist_z_m': float(data.xpos[palm, 2]),
                     'hand_force_world_n': hand.tolist(), 'table_force_world_n': table.tolist(),
                     'loaded_hand_links': links,
                     'loaded_contact_positions_world_m': [p.tolist() for p in points]})
    weight = float(-model.body_mass[obj] * model.opt.gravity[2])
    phase_summary = {}
    for phase in dict.fromkeys(phases):
        selected = [r for r in rows if r['phase'] == phase]
        phase_summary[str(phase)] = {
            'start_com_z_m': selected[0]['object_com_z_m'],
            'end_com_z_m': selected[-1]['object_com_z_m'],
            'end_wrist_z_m': selected[-1]['wrist_z_m'],
            'min_object_bottom_above_table_m': min(r['object_bottom_z_m'] for r in selected) - float(model.geom_pos[tg, 2]),
            'min_loaded_hand_links': min(len(r['loaded_hand_links']) for r in selected),
            'loaded_hand_links_union': sorted({link for r in selected for link in r['loaded_hand_links']}),
            'mean_hand_upward_force_n': float(np.mean([r['hand_force_world_n'][2] for r in selected])),
            'min_hand_upward_force_n': min(r['hand_force_world_n'][2] for r in selected),
            'max_table_force_norm_n': max(float(np.linalg.norm(r['table_force_world_n'])) for r in selected)}
    held = phase_summary['hold']
    report = {'sample': str(folder), 'scope': 'same-model physical replay and force audit',
              'mujoco_version': mujoco.__version__, 'max_qpos_error': maximum_error,
              'physics_steps': len(rows), 'object_weight_n': weight,
              'equality_constraints': int(model.neq),
              'object_gravity_compensation': float(model.body_gravcomp[obj]),
              'normal_phase_object_applied_force_max_n': float(np.max(np.linalg.norm(trace['applied_object_force_world'][np.isin(phases, ['settle','approach','close','lift','hold'])], axis=1))),
              'phase_summary': phase_summary,
              'lift_phase_com_delta_m': phase_summary['lift']['end_com_z_m'] - phase_summary['close']['end_com_z_m'],
              'close_phase_com_delta_m': phase_summary['close']['end_com_z_m'] - phase_summary['approach']['end_com_z_m'],
              'hold_force_audit_passed': held['min_loaded_hand_links'] >= 1 and held['max_table_force_norm_n'] < 1e-6 and held['min_object_bottom_above_table_m'] >= .05 and abs(held['mean_hand_upward_force_n'] - weight) < .05 * weight,
              'inputs': [file_receipt(folder / n) for n in ['execution.xml','physics_trace.npz','execution_trace.npz']],
              'force_convention_source': 'https://mujoco.readthedocs.io/en/3.3.3/XMLreference.html#contact-pair',
              'limitations': ['Local free-wrist scene; arm reachability untested', 'Original contact/friction parameters unchanged', 'Force audit does not classify the grasp taxonomy']}
    atomic_json(output / 'audit.json', report)
    np.savez_compressed(output / 'force_height_trace.npz', time_s=[r['time_s'] for r in rows], phase=phases,
                        object_com_z_m=[r['object_com_z_m'] for r in rows],
                        hand_force_world_n=[r['hand_force_world_n'] for r in rows],
                        table_force_world_n=[r['table_force_world_n'] for r in rows])
    if render:
        render_audit(model, trace, phases, rows, obj, og, tg, output)
    return report


def render_audit(model, trace, phases, rows, obj, og, tg, output):
    from PIL import Image, ImageDraw
    import cv2

    model.vis.global_.offwidth, model.vis.global_.offheight = 960, 640
    for gid in range(model.ngeom):
        if gid not in (og,tg):
            model.geom_rgba[gid] = [.15,.55,.8,1]
    # Display source visual meshes for the hand; collision hulls are queried for forces.
    option = mujoco.MjvOption()
    option.geomgroup[0] = 0
    model.geom_group[og] = model.geom_group[tg] = 2
    option.geomgroup[2] = 1
    data = mujoco.MjData(model)
    fps = 20
    indices = np.unique(np.r_[np.arange(0,len(rows),round(1 / (fps * model.opt.timestep))),len(rows)-1]).astype(int)
    centers = []
    for i in indices:
        data.qpos[:] = trace['qpos_after'][i]
        mujoco.mj_forward(model,data)
        centers.append(data.xipos[obj].copy())
    centers = np.asarray(centers)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = (centers.min(axis=0) + centers.max(axis=0)) / 2 + [0,0,.025]
    camera.distance = max(.55,float(np.ptp(centers,axis=0).max()) * 2.4 + .25)
    camera.azimuth, camera.elevation = 115,-15
    writer = cv2.VideoWriter(str(output / 'execution_audit.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),fps,(960,640))
    if not writer.isOpened():
        raise RuntimeError('MP4 writer failed')
    images = []
    settled_z = next(r['object_com_z_m'] for r in reversed(rows) if r['phase'] == 'settle')
    def annotated_frame(renderer, index, cam, collision=False):
        data.qpos[:] = trace['qpos_after'][index]
        mujoco.mj_forward(model,data)
        renderer.update_scene(data,camera=cam,scene_option=option)
        # Positions and load-bearing status both come from the true command replay.
        for position in rows[index]['loaded_contact_positions_world_m']:
            geom = renderer.scene.geoms[renderer.scene.ngeom]
            mujoco.mjv_initGeom(geom,mujoco.mjtGeom.mjGEOM_SPHERE,np.array([.004]*3),np.asarray(position),np.eye(3).ravel(),np.array([.1,1,.2,1],dtype=np.float32))
            renderer.scene.ngeom += 1
        img = Image.fromarray(renderer.render())
        draw = ImageDraw.Draw(img)
        r = rows[index]
        draw.rectangle((0,0,960,92),fill=(15,20,28))
        draw.text((16,10),f'ACTUAL RECORDED EXECUTION | t={r["time_s"]:.2f}s | {r["phase"]}',fill='white')
        draw.text((16,30),f'Ball COM rise from settled: {(r["object_com_z_m"]-settled_z)*1000:.1f} mm | table top z=0.750 m',fill='yellow')
        draw.text((16,50),f'Loaded hand links: {len(r["loaded_hand_links"])} | hand upward force: {r["hand_force_world_n"][2]:.3f} N | weight: {-model.body_mass[obj]*model.opt.gravity[2]:.3f} N',fill='white')
        hand_label = 'hand collision hulls' if collision else 'original hand visuals'
        draw.text((16,70),f'Blue: {hand_label} | Gold: ball collision mesh | Green: load-bearing contact locations',fill='white')
        return img
    try:
        with mujoco.Renderer(model,height=640,width=960) as renderer:
            for index in indices:
                img = annotated_frame(renderer,index,camera)
                writer.write(cv2.cvtColor(np.asarray(img),cv2.COLOR_RGB2BGR))
                images.append(img.resize((720,480)))
            end_hold = int(np.flatnonzero(phases=='hold')[-1])
            data.qpos[:] = trace['qpos_after'][end_hold]
            mujoco.mj_forward(model,data)
            camera.lookat[:] = data.xipos[obj] + [0,0,.025]
            camera.distance = .32
            views = []
            for angle in [25,115,205]:
                camera.azimuth = angle
                views.append(annotated_frame(renderer,end_hold,camera))
            sheet = Image.new('RGB',(960*3,640))
            for i,img in enumerate(views): sheet.paste(img,(960*i,0))
            sheet.save(output/'hold_contact_views.png')
            option.geomgroup[0], option.geomgroup[1] = 1,0
            for gid in range(model.ngeom):
                if gid != tg: model.geom_rgba[gid,3] = .4
            camera.azimuth = 25
            collision_image = annotated_frame(renderer,end_hold,camera,collision=True)
            ImageDraw.Draw(collision_image).text((16,98),'TRANSPARENT COLLISION HULLS | green markers are load-bearing contacts',fill='white')
            collision_image.save(output/'hold_collision_contacts.png')
    finally:
        writer.release()
    images[0].save(output/'execution_audit.gif',save_all=True,append_images=images[1:],duration=50,loop=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--render',action='store_true')
    args = parser.parse_args()
    report = audit(args.sample,args.output,args.render)
    print(json.dumps({k:report[k] for k in ['sample','max_qpos_error','object_weight_n','close_phase_com_delta_m','lift_phase_com_delta_m','hold_force_audit_passed']},indent=2))
    print(json.dumps(report['phase_summary']['hold'],indent=2))
