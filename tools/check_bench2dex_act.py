#!/usr/bin/env python3
"""Read prepared data with the original Bench2Dex ACT dataset on CPU.

Run this in a Torch/OpenCV/h5py environment, independently of MuJoCo.
No imitation policy is trained and no weights are downloaded.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import torch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bench2dex-root', type=Path, required=True)
    parser.add_argument('--episode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=3)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('--samples must be positive')
    root = args.bench2dex_root.resolve()
    sys.path.insert(0, str(root))
    source = root / 'policy/ACT/utils.py'
    spec = importlib.util.spec_from_file_location('bench2dex_act_utils', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    episode = str(args.episode.resolve())
    import h5py
    with h5py.File(episode) as f:
        end = int(np.searchsorted(f['time/sim_step'][:], f['meta/homing_start_sim_step'][()]))
        if not np.all(f['frame_valid'][:end]) or not np.all(f['action/action_valid'][:end]) or not np.isfinite(f['action/commanded'][:end]).all():
            raise ValueError('Prepare this episode first; ACT would otherwise fill or consume invalid actions')
        if f['robot/joint_names'].asstr()[:].tolist() != f['action/action_names'].asstr()[:].tolist():
            raise ValueError('Prepare this episode first; ACT does not remap action columns')
    adi = module.get_active_dof_info_for_hdf5(episode)
    if adi is None or adi.robot_key != 'multi_ur5_wuji_with_flange':
        raise ValueError('Original ACT runtime joint mapping could not be loaded')
    stats, max_len = module.get_norm_stats_dex2bench([episode], active_dof_info=adi)
    cameras = ['cam_right_wrist', 'cam_left_wrist', 'cam_stereo_left', 'cam_stereo_right']
    dataset = module.Dex2BenchEpisodicDataset([episode], cameras, stats, max_len, active_dof_info=adi)
    np.random.seed(0)
    shapes = []
    for _ in range(args.samples):
        images, qpos, actions, is_pad = dataset[0]
        if not all(torch.isfinite(t).all().item() for t in (images, qpos, actions)):
            raise ValueError('ACT reader produced non-finite tensors')
        if qpos.shape != (52,) or actions.shape != (max_len, 52) or images.shape != (4, 3, 480, 640):
            raise ValueError('ACT dimensions disagree with selected baseline')
        shapes.append({'images': list(images.shape), 'qpos': list(qpos.shape), 'actions': list(actions.shape),
                       'padding': list(is_pad.shape)})
    import hashlib
    with h5py.File(episode) as f:
        steps = f['time/sim_step'][:]
        effective = int(np.searchsorted(steps, f['meta/homing_start_sim_step'][()]))
        if max_len != effective:
            raise ValueError('Original normalization did not truncate at actual homing')
        values = f['robot/qpos'][:effective]
        np.testing.assert_allclose(stats['qpos_mean'], values.mean(axis=0), rtol=1e-5, atol=1e-6)
    report = {'schema_version': 1, 'reader_path': str(source), 'reader_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'episode': episode, 'camera_names': cameras, 'training_frames': max_len,
              'samples': shapes, 'finite': True, 'actual_reader_passed': True,
              'homing_excluded_from_normalization': True, 'short_training_passed': False,
              'note': 'Tests original ACT dataset and normalization; does not train a policy or prove generated task success'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}))


if __name__ == '__main__':
    main()
