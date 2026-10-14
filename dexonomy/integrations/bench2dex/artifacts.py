"""Verify, replay recorded physical commands, and export portable local samples."""
import json
from pathlib import Path
import shutil
import zipfile
from time import monotonic

import mujoco
import numpy as np

from .common import atomic_json, sha256
from .coordinates import matrix_pose


def verify_sample(folder):
    folder = Path(folder).resolve()
    receipt = json.loads((folder / 'result.json').read_text())
    for item in receipt['artifacts']:
        path = (folder / item['path']).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or sha256(path) != item['sha256']:
            raise ValueError(f'Artifact missing or checksum mismatch: {item["path"]}')
    return receipt


def replay_physics(folder, output):
    folder = Path(folder).resolve()
    receipt = verify_sample(folder)
    if not (folder / 'physics_trace.npz').is_file():
        raise ValueError('Sample has no recorded physical execution')
    # NpzFile decompresses on every lookup. Load once before the physics loop.
    with np.load(folder / 'physics_trace.npz', allow_pickle=False) as stored:
        trace = {key: stored[key] for key in stored.files}
    record = json.loads((folder / 'candidate.json').read_text())
    execution = json.loads((folder / 'execution_report.json').read_text())
    model = mujoco.MjModel.from_xml_path(str(folder / 'execution.xml'))
    data = mujoco.MjData(model)
    palm = model.body(f'{record["side"]}_palm_link').id
    obj = model.body('target_object').id
    data.qpos[:] = trace['qpos_before'][0]
    mujoco.mj_forward(model, data)
    maximum_qpos_error = 0.
    started = monotonic()
    completed = 0
    termination = 'complete'
    for i in range(len(trace['sim_step'])):
        if monotonic() - started > 60:
            termination = 'timeout'; break
        data.ctrl[:] = trace['commanded_finger_qpos'][i]
        data.xfrc_applied[:] = 0
        data.xfrc_applied[palm] = trace['applied_wrist_force_torque_world'][i]
        data.xfrc_applied[obj, :3] = trace['applied_object_force_world'][i]
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        maximum_qpos_error = max(maximum_qpos_error, float(np.max(np.abs(data.qpos - trace['qpos_after'][i]))))
        completed = i + 1
        if maximum_qpos_error > 1e-4 or not np.isfinite(data.qpos).all():
            termination = 'state_divergence'; break
    report = {'schema_version': 1, 'sample_status': receipt['status'], 'original_physical_passed': execution['passed'],
              'physics_steps': len(trace['sim_step']), 'max_qpos_component_error': maximum_qpos_error,
              'same_version_replay_passed': termination == 'complete' and maximum_qpos_error <= 1e-8,
              'completed_steps': completed, 'termination': termination,
              'mujoco_version': mujoco.__version__, 'validation_scope': 'recorded_commands_replayed_by_mj_step',
              'note': 'Only initial state is assigned; each later state is integrated. This is not a new task or simulator evaluation.'}
    atomic_json(output, report)
    return report


