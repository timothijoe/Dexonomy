"""Strict episode validation and lossless action alignment for the ACT reader.

No observation-as-action fallback. Preparation may remove an initial actionless
observation, reorder actions by explicit names, and encode raw RGB to JPEG.
Homing frames and their real sim_step boundary are retained for upstream ACT.
"""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import tempfile

import h5py
import numpy as np
from PIL import Image

from .common import atomic_json, sha256
from .coordinates import joint_indices


def _text(value):
    return value.decode('utf-8') if isinstance(value, bytes) else str(value)


def _names(ds):
    return [_text(x) for x in ds[:]]


def _jpeg_ok(value):
    try:
        with Image.open(BytesIO(bytes(value))) as im:
            im.load()
            return im.format == 'JPEG' and im.mode == 'RGB'
    except (ValueError, OSError):
        return False


def validate_episode(path, expected_names, cameras, *, require_act=False) -> dict:
    path = Path(path)
    errors, warnings = [], []
    report = {'schema_version': 1, 'path': str(path.resolve()), 'sha256': sha256(path),
              'errors': errors, 'warnings': warnings, 'act_ready': False,
              'execution_verified': False}
    with h5py.File(path) as f:
        required = ['robot/joint_names', 'robot/qpos', 'action/action_names', 'action/commanded',
                    'action/action_valid', 'action/control_mode', 'action/action_type', 'frame_valid',
                    'time/sim_step', 'meta/homing_start_sim_step', 'meta/robot_key']
        missing = [key for key in required if key not in f]
        if missing:
            errors.append(f'Missing required fields: {missing}')
            report['valid'] = False
            return report
        qpos, action = f['robot/qpos'][:], f['action/commanded'][:]
        names, anames = _names(f['robot/joint_names']), _names(f['action/action_names'])
        if qpos.ndim != 2 or action.ndim != 2:
            errors.append('qpos and commanded must have shape [T,D]')
            report['valid'] = False
            return report
        n = len(qpos)
        report.update(frame_count=n, joint_names=names, action_names=anames)
        try:
            joint_indices(names, expected_names)
            joint_indices(anames, expected_names)
            if set(names) != set(expected_names) or set(anames) != set(expected_names):
                raise ValueError('Unexpected joints for target robot')
        except ValueError as exc:
            errors.append(str(exc))
        if qpos.shape != (n, len(names)) or action.shape != (n, len(anames)) or n < 2:
            errors.append('Episode length/dimensions disagree with names')
            report['valid'] = False
            return report
        report['action_reorder_needed'] = names != anames
        if report['action_reorder_needed']:
            warnings.append('ACT ignores action_names; reorder commanded to robot/joint_names before training')
        scalars = {'meta/robot_key': 'multi_ur5_wuji_with_flange', 'action/control_mode': 'joint_position', 'action/action_type': 'absolute'}
        for key, expected in scalars.items():
            if _text(f[key][()]) != expected:
                errors.append(f'{key} must equal {expected}')
        steps = f['time/sim_step'][:]
        fv, av = f['frame_valid'][:], f['action/action_valid'][:]
        if steps.shape != (n,) or fv.shape != (n,) or av.shape != (n,):
            errors.append('Time and validity dimensions disagree')
            report['valid'] = False
            return report
        if fv.dtype != np.bool_ or av.dtype != np.bool_:
            errors.append('Frame/action validity masks must be boolean')
        if not np.issubdtype(steps.dtype, np.integer) or np.any(np.diff(steps) <= 0):
            errors.append('sim_step must contain strictly increasing integer steps')
        homing = f['meta/homing_start_sim_step'][()]
        if np.asarray(homing).shape != () or not np.issubdtype(np.asarray(homing).dtype, np.integer):
            errors.append('homing_start_sim_step must be an integer scalar')
            report['valid'] = False
            return report
        end = int(np.searchsorted(steps, homing))
        report['training_end_index'] = end
        report['homing_start_sim_step'] = int(homing)
        if not 0 < end < n:
            errors.append('Actual homing boundary must lie inside recorded episode')
        initial = int(n > 0 and not av[0])
        report['initial_actionless_frames'] = initial
        if initial:
            warnings.append('Initial actionless observation must be excluded from ACT training')
        valid_actions = action[av.astype(bool)]
        if not np.isfinite(qpos[fv.astype(bool)]).all() or not np.isfinite(valid_actions).all():
            errors.append('Non-finite values on valid frames/actions')
        if not np.all(fv[initial:end]) or not np.all(av[initial:end]):
            errors.append('Invalid internal training frames/actions; ACT does not honor these masks')
        report['cameras'] = {}
        for name in cameras:
            group = f.get('cameras/' + name)
            key = 'cameras/' + name + '/rgb'
            if group is None or key not in f:
                errors.append(f'Missing RGB camera: {name}')
                continue
            ds = f[key]
            encoding = 'raw_rgb' if ds.ndim == 4 and ds.shape[-1] == 3 and ds.dtype == np.uint8 else 'jpeg' if ds.ndim == 1 and h5py.check_dtype(vlen=ds.dtype) is not None else 'unknown'
            report['cameras'][name] = {'shape': list(ds.shape), 'encoding': encoding}
            if ds.shape[0] != n or encoding == 'unknown':
                errors.append(f'Bad RGB shape/encoding: {name}')
            elif encoding == 'jpeg':
                indices = range(initial, end) if require_act else sorted(set([initial, max(initial, end - 1)]))
                for idx in indices:
                    if idx < n and not _jpeg_ok(ds[idx]):
                        errors.append(f'Invalid JPEG: {name} frame {idx}')
            else:
                warnings.append(f'{name}: raw RGB requires JPEG encoding for current ACT reader')
            for field, shape in [('intrinsic', (3, 3)), ('extrinsic_world_from_cam', (n, 4, 4))]:
                if field not in group or group[field].shape != shape or not np.isfinite(group[field][:]).all():
                    errors.append(f'Invalid camera calibration: {name}/{field}')
        for field in ('meta/physics_dt', 'meta/step_stride', 'meta/instruction'):
            if field not in f:
                errors.append(f'Missing timing/instruction: {field}')
        if 'meta/physics_dt' in f and (not np.isfinite(f['meta/physics_dt'][()]) or f['meta/physics_dt'][()] <= 0):
            errors.append('physics_dt must be positive')
        if 'meta/step_stride' in f:
            stride = f['meta/step_stride'][()]
            if stride <= 0 or int(stride) != stride:
                errors.append('step_stride must be a positive integer')
            elif end > initial + 1 and np.any(np.diff(steps[initial:end]) != stride):
                errors.append('sim_step spacing disagrees with declared control stride')
        report['declared_success'] = None
        if 'meta/success' in f:
            success = f['meta/success'][()]
            if not isinstance(success, (bool, np.bool_)):
                errors.append('meta/success must be a boolean scalar, not a string or array')
            else:
                report['declared_success'] = bool(success)
        report['jpeg_validation'] = 'all_training_frames' if require_act else 'boundary_frames_only'
        report['act_ready'] = not errors and initial == 0 and names == anames and all(v['encoding'] == 'jpeg' for v in report['cameras'].values()) and len(report['cameras']) == len(cameras)
        if require_act and not report['act_ready']:
            errors.append('Not directly consumable by the current ACT reader')
    report['valid'] = not errors
    report['alignment_note'] = 'Structural validation only; one-frame offset needs actual action/response evidence'
    return report


