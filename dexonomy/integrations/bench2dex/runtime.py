"""File boundary for Isaac Lab fixed-posture diagnostics.

capture_pose is called by a running Bench2Dex process after reset/update. It
reads articulation state; it neither initializes Isaac nor controls the robot.
"""
from pathlib import Path

import numpy as np
import yaml

from .common import sha256
from .coordinates import joint_indices, pose_matrix


def _numpy(value):
    if hasattr(value, 'detach'):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def capture_pose(robot, posture_name, semantics_path, *, env_index=0):
    semantics = yaml.safe_load(Path(semantics_path).read_text())
    joint_names = list(robot.data.joint_names)
    if len(joint_names) != 52 or len(set(joint_names)) != 52:
        raise ValueError('Runtime capture needs all 52 uniquely named robot joints')
    body_names = list(robot.data.body_names)
    needed = [name for side in semantics['sides'].values() for name in [side['palm_link'], *side['tip_links']]]
    joint_indices(body_names, needed)  # exact explicit names; no approximate matching
    body_pos = _numpy(robot.data.body_pos_w)[env_index]
    body_quat = _numpy(robot.data.body_quat_w)[env_index]
    transforms = {name: np.r_[body_pos[body_names.index(name)], body_quat[body_names.index(name)]].tolist() for name in needed}
    return {'posture_name': posture_name, 'joint_names': joint_names,
            'qpos_rad': _numpy(robot.data.joint_pos)[env_index].tolist(), 'body_poses_world_wxyz': transforms,
            'capture_mode': 'kinematic_diagnostic'}


def compare_runtime(snapshot, cfg, models_root):
    """Compare every named fixed posture against persisted MuJoCo FK."""
    if snapshot.get('schema_version') != 1 or snapshot.get('simulator') != 'isaaclab' or snapshot.get('robot_key') != cfg['robot_key']:
        raise ValueError('Runtime snapshot has the wrong schema/simulator/robot')
    import mujoco
    from scipy.spatial.transform import Rotation
    semantics = yaml.safe_load(cfg['semantics'].read_text())
    maps = yaml.safe_load((cfg['bench2dex_root'] / 'robots/active_dof_maps.yml').read_text())
    expected_joints = set(maps['robots'][cfg['robot_key']]['full_joint_names'])
    expected_source = sha256(cfg['asset_root'] / cfg['robot_usd'])
    if snapshot.get('robot_usd_sha256') != expected_source:
        raise ValueError('Runtime snapshot was captured with a different original USD')
    if not snapshot.get('bench2dex_commit'):
        raise ValueError('Runtime snapshot must identify the Bench2Dex code commit')
    from .common import git_identity
    if snapshot['bench2dex_commit'] != git_identity(cfg['bench2dex_root'])['commit']:
        raise ValueError('Runtime and inspected Bench2Dex commits disagree')
    frames = snapshot.get('frames', [])
    if len({f['posture_name'] for f in frames}) != len(frames):
        raise ValueError('Duplicate runtime posture names')
    rows = []
    for side in ('right', 'left'):
        folder = Path(models_root) / side
        import json
        reference = json.loads((folder / 'model_report.json').read_text())
        if reference['source']['source']['sha256'] != sha256(cfg['asset_root'] / cfg['hand_urdf'][side]):
            raise ValueError('Converted hand source identity mismatch')
        if reference['mjcf']['sha256'] != sha256(folder / 'hand.xml'):
            raise ValueError('Converted hand artifact identity mismatch')
        if set(reference['postures_rad']) != {f['posture_name'] for f in frames}:
            raise ValueError('Runtime snapshot must cover every declared fixed posture')
        model = mujoco.MjModel.from_xml_path(str(folder / 'hand.xml'))
        data = mujoco.MjData(model)
        desc = semantics['sides'][side]
        for frame in frames:
            if frame.get('capture_mode') != 'kinematic_diagnostic':
                raise ValueError('Fixed-posture comparison needs an explicit diagnostic capture')
            names = frame['joint_names']
            if len(names) != 52 or len(set(names)) != 52:
                raise ValueError('Runtime must declare all 52 unique joint names')
            if set(names) != expected_joints:
                raise ValueError('Runtime joint identity disagrees with target robot')
            qpos = np.asarray(frame['qpos_rad'], dtype=float)
            if qpos.shape != (52,) or not np.isfinite(qpos).all():
                raise ValueError('Bad runtime joint state')
            indices = joint_indices(names, [j['runtime_name'] for j in desc['joints']])
            target = np.asarray(reference['postures_rad'][frame['posture_name']])
            if np.max(np.abs(qpos[indices] - target)) > cfg['validation']['joint_tolerance_rad']:
                raise ValueError('Runtime joints do not match declared fixed posture')
            for joint, value in zip(desc['joints'], qpos[indices]):
                data.qpos[model.joint(joint['urdf_name']).qposadr[0]] = value
            mujoco.mj_forward(model, data)
            world_from_palm = pose_matrix(frame['body_poses_world_wxyz'][desc['palm_link']])
            for tip in desc['tip_links']:
                runtime_pose = np.linalg.inv(world_from_palm) @ pose_matrix(frame['body_poses_world_wxyz'][tip])
                idx = model.body(tip).id
                translation = float(np.linalg.norm(runtime_pose[:3, 3] - data.xpos[idx]))
                angle = float(np.rad2deg(Rotation.from_matrix(runtime_pose[:3, :3].T @ data.xmat[idx].reshape(3, 3)).magnitude()))
                rows.append({'side': side, 'posture': frame['posture_name'], 'tip': tip, 'position_error_m': translation,
                             'angle_error_deg': angle, 'passed': translation <= cfg['validation']['fk_position_tolerance_m'] and angle <= cfg['validation']['fk_angle_tolerance_deg']})
    return {'schema_version': 1, 'runtime_fk_passed': all(r['passed'] for r in rows), 'comparisons': rows,
            'm0_accepted': False, 'remaining': ['Physical geometry/contact surface, flange and dynamics comparison'],
            'note': 'Fixed-pose kinematics only; never grants dynamic grasp success'}
