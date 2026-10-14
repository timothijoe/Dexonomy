"""Kinematic diagnostics from original hand models and recorded joint names."""
from pathlib import Path

import h5py
import mujoco
import numpy as np
from PIL import Image, ImageDraw
import yaml

from .common import atomic_json, sha256
from .coordinates import reorder_joints


def preview_hands(episode, frame, models, output, cfg):
    output, models = Path(output), Path(models)
    output.mkdir(parents=True, exist_ok=True)
    semantics = yaml.safe_load(cfg['semantics'].read_text())
    with h5py.File(episode) as f:
        if not 0 <= frame < len(f['robot/qpos']):
            raise ValueError('Frame is outside episode')
        recorded_names = f['robot/joint_names'].asstr()[:].tolist()
        qpos = f['robot/qpos'][frame]
        sim_step = int(f['time/sim_step'][frame])
    images, sides = [], {}
    for side in ['right', 'left']:
        mjcf = models / side / 'hand.xml'
        model = mujoco.MjModel.from_xml_path(str(mjcf))
        data = mujoco.MjData(model)
        names = [j['runtime_name'] for j in semantics['sides'][side]['joints']]
        angles = reorder_joints(qpos, recorded_names, names)
        for j, angle in zip(semantics['sides'][side]['joints'], angles):
            data.qpos[model.joint(j['urdf_name']).qposadr[0]] = angle
        mujoco.mj_forward(model, data)
        model.geom_rgba[:, :] = [0.2, 0.65, 0.88, 1] if side == 'right' else [0.24, 0.76, 0.42, 1]
        model.vis.global_.offwidth = 640
        model.vis.global_.offheight = 640
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [0, 0, 0.075]
        camera.distance = 0.38
        camera.azimuth = 120 if side == 'right' else 60
        camera.elevation = -25
        with mujoco.Renderer(model, height=640, width=640) as renderer:
            option = mujoco.MjvOption()
            option.geomgroup[:] = 0
            option.geomgroup[1] = 1  # Visual surface only; collision hulls are a separate diagnostic.
            renderer.update_scene(data, camera=camera, scene_option=option)
            image = Image.fromarray(renderer.render())
        ImageDraw.Draw(image).text((20, 20), f'Bench2Dex Wuji v1 / {side}\nRecorded frame {frame}; kinematics only', fill='white')
        image.save(output / f'{side}.png')
        images.append(image)
        sides[side] = {'mjcf_sha256': sha256(mjcf), 'joint_names': names, 'qpos_rad': angles.tolist()}
    combined = Image.new('RGB', (1280, 640))
    for i, im in enumerate(images):
        combined.paste(im, (640 * i, 0))
    combined.save(output / 'comparison.png')
    report = {'schema_version': 1, 'episode_sha256': sha256(episode), 'frame_index': frame, 'sim_step': sim_step,
              'sides': sides, 'execution_verified': False, 'status': 'kinematic_only',
              'image': str(output / 'comparison.png')}
    atomic_json(output / 'preview_report.json', report)
    return {'image': report['image'], 'status': report['status']}