def export_sample(folder, destination):
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    receipt = verify_sample(folder)
    if destination == folder or destination.is_relative_to(folder):
        raise ValueError('Export destination must be outside the original sample')
    if destination.exists():
        raise ValueError('Export destination exists; no overwrite')
    archive = destination.with_suffix('.zip')
    if archive.exists():
        raise ValueError('ZIP destination exists; no overwrite')
    shutil.copytree(folder, destination)
    if (folder / 'physics_trace.npz').exists():
        atomic_json(destination / 'executed_pose_record.json', executed_pose_record(folder))
    (destination / 'README.md').write_text(
        '# MuJoCo 单手局部抓取结果包\n\n'
        f'本地状态：`{receipt["status"]}`。不代表 Isaac Lab 或完整 Bench2Dex 任务通过。\n\n'
        '- `geometry.xml` / `execution.xml` 的网格路径均为包内相对路径。\n'
        '- `candidate.json` 保存来源、类别条件、具名关节、对象相对位姿和静态诊断。\n'
        '- `execution_report.json` 保存控制器、接触参数、判据和失败原因。\n'
        '- `physics_trace.npz` 保存每个物理步的实际电机目标、腕部力/力矩、扰动力与执行前后状态。\n'
        '- `execution_trace.npz` 是控制周期轨迹；所有新位姿采用米/弧度/wxyz。\n'
        '- `result.json` 记录原始生成身份与文件校验值。物体在重置后为自由动态刚体。\n\n'
        '在 Dexonomy 的 MuJoCo 环境中使用 `tools/bench2dex.py replay-physics <本目录> --output <报告路径>` '
        '重放已记录的实际物理指令。该重放只设置初始状态，后续通过 mj_step 推进；离线逐帧设置状态仅用于图像诊断。\n\n'
        '接触刚度、软指腹扭转摩擦与防滑求解器均是声明的 MuJoCo 局部模型设置，尚未跨模拟器确认。'
        '自由腕控制未包含 UR5 IK、另一只手或完整任务场景；目标 RTX 机器须单独执行 Isaac 验证。\n', encoding='utf-8')
    manifest = {'schema_version': 1, 'original_status': receipt['status'], 'isaaclab_passed': None,
                'files': [{'path': p.relative_to(destination).as_posix(), 'sha256': sha256(p)} for p in sorted(destination.rglob('*')) if p.is_file()]}
    atomic_json(destination / 'bundle_manifest.json', manifest)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(destination.rglob('*')):
            if path.is_file():
                stream.write(path, path.relative_to(destination.parent))
    return {'status': receipt['status'], 'directory': str(destination), 'zip': str(archive),
            'sha256': sha256(archive), 'isaaclab_passed': None}


def executed_pose_record(folder):
    folder = Path(folder)
    verify_sample(folder)
    candidate = json.loads((folder / 'candidate.json').read_text())
    report = json.loads((folder / 'execution_report.json').read_text())
    with np.load(folder / 'execution_trace.npz', allow_pickle=False) as stored:
        controls = {key: stored[key] for key in stored.files}
    with np.load(folder / 'physics_trace.npz', allow_pickle=False) as stored:
        physics = {key: stored[key] for key in stored.files}
    model = mujoco.MjModel.from_xml_path(str(folder / 'execution.xml')); data = mujoco.MjData(model)
    palm = model.body(f'{candidate["side"]}_palm_link').id; obj = model.body('target_object').id
    hand_indices = [int(model.joint(name).qposadr[0]) for name in candidate['joint_names']]
    from .local_grasp import _body_matrix
    poses = {}
    substeps = int(round(report['control_dt_s'] / report['physics_dt_s']))
    for phase in ['approach','close','lift','hold']:
        index = int(np.flatnonzero(controls['phase'] == phase)[-1])
        pindex = int(np.searchsorted(physics['sim_step'], controls['sim_step'][index] + substeps) - 1)
        data.qpos[:] = physics['qpos_after'][pindex]; mujoco.mj_forward(model,data)
        poses[phase] = {'sim_step_after': int(physics['sim_step'][pindex] + 1),
                        'T_object_from_wrist_wxyz': matrix_pose(np.linalg.inv(_body_matrix(data,obj)) @ _body_matrix(data,palm)).tolist(),
                        'hand_qpos_rad': data.qpos[hand_indices].tolist(),
                        'source': 'actual integrated state; not nominal optimization target'}
    return {'schema_version':1,'side':candidate['side'],'requested_category':candidate['category'],
            'category_semantics':'generator condition; actual taxonomy label not independently classified',
            'joint_names':candidate['joint_names'],'object':candidate['object'],'executed_stages':poses,
            'local_dynamic_passed':report['passed'],'validation_scope':'mujoco_hand_only',
            'isaaclab_passed':None,'full_task_passed':None,
            'note':'Executed close/hold poses differ from planned grasp/squeeze targets; phase names remain explicit.'}
