"""Regression checks for model identity, units, action ordering and ACT boundaries."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np
from PIL import Image

from dexonomy.integrations.bench2dex.coordinates import (delta_pose, joint_indices,
    matrix_pose, pose_matrix, reorder_joints, replace_named_targets, scene_wrist_pose)
from dexonomy.integrations.bench2dex.episodes import prepare_episode, validate_episode
from dexonomy.integrations.bench2dex.models import URDFModel
from dexonomy.integrations.bench2dex.provenance import verify_resources
from dexonomy.integrations.bench2dex.common import atomic_json, sha256
from dexonomy.integrations.bench2dex.runtime import capture_pose, compare_runtime


class CoordinatesTest(unittest.TestCase):
    def test_joint_reorder_with_arbitrary_runtime_order(self):
        np.testing.assert_array_equal(reorder_joints([[2, 1, 3]], ['b', 'a', 'c'], ['a', 'b']), [[1, 2]])

    def test_duplicate_and_missing_joint_names_rejected(self):
        for source, target in [(['a', 'a'], ['a']), (['a'], ['b']), (['a'], ['a', 'a'])]:
            with self.assertRaises(ValueError):
                joint_indices(source, target)

    def test_rotation_unit_is_radians_and_quaternion_sign_invariant(self):
        a = [0, 0, 0, 1, 0, 0, 0]
        b = [0, 0, 0, np.cos(np.pi / 4), 0, 0, np.sin(np.pi / 4)]
        self.assertAlmostEqual(delta_pose(a, b)[1], np.pi / 2)
        self.assertAlmostEqual(delta_pose(b, [*b[:3], *(-np.asarray(b[3:]))])[1], 0)

    def test_object_relative_wrist_transform(self):
        obj = [1, 0, 0, np.sqrt(.5), 0, 0, np.sqrt(.5)]
        wrist = [1, 0, 0, 1, 0, 0, 0]
        world = scene_wrist_pose(obj, wrist)
        np.testing.assert_allclose(world[:3], [1, 1, 0], atol=1e-12)
        np.testing.assert_allclose(pose_matrix(matrix_pose(pose_matrix(world))), pose_matrix(world), atol=1e-12)

    def test_invalid_pose_and_reflection_rejected(self):
        with self.assertRaises(ValueError):
            pose_matrix([0, 0, 0, 2, 0, 0, 0])
        with self.assertRaises(ValueError):
            matrix_pose(np.diag([-1, 1, 1, 1]))

    def test_named_action_merge_preserves_other_arm(self):
        np.testing.assert_array_equal(replace_named_targets([1, 2, 3], ['left', 'right', 'finger'], {'finger': .5}), [1, 2, .5])
        with self.assertRaises(ValueError):
            replace_named_targets([1, 2], ['left', 'right'], {'wrist_x': 1})


class EpisodeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'source.hdf5'
        self.output = self.root / 'prepared.hdf5'
        self.expected = ['right', 'left']
        self.cameras = ['cam']
        self.fixture()

    def fixture(self):
        n = 8
        with h5py.File(self.source, 'w') as f:
            strings = h5py.string_dtype()
            f.create_dataset('robot/joint_names', data=self.expected, dtype=strings)
            f.create_dataset('robot/qpos', data=np.zeros((n, 2)))
            f.create_dataset('action/action_names', data=['left', 'right'], dtype=strings)
            a = np.tile([20., 10.], (n, 1)); a[0] = np.nan
            f.create_dataset('action/commanded', data=a)
            f.create_dataset('action/action_valid', data=[False, True, True, True, True, True, True, False])
            f.create_dataset('action/control_mode', data='joint_position', dtype=strings)
            f.create_dataset('action/action_type', data='absolute', dtype=strings)
            f.create_dataset('frame_valid', data=np.ones(n, dtype=bool))
            f.create_dataset('time/sim_step', data=[0, 1, 4, 7, 10, 13, 16, 19])
            f.create_dataset('time/frame_index', data=np.arange(n))
            f.create_dataset('meta/homing_start_sim_step', data=16)
            f.create_dataset('meta/robot_key', data='multi_ur5_wuji_with_flange', dtype=strings)
            f.create_dataset('meta/physics_dt', data=1/60)
            f.create_dataset('meta/step_stride', data=3)
            f.create_dataset('meta/instruction', data='Put all four balls in box', dtype=strings)
            f.create_dataset('meta/success', data=True)
            f.create_dataset('cameras/cam/rgb', data=np.full((n, 8, 8, 3), 123, dtype=np.uint8))
            f.create_dataset('cameras/cam/intrinsic', data=np.eye(3))
            f.create_dataset('cameras/cam/extrinsic_world_from_cam', data=np.tile(np.eye(4), (n, 1, 1)))
            f.create_dataset('episode/is_first', data=np.arange(n) == 0)
            f.create_dataset('episode/success', data=np.arange(n) == n - 1)

    def inspect(self, **kwargs):
        return validate_episode(self.source, self.expected, self.cameras, **kwargs)

    def test_source_valid_but_not_act_ready(self):
        r = self.inspect()
        self.assertTrue(r['valid']); self.assertFalse(r['act_ready'])
        self.assertEqual(r['training_end_index'], 6)

    def test_preparation_preserves_actions_and_real_homing(self):
        original_hash = sha256(self.source)
        r = prepare_episode(self.source, self.output, self.expected, self.cameras)
        self.assertEqual(r['training_frames'], 5)
        with h5py.File(self.output) as f:
            np.testing.assert_array_equal(f['action/commanded'][0], [10, 20])
            np.testing.assert_array_equal(f['time/sim_step'][:], [1, 4, 7, 10, 13, 16, 19])
            self.assertEqual(f['meta/homing_start_sim_step'][()], 16)
            self.assertEqual(f['meta/frame_count'][()], 7)
            np.testing.assert_array_equal(f['dexonomy/source_frame_index'][:], np.arange(1, 8))
            self.assertEqual(f['cameras/cam/rgb'].ndim, 1)
        self.assertEqual(sha256(self.source), original_hash)
        self.assertTrue(validate_episode(self.output, self.expected, self.cameras, require_act=True)['valid'])

    def test_internal_invalid_action_rejected_not_filled_from_qpos(self):
        with h5py.File(self.source, 'r+') as f:
            f['action/action_valid'][3] = False
        self.assertFalse(self.inspect()['valid'])
        with self.assertRaises(ValueError):
            prepare_episode(self.source, self.output, self.expected, self.cameras)

    def test_nonfinite_valid_action_rejected(self):
        with h5py.File(self.source, 'r+') as f:
            f['action/commanded'][2, 0] = np.nan
        self.assertFalse(self.inspect()['valid'])

    def test_wrong_action_frame_count_returns_diagnostic(self):
        with h5py.File(self.source, 'r+') as f:
            del f['action/commanded']
            f.create_dataset('action/commanded', data=np.zeros((7, 2)))
        self.assertFalse(self.inspect()['valid'])

    def test_success_string_not_interpreted_as_true(self):
        with h5py.File(self.source, 'r+') as f:
            del f['meta/success']
            f.create_dataset('meta/success', data='False', dtype=h5py.string_dtype())
        self.assertFalse(self.inspect()['valid'])

    def test_bad_homing_boundary_rejected(self):
        for value in [-1, 999]:
            with h5py.File(self.source, 'r+') as f:
                f['meta/homing_start_sim_step'][()] = value
            self.assertFalse(self.inspect()['valid'])

    def test_wrong_robot_joint_and_control_mode_rejected(self):
        with h5py.File(self.source, 'r+') as f:
            f['action/control_mode'][()] = 'velocity'
            f['robot/joint_names'][0] = 'wuji2_finger'
        self.assertFalse(self.inspect()['valid'])

    def test_one_step_time_offset_or_stride_discontinuity_rejected(self):
        with h5py.File(self.source, 'r+') as f:
            f['time/sim_step'][3] = 8
        self.assertFalse(self.inspect()['valid'])

    def test_resume_checks_source_configuration_and_output_identity(self):
        prepare_episode(self.source, self.output, self.expected, self.cameras)
        prepare_episode(self.source, self.output, self.expected, self.cameras, resume=True)
        with h5py.File(self.output, 'r+') as f:
            f['action/commanded'][1, 0] += 1
        with self.assertRaises(ValueError):
            prepare_episode(self.source, self.output, self.expected, self.cameras, resume=True)

    def test_check_only_does_not_write_and_overwrite_forbidden(self):
        prepare_episode(self.source, self.output, self.expected, self.cameras, check_only=True)
        self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            prepare_episode(self.source, self.source, self.expected, self.cameras)

    def test_check_only_can_inspect_an_existing_output_without_changing_it(self):
        prepare_episode(self.source, self.output, self.expected, self.cameras)
        previous = sha256(self.output)
        result = prepare_episode(self.source, self.output, self.expected, self.cameras, check_only=True)
        self.assertTrue(result['output_exists'])
        self.assertEqual(previous, sha256(self.output))

    def test_corrupt_internal_jpeg_detected_in_strict_mode(self):
        prepare_episode(self.source, self.output, self.expected, self.cameras)
        with h5py.File(self.output, 'r+') as f:
            f['cameras/cam/rgb'][2] = np.array([0, 1, 2], dtype=np.uint8)
        self.assertFalse(validate_episode(self.output, self.expected, self.cameras, require_act=True)['valid'])

    def test_existing_jpeg_vlen_bytes_preserved_exactly(self):
        stream = BytesIO(); Image.new('RGB', (8, 8), 'red').save(stream, format='JPEG')
        value = np.frombuffer(stream.getvalue(), dtype=np.uint8)
        with h5py.File(self.source, 'r+') as f:
            del f['cameras/cam/rgb']
            d = f.create_dataset('cameras/cam/rgb', (8,), dtype=h5py.vlen_dtype(np.dtype('uint8')))
            for i in range(8):
                d[i] = value
        prepare_episode(self.source, self.output, self.expected, self.cameras)
        with h5py.File(self.output) as f:
            self.assertEqual(bytes(f['cameras/cam/rgb'][3]), stream.getvalue())

    def test_failed_trajectory_not_prepared_for_bc(self):
        with h5py.File(self.source, 'r+') as f:
            f['meta/success'][()] = False
        with self.assertRaises(ValueError):
            prepare_episode(self.source, self.output, self.expected, self.cameras)


class ModelTest(unittest.TestCase):
    def test_known_urdf_axis_origin_and_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'hand.urdf'
            path.write_text('<robot name="hand"><link name="palm"/><link name="tip"/>'
                            '<joint name="bend" type="revolute"><parent link="palm"/><child link="tip"/>'
                            '<origin xyz="0 0 1" rpy="0 0 0"/><axis xyz="0 1 0"/>'
                            '<limit lower="0.1" upper="1.5"/></joint></robot>')
            m = URDFModel(path)
            T = m.forward({'bend': np.pi / 2})['tip']
            np.testing.assert_allclose(T[:3, 3], [0, 0, 1])
            np.testing.assert_allclose(T[:3, :3] @ [0, 0, 1], [1, 0, 0], atol=1e-12)
            np.testing.assert_allclose(m.limits(['bend']), [[.1, 1.5]])
            with self.assertRaises(ValueError):
                m.forward({})
            with self.assertRaises(ValueError):
                m.fixed_transform('palm', 'tip')

    def test_official_manifest_hash_mismatch_and_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); asset = root / 'robot.urdf'; asset.write_text('original')
            payload = {'schema_version': 1, 'resources': {'assets': {'repo_id': 'Bench2Dex/Assets', 'revision': 'fixed',
                'files': [{'path': 'robot.urdf', 'hash_type': 'sha256', 'hash': sha256(asset)}]}}}
            manifest = root / 'receipt.json'; atomic_json(manifest, payload)
            self.assertTrue(verify_resources(manifest, root, root)['verified'])
            asset.write_text('different_version')
            self.assertFalse(verify_resources(manifest, root, root)['verified'])
            payload['resources']['assets']['files'][0]['path'] = '../robot.urdf'; atomic_json(manifest, payload)
            with self.assertRaises(ValueError):
                verify_resources(manifest, root, root)


class RuntimeBoundaryTest(unittest.TestCase):
    def test_old_wuji2_snapshot_rejected_before_comparison(self):
        with self.assertRaises(ValueError):
            compare_runtime({'schema_version': 1, 'simulator': 'mujoco', 'robot_key': 'wuji2'},
                            {'semantics': Path(__file__).resolve().parents[1] / 'assets/hand/wuji/bench2dex.yaml',
                             'bench2dex_root': Path('/nonexistent'), 'robot_key': 'multi_ur5_wuji_with_flange'}, Path('/nonexistent'))

    def test_capture_missing_runtime_joints_rejected(self):
        from types import SimpleNamespace
        robot = SimpleNamespace(data=SimpleNamespace(joint_names=['finger1_joint1']))
        with self.assertRaises(ValueError):
            capture_pose(robot, 'neutral', Path(__file__).resolve().parents[1] / 'assets/hand/wuji/bench2dex.yaml')


if __name__ == '__main__':
    unittest.main()
