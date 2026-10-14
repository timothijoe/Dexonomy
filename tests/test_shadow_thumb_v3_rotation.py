"""Rotation viewing preserves pose data and original hand scale."""
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.integrations.bench2dex.shadow_retarget import HandGeometry
from dexonomy.integrations.bench2dex.thumb_v3_rotation import aligned_pose


class PalmAlignmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hand = HandGeometry(MuJoCo_VisEnv(HandCfg('output/bench2dex_v1/models/right/hand.xml', freejoint=True),
                                           vis_mode='collision'), 'wuji')
        cls.source = HandGeometry(MuJoCo_VisEnv(HandCfg('assets/hand/shadow/right.xml', freejoint=True),
                                             vis_mode='collision'), 'shadow')

    def test_alignment_preserves_joint_angles_and_original_metric_lengths(self):
        h = self.hand; q = h.neutral.copy(); q[:3] = [.3, -.2, .6]
        q[3:7] = Rotation.from_rotvec([.4, -.3, .8]).as_quat()[[3, 0, 1, 2]]
        original = q.copy(); h.set_pose(q)
        lengths = np.linalg.norm(np.diff(h.points('thumb'), axis=0), axis=1)
        aligned = aligned_pose(h, q); h.set_pose(aligned)
        np.testing.assert_array_equal(q, original)
        np.testing.assert_array_equal(aligned[7:], q[7:])
        np.testing.assert_allclose(h.data.xpos[h.palm], 0, atol=1e-10)
        np.testing.assert_allclose(h.frame(), np.eye(3), atol=1e-10)
        np.testing.assert_allclose(np.linalg.norm(np.diff(h.points('thumb'), axis=0), axis=1), lengths, atol=1e-10)

    def test_both_hands_have_identical_aligned_points_under_world_rigid_motion(self):
        for hand in [self.hand, self.source]:
            q = hand.neutral.copy()
            hand.set_pose(aligned_pose(hand, q))
            reference = np.vstack([hand.points(f).copy() for f in hand.chains])
            moved = q.copy(); moved[:3] = [-.5, .2, .9]
            moved[3:7] = Rotation.from_rotvec([-.8, .1, .7]).as_quat()[[3, 0, 1, 2]]
            hand.set_pose(aligned_pose(hand, moved))
            np.testing.assert_allclose(np.vstack([hand.points(f) for f in hand.chains]), reference, atol=1e-10)


if __name__ == '__main__': unittest.main()
