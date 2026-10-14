"""Read-only asset inspection with explicit missing/unconfirmed states."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from .common import file_receipt, git_identity
from .models import URDFModel


def usd_inventory(path: Path) -> dict:
    result = file_receipt(path)
    if not path.is_file():
        return result
    try:
        from pxr import Usd, UsdGeom, UsdPhysics, UsdUtils
        layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(path))
        result['dependencies'] = [file_receipt(Path(layer.realPath)) for layer in layers if layer.realPath]
        result['assets'] = [file_receipt(Path(x)) for x in assets]
        result['unresolved'] = [str(x) for x in unresolved]
        stage = Usd.Stage.Open(str(path))
        result['composition_errors'] = [str(error) for error in stage.GetCompositionErrors()]
        result['meters_per_unit'] = stage.GetMetadata('metersPerUnit')
        result['up_axis'] = str(stage.GetMetadata('upAxis'))
        result['revolute_joints'] = []
        result['rigid_body_properties'] = []
        result['collision_properties'] = []
        result['mesh_extents_local'] = []
        # Robot colliders are authored in instance proxies; plain Traverse()
        # misses them and would falsely report no physical collision geometry.
        for prim in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
            if prim.IsA(UsdPhysics.RevoluteJoint):
                result['revolute_joints'].append({'path': str(prim.GetPath()), 'attributes': {
                    attr.GetName(): str(attr.Get()) for attr in prim.GetAttributes()
                    if attr.GetName().startswith(('physics:', 'drive:'))}})
            if prim.HasAPI(UsdPhysics.MassAPI):
                result['rigid_body_properties'].append({'path': str(prim.GetPath()), 'attributes': {
                    attr.GetName(): str(attr.Get()) for attr in prim.GetAttributes()
                    if attr.GetName().startswith(('physics:', 'physxRigidBody:'))}})
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                result['collision_properties'].append({'path': str(prim.GetPath()), 'attributes': {
                    attr.GetName(): str(attr.Get()) for attr in prim.GetAttributes()
                    if attr.GetName().startswith(('physics:', 'physxCollision:'))}})
            if prim.IsA(UsdGeom.Mesh):
                result['mesh_extents_local'].append({'path': str(prim.GetPath()),
                    'extent': str(UsdGeom.Mesh(prim).GetExtentAttr().Get()),
                    'semantics': 'raw USD mesh-local extent; apply authored transforms, metersPerUnit and scene scale before using physical dimensions'})
        result['dependency_inspection'] = 'passed' if not unresolved else 'unresolved'
    except ImportError:
        result['dependency_inspection'] = 'unavailable_usd_core'
    return result


def inspect_assets(cfg: dict) -> dict:
    bench, root = cfg['bench2dex_root'], cfg['asset_root']
    code_paths = ['robots/multi_ur5_wuji_with_flange.py', 'robots/active_dof_maps.yml',
                  'robots/active_dof_utils.py', 'teleop/hand_cfgs/wuji.yml',
                  'collector/data_collector.py', 'collector/hdf5_writer.py', 'policy/ACT/utils.py']
    report = {'schema_version': 1, 'robot_key': cfg['robot_key'], 'config_sha256': cfg['config_sha256'],
              'bench2dex': {'root': str(bench), **git_identity(bench), 'files': [file_receipt(bench / p) for p in code_paths]},
              'robot_usd': usd_inventory(root / cfg['robot_usd']),
              'robot_urdf': file_receipt(root / cfg['robot_urdf']), 'hands': {}, 'tasks': {},
              'dependencies': {name: importlib.util.find_spec(name) is not None for name in ('mujoco', 'h5py', 'torch', 'isaaclab', 'pxr')}}
    semantics = yaml.safe_load(cfg['semantics'].read_text())
    if report['robot_urdf']['status'] == 'present':
        full_model = URDFModel(root / cfg['robot_urdf'])
        report['robot_urdf']['inventory'] = full_model.inventory()
        usd_joints = {Path(j['path']).name: j for j in report['robot_usd'].get('revolute_joints', [])}
        limit_comparison = []
        import numpy as np
        for name in full_model.moving_names:
            entry = {'joint_name': name, 'usd_found': name in usd_joints}
            if name in usd_joints:
                attributes = usd_joints[name]['attributes']
                urdf_limits = full_model.limits([name])[0]
                usd_limits = np.deg2rad([float(attributes['physics:lowerLimit']), float(attributes['physics:upperLimit'])])
                entry.update(urdf_limits_rad=urdf_limits.tolist(), usd_limits_rad=usd_limits.tolist(),
                             max_difference_rad=float(np.max(np.abs(urdf_limits - usd_limits))))
            limit_comparison.append(entry)
        report['urdf_usd_joint_limit_comparison'] = limit_comparison
        report['urdf_usd_limit_names_complete'] = set(full_model.moving_names) == set(usd_joints)
        report['mount_transforms'] = {side: {
            'end_effector_link': semantics['sides'][side]['end_effector_link'],
            'palm_link': semantics['sides'][side]['palm_link'],
            'T_ee_from_palm': full_model.fixed_transform(semantics['sides'][side]['end_effector_link'], semantics['sides'][side]['palm_link']).tolist(),
            'status': 'urdf_static_verified_runtime_pending',
        } for side in ('right', 'left')}
    for side, rel in cfg['hand_urdf'].items():
        path = root / rel
        hand = file_receipt(path)
        if path.is_file():
            try:
                model = URDFModel(path)
                hand = model.inventory()
                expected = [j['urdf_name'] for j in semantics['sides'][side]['joints']]
                hand['mapping_complete'] = set(model.moving_names) == set(expected)
                hand['joint_limits_rad'] = model.limits(expected).tolist()
                hand['status'] = 'present_version_unconfirmed'
            except (ValueError, KeyError) as exc:
                hand['status'] = 'invalid'
                hand['error'] = str(exc)
        report['hands'][side] = hand
    for task in cfg['tasks']:
        path = bench / 'scenes' / f'{task}.yaml'
        entry = {'scene': file_receipt(path), 'objects': {}, 'demos': {}}
        if path.is_file():
            scene = yaml.safe_load(path.read_text())
            entry['instruction'] = scene['description']
            entry['table'] = scene['table']
            entry['stages'] = scene.get('metrics', {}).get('stages', [])
            entry['terminal'] = scene.get('metrics', {}).get('terminal')
            for key, asset in scene.get('assets', {}).items():
                raw_parts = Path(asset['path']).parts
                if 'dex2bench_dataset' not in raw_parts:
                    raise ValueError(f'Unrecognized scene asset root: {asset["path"]}')
                rel = Path(*raw_parts[raw_parts.index('dex2bench_dataset') + 1:])
                entry['objects'][key] = {**usd_inventory(root / rel), 'scale_xyz': asset['scale'],
                                         'scale_semantics': 'scene multiplier, not measured diameter'}
        for kind in ('origin-generalization', 'replay-generalization'):
            directory = cfg['demo_root'] / 'dataset' / task / kind
            files = sorted(directory.glob('*.hdf5')) if directory.is_dir() else []
            entry['demos'][kind] = {'path': str(directory), 'count': len(files),
                                    'status': 'present' if files else 'missing'}
        report['tasks'][task] = entry
    # Asset existence cannot grant M0 acceptance without actual runtime comparisons.
    report['m0_accepted'] = False
    report['acceptance_pending'] = ['USD/URDF geometry and dynamics comparison', 'Isaac Lab joint_names capture',
                                    'Left/right URDF/MuJoCo/Isaac Lab fixed-posture FK comparison',
                                    'Palm/flange transforms and physical contact surface calibration']
    report['missing'] = []
    def walk(value):
        if isinstance(value, dict):
            if value.get('status') == 'missing' and 'path' in value:
                report['missing'].append(value['path'])
            for key, child in value.items():
                if key != 'missing':
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(report)
    report['missing'] = sorted(set(report['missing']))
    return report


def asset_markdown(report: dict) -> str:
    lines = ['# Bench2Dex / Wuji 资产检查', '', f'Bench2Dex commit: `{report["bench2dex"]["commit"]}`', '',
             f'M0 验收：未完成。缺失路径：{len(report["missing"])}。', '', '| 资源 | 状态 |', '| --- | --- |',
             f'| 原始机器人 USD | {report["robot_usd"]["status"]} |',
             f'| 原始机器人 URDF | {report["robot_urdf"]["status"]} |']
    lines += [f'| {side} hand | {hand["status"]} |' for side, hand in report['hands'].items()]
    if 'urdf_usd_joint_limit_comparison' in report:
        differences = [row.get('max_difference_rad', 0) for row in report['urdf_usd_joint_limit_comparison']]
        lines += ['', f'原始 URDF / USD 限位对照最大差：`{max(differences):.3g} rad`。',
                  '本项为静态检查，不代替运行时 FK、碰撞与动力学验收。']
    lines += ['', '## 原始 USD 的独立解析诊断', '',
              f'未解析外部依赖：`{report["robot_usd"].get("unresolved", [])}`；组合错误：{len(report["robot_usd"].get("composition_errors", []))}。',
              '材质 MDL 依赖可能由 Isaac Sim 内置解析器提供，须在目标环境核实。']
    lines += ['', '## 待验收', ''] + [f'- {item}' for item in report['acceptance_pending']]
    lines += ['', '## 缺失资源', ''] + [f'- `{item}`' for item in report['missing']]
    lines += ['', '详细关节、网格、USD 依赖和任务尺度见同目录 JSON。文件存在仅代表资产可读取。', '']
    return '\n'.join(lines)
