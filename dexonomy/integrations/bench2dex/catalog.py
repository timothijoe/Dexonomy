"""Versioned per-task asset roles, keeping unknown semantics explicitly pending."""
from collections import defaultdict
from pathlib import Path

import yaml

from .common import file_receipt, git_identity, sha256


OFFICIAL_TASK_IDS = {3, 6, 7, 8, 9, 12, 21, 22, 24, 26, 27, 32, 34, 42, 43, 44, 51, 60, 61, 62, 64, 67, 73, 76, 79, 80}


def object_relative_path(path):
    parts = Path(path).parts
    if 'Objects' not in parts:
        raise ValueError(f'Unrecognized object asset URI: {path}')
    return Path(*parts[parts.index('Objects'):])


def suggested_role(folder, key, body_type):
    if body_type == 'articulation':
        return 'articulated_device', ['part_contact', 'constrained_motion']
    if folder.startswith(('332_', '333_')):
        return 'support_fixture', ['support']
    if folder.startswith('326_'):
        return 'assembly_part', ['grasp', 'orient', 'align', 'place']
    if folder.startswith('201_'):
        return 'adjustable_equipment', ['support', 'adjust_pose']
    if folder.startswith(('024_', '025_', '029_', '065-', '129_', '130_', '154_', '167_', '169_', '183_', '194_')) or 'bowl' in key or 'pot' in key:
        return 'container_or_support', ['task_role_review_required']
    if folder.startswith(('030_', '031_', '033_', '042_', '043_', '044_', '048_', '147_', '189_')) or 'ladle' in key:
        return 'tool', ['functional_grasp', 'task_specific_motion']
    return 'movable_object', ['task_role_review_required']


def build_catalog(cfg, roles_path):
    roles_path = Path(roles_path)
    roles = yaml.safe_load(roles_path.read_text())
    if roles.get('schema_version') != 1:
        raise ValueError('Unsupported role schema')
    assets = defaultdict(list)
    tasks = []
    for path in sorted((cfg['bench2dex_root'] / 'scenes').glob('*.yaml')):
        if int(path.name.split('_', 1)[0]) not in OFFICIAL_TASK_IDS:
            continue
        scene = yaml.safe_load(path.read_text())
        declared = roles['tasks'].get(path.stem, {})
        unknown_keys = set(declared) - set(scene['assets'])
        if unknown_keys:
            raise ValueError(f'Role declaration does not match scene: {sorted(unknown_keys)}')
        entries = []
        for key, desc in scene['assets'].items():
            rel = object_relative_path(desc['path'])
            folder = rel.parts[1]
            instances = [o['id'] for o in scene.get('objects', []) if o.get('asset') == key]
            fallback_role, fallback_skills = suggested_role(folder, key, desc.get('body_type'))
            role = declared.get(key, {'role': fallback_role, 'skills': fallback_skills, 'required_sides': [], 'generation': 'pending_review'})
            entry = {'task': path.stem, 'asset_key': key, 'object_directory': folder, 'asset_path': rel.as_posix(),
                     'scale_xyz': desc['scale'], 'body_type': desc.get('body_type'), 'instance_ids': instances,
                     **role, 'role_status': 'declared_development_role' if key in declared else 'heuristic_pending_review',
                     'source': file_receipt(cfg['asset_root'] / rel), 'execution_verified': False}
            entries.append(entry)
            assets[folder].append(entry)
        tasks.append({'task': path.stem, 'instruction': scene['description'], 'scene_sha256': sha256(path),
                      'stages': scene.get('metrics', {}).get('stages', []), 'assets': entries})
    return {'schema_version': 1, 'bench2dex': git_identity(cfg['bench2dex_root']), 'roles_sha256': sha256(roles_path),
            'task_count': len(tasks), 'object_directory_count': len(assets),
            'usd_entry_count': len({e['asset_path'] for entries in assets.values() for e in entries}),
            'tasks': tasks, 'object_directories': dict(assets),
            'note': 'Unreviewed roles remain pending; catalog rows are not executed skills or success labels'}


def catalog_markdown(catalog):
    lines = ['# Bench2Dex 任务资产与动作覆盖清单', '', f'任务 {catalog["task_count"]}；资产目录 {catalog["object_directory_count"]}；USD 入口 {catalog["usd_entry_count"]}。', '',
             '首版 21/27 为明确配置的开发角色，其余为待检查建议；全部尚无执行标签。', '',
             '| 任务 | 资产 | 角色 | 生成方式 | 状态 |', '| --- | --- | --- | --- | --- |']
    for task in catalog['tasks']:
        for e in task['assets']:
            lines.append(f'| {task["task"]} | {e["asset_key"]} | {e["role"]} | {e["generation"]} | {e["role_status"]} |')
    return '\n'.join(lines) + '\n'
