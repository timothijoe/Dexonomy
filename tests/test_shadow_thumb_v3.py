"""Hard bend feasibility, actual-model axis calibration and publication gates."""
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.integrations.bench2dex.shadow_retarget import HandGeometry
from dexonomy.integrations.bench2dex.shadow_thumb_v2 import pad_calibration
from dexonomy.integrations.bench2dex.shadow_thumb_v3 import (
    BendDomain, projected_turn, hinge_turns, bone_directions, calibrate_bends, select_candidate)


class ActualThumbDomainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sh = HandGeometry(MuJoCo_VisEnv(HandCfg('assets/hand/shadow/right.xml', freejoint=True), vis_mode='collision'), 'shadow')
        cls.w = HandGeometry(MuJoCo_VisEnv(HandCfg('output/bench2dex_v1/models/right/hand.xml', freejoint=True), vis_mode='collision'), 'wuji')
        pad = pad_calibration(cls.sh, cls.w, 'assets/hand/shadow/raw_anno/13_Precision_Sphere.yaml')
        cls.cal = calibrate_bends(cls.w, pad['target_normal_local'])
        cls.domain = BendDomain(cls.w.limits[2:4], cls.cal, np.deg2rad(130))

    def test_whole_domain_obeys_actual_geometric_and_mechanical_limits(self):
        rng = np.random.default_rng(3)
        coordinates = np.vstack([rng.uniform(size=(100, 2)), [[0, 0], [0, 1], [1, 0], [1, 1]]])
        for pair in coordinates:
            q = self.w.neutral.copy()
            q[7:] = rng.uniform(self.w.limits[:, 0], self.w.limits[:, 1])
            q[9:11] = self.domain.decode(pair)
            bends = hinge_turns(self.w, q) * self.cal['flexion_sign']
            self.assertTrue(np.all(bends >= -1e-10))
            self.assertLessEqual(bends.sum(), np.deg2rad(130) + 1e-10)
            self.assertTrue(np.all(q[9:11] >= self.w.limits[2:4, 0] - 1e-10))
            self.assertTrue(np.all(q[9:11] <= self.w.limits[2:4, 1] + 1e-10))

    def test_correction_uses_geometric_zero_and_preserves_opposition_joint(self):
        q = self.w.neutral.copy(); q[8] = -.1; q[9:11] = [-.35, -.44]
        fixed = q.copy(); fixed[9:11] = self.domain.decode(self.domain.encode(q[9:11]))
        self.assertEqual(fixed[8], -.1)
        self.assertGreater(fixed[9], 0)
        self.assertGreater(fixed[10], 0)
        np.testing.assert_allclose(hinge_turns(self.w, fixed), 0, atol=1e-10)

    def test_bone_directions_and_signed_bends_are_rigid_transform_invariant(self):
        q = self.w.neutral.copy(); q[9:11] = self.domain.decode([.3, .7])
        before = hinge_turns(self.w, q); directions = bone_directions(self.w, q)
        q[:3] = [.4, -.2, .8]
        q[3:7] = Rotation.from_rotvec([.7, -.4, .3]).as_quat()[[3, 0, 1, 2]]
        np.testing.assert_allclose(hinge_turns(self.w, q), before, atol=1e-10)
        np.testing.assert_allclose(bone_directions(self.w, q), directions, atol=1e-10)

    def test_sum_cap_enforces_coupling_near_joint_maxima(self):
        joints = self.domain.decode([1, 1])
        self.assertAlmostEqual(self.domain.angles(joints).sum(), np.deg2rad(130))

    def test_signed_turn_preserves_reverse_direction(self):
        angle = projected_turn(np.array([0., 0, 1]), np.array([-.5, 0, np.sqrt(.75)]), np.array([0., 1, 0]))
        self.assertAlmostEqual(np.rad2deg(angle), -30)


class NaturalPolicySelectionTest(unittest.TestCase):
    metrics = [{'score': 1, 'palm': .2, 'directions': .2, 'opposition': .2, 'pad_chord': .2}] * 3
    cfg = {'minimum_thumb_score_improvement_fraction': .02,
           'maximum_component_regression_fraction': .1, 'maximum_component_regression_absolute': .02}

    def select(self, old_g, new_g, old_n, new_n):
        return select_candidate({'passed': old_g}, {'passed': new_g}, {'passed': old_n},
                                {'passed': new_n}, self.metrics, self.metrics, self.cfg)

    def test_bad_baseline_cannot_be_retained_as_passed_when_new_geometry_fails(self):
        self.assertEqual(self.select(True, False, False, True)[1], 'v3_rejected')

    def test_policy_failure_cannot_be_overridden_by_geometry_success(self):
        self.assertEqual(self.select(True, True, False, False)[1], 'v3_rejected')

    def test_repaired_constraints_can_be_adopted_without_claiming_score_improvement(self):
        self.assertEqual(self.select(True, True, False, True)[1], 'v3')

    def test_valid_baseline_is_preserved_when_proposal_is_invalid(self):
        self.assertEqual(self.select(True, False, True, True)[1], 'v2_retained')

    def test_valid_baseline_with_no_improvement_is_retained(self):
        self.assertEqual(self.select(True, True, True, True)[1], 'v2_retained')


if __name__ == '__main__': unittest.main()