def prepare_episode(source, destination, expected_names, cameras, *, check_only=False, resume=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Preparation cannot overwrite the source episode')
    report = validate_episode(source, expected_names, cameras)
    if not report['valid']:
        raise ValueError('; '.join(report['errors']))
    if report['declared_success'] is not True:
        raise ValueError('First-version BC preparation requires an episode declared successful by its source evaluator')
    identity = {'source_sha256': report['sha256'], 'schema_version': 1,
                'camera_names': list(cameras), 'expected_joint_names': list(expected_names),
                'jpeg_quality': 95, 'preparation_version': 1}
    receipt = destination.with_suffix(destination.suffix + '.provenance.json')
    if check_only:
        return {'identity': identity, 'check_only': True, 'output_exists': destination.exists(), 'inspection': report}
    if destination.exists():
        import json
        prior = json.loads(receipt.read_text()) if receipt.exists() else {}
        if resume and prior.get('identity') == identity and prior.get('output_sha256') == sha256(destination):
            return prior
        raise ValueError('Output exists or resume identity/checksum mismatch')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(dir=destination.parent, suffix='.hdf5')
    os.close(fd)
    tmp = Path(tmpname)
    start, n = report['initial_actionless_frames'], report['frame_count']
    try:
        with h5py.File(source) as src, h5py.File(tmp, 'w') as dst:
            # Clone groups and datasets once. Bound RGB memory to one frame, and
            # avoid copying then deleting large HDF5 datasets (which leaves holes).
            def clone_group(source_group, target_group):
                for key, value in source_group.attrs.items():
                    target_group.attrs[key] = value
                for key, ds in source_group.items():
                    if isinstance(ds, h5py.Group):
                        clone_group(ds, target_group.create_group(key))
                        continue
                    name = ds.name.lstrip('/')
                    per_frame = ds.ndim > 0 and ds.shape[0] == n
                    if name.startswith('meta/') or name.endswith(('/joint_names', '/action_names')):
                        per_frame = False
                    if name.startswith('cameras/') and name.split('/')[-1] not in ('rgb', 'depth_m', 'depth_semantics', 'extrinsic_world_from_cam'):
                        per_frame = False
                    offset = start if per_frame else 0
                    is_raw = name.endswith('/rgb') and name.split('/')[1] in report['cameras'] and report['cameras'][name.split('/')[1]]['encoding'] == 'raw_rgb'
                    if is_raw:
                        new = target_group.create_dataset(key, (n - start,), dtype=h5py.vlen_dtype(np.dtype('uint8')))
                        for i in range(n - start):
                            stream = BytesIO()
                            Image.fromarray(ds[i + start]).save(stream, format='JPEG', quality=95)
                            new[i] = np.frombuffer(stream.getvalue(), dtype=np.uint8)
                    elif per_frame:
                        new = target_group.create_dataset(key, shape=(n - start, *ds.shape[1:]), dtype=ds.dtype,
                                                          compression=ds.compression, compression_opts=ds.compression_opts)
                        vlen = h5py.check_dtype(vlen=ds.dtype)
                        if vlen is not None and vlen not in (str, bytes):
                            # Numeric vlen arrays must be assigned as scalar
                            # elements; a one-row slice can broadcast as 2-D.
                            for i in range(n - start):
                                new[i] = ds[i + offset]
                        else:
                            batch = 1 if name.endswith('/rgb') or name.endswith('/depth_m') else 128
                            for i in range(0, n - start, batch):
                                stop = min(i + batch, n - start)
                                values = ds[i + offset:stop + offset]
                                if name == 'action/commanded':
                                    values = values[:, joint_indices(report['action_names'], report['joint_names'])]
                                new[i:stop] = values
                    else:
                        new = target_group.create_dataset(key, data=ds[()], dtype=ds.dtype)
                    for attr, value in ds.attrs.items():
                        new.attrs[attr] = value
            clone_group(src, dst)
            del dst['action/action_names']
            dst.create_dataset('action/action_names', data=np.asarray(report['joint_names'], dtype=h5py.string_dtype()))
            # Update duplicate action metadata to match actual arrays.
            for key, value in [('frame_count', n - start), ('action_names', report['joint_names'])]:
                if key in dst['meta']:
                    del dst['meta'][key]
                import json
                dst['meta'].create_dataset(key, data=(n - start) if key == 'frame_count' else json.dumps(value), dtype=None if key == 'frame_count' else h5py.string_dtype())
            if 'time/frame_index' in dst:
                dst['time/frame_index'][:] = np.arange(n - start)
            if 'episode/is_first' in dst:
                dst['episode/is_first'][:] = False
                dst['episode/is_first'][0] = True
            if any(info['encoding'] == 'raw_rgb' for info in report['cameras'].values()):
                if 'rgb_encoding' in dst['meta']:
                    del dst['meta/rgb_encoding']
                dst['meta'].create_dataset('rgb_encoding', data='jpeg', dtype=h5py.string_dtype())
            extra = dst.require_group('dexonomy')
            if 'source_frame_index' in extra:
                raise ValueError('Episode was already prepared; use its original source')
            extra.create_dataset('source_frame_index', data=np.arange(start, n, dtype=np.int64))
            extra.create_dataset('source_sha256', data=report['sha256'], dtype=h5py.string_dtype())
            extra.create_dataset('preparation_version', data=1)
        checked = validate_episode(tmp, expected_names, cameras, require_act=True)
        if not checked['valid']:
            raise ValueError('Prepared episode failed validation: ' + '; '.join(checked['errors']))
        os.replace(tmp, destination)
    finally:
        if tmp.exists():
            tmp.unlink()
    result = {'identity': identity, 'output_sha256': sha256(destination), 'source': str(source),
              'output': str(destination), 'removed_initial_frames': start,
              'training_frames': report['training_end_index'] - start,
              'homing_start_sim_step': report['homing_start_sim_step'],
              'changes': ['Remove initial actionless observation if present', 'Align action columns by joint names',
                          'Encode raw RGB as JPEG if present', 'Preserve real homing and sim_step alignment'],
              'execution_verified': False, 'purpose': 'ACT storage compatibility; not generated task success'}
    atomic_json(receipt, result)
    return result
