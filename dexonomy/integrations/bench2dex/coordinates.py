"""Explicit name-based joint and SI/wxyz pose conversion boundaries."""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


def joint_indices(source_names, target_names) -> np.ndarray:
    source, target = list(source_names), list(target_names)
    if len(source) != len(set(source)) or len(target) != len(set(target)):
        raise ValueError('Duplicate joint names')
    missing = set(target) - set(source)
    if missing:
        raise ValueError(f'Missing joint names: {sorted(missing)}')
    lookup = {name: i for i, name in enumerate(source)}
    return np.asarray([lookup[name] for name in target], dtype=np.intp)


def reorder_joints(values, source_names, target_names):
    values = np.asarray(values)
    if values.shape[-1] != len(source_names):
        raise ValueError('Joint array dimension disagrees with source names')
    return values[..., joint_indices(source_names, target_names)]


def pose_matrix(pose_wxyz) -> np.ndarray:
    pose = np.asarray(pose_wxyz, dtype=float)
    if pose.shape != (7,) or not np.isfinite(pose).all():
        raise ValueError('Pose must be seven finite values in metres/wxyz')
    if abs(np.linalg.norm(pose[3:]) - 1) > 1e-5:
        raise ValueError('Quaternion must have unit norm')
    out = np.eye(4)
    out[:3, :3] = Rotation.from_quat(pose[[4, 5, 6, 3]]).as_matrix()
    out[:3, 3] = pose[:3]
    return out


def matrix_pose(matrix) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Transform must be a finite 4x4 matrix')
    rot = matrix[:3, :3]
    if not np.allclose(matrix[3], [0, 0, 0, 1]) or not np.allclose(rot.T @ rot, np.eye(3), atol=1e-6) or not np.isclose(np.linalg.det(rot), 1):
        raise ValueError('Transform is not a rigid SE(3) transform')
    quat = Rotation.from_matrix(rot).as_quat()
    return np.r_[matrix[:3, 3], quat[[3, 0, 1, 2]]]


def delta_pose(a, b) -> tuple[float, float]:
    """Return translation in metres and shortest rotation in radians."""
    A, B = pose_matrix(a), pose_matrix(b)
    return float(np.linalg.norm(A[:3, 3] - B[:3, 3])), float(Rotation.from_matrix(A[:3, :3].T @ B[:3, :3]).magnitude())


def scene_wrist_pose(T_world_from_object, T_object_from_wrist):
    return matrix_pose(pose_matrix(T_world_from_object) @ pose_matrix(T_object_from_wrist))


def replace_named_targets(previous, runtime_names, replacement: dict):
    """Merge arm IK and finger targets by name; never expand a free wrist as joints."""
    previous = np.asarray(previous, dtype=float)
    if previous.shape != (len(runtime_names),) or not np.isfinite(previous).all():
        raise ValueError('Expected one finite target per runtime joint')
    result = previous.copy()
    idx = joint_indices(runtime_names, replacement.keys())
    values = np.asarray(list(replacement.values()), dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('Non-finite replacement command')
    result[idx] = values
    return result
