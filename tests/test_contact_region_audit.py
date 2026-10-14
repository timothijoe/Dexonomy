"""Contact-region diagnostics distinguish distance, patch and segment changes."""
import unittest
import numpy as np
from scipy.spatial.transform import Rotation

from dexonomy.integrations.bench2dex.contact_region_audit import classify, segment_distance, CONFIG


class ContactRegionDiagnosticsTest(unittest.TestCase):
    def test_touching_elsewhere_does_not_hide_lost_source_edge_or_segment(self):
        target = {'full': {'gap_m': .0004}, 'corresponding': {'gap_m': .008}}
        flags = classify({}, target, .012, .0005, .01, True, True, CONFIG)
        self.assertIn('source_edge_not_preserved', flags)
        self.assertIn('touching_another_patch', flags)
        self.assertIn('contact_segment_substitution', flags)
        self.assertNotIn('finger_contact_lost', flags)

    def test_unreliable_source_reference_does_not_produce_a_loss_claim(self):
        target = {'full': {'gap_m': .02}, 'corresponding': {'gap_m': .02}}
        self.assertEqual(classify({}, target, .03, .001, .02, False, True, CONFIG), [])

    def test_motion_along_the_same_edge_is_only_a_patch_drift_candidate(self):
        target = {'full': {'gap_m': .0005}, 'corresponding': {'gap_m': .0005}}
        flags = classify({}, target, .012, .0005, .0006, True, True, CONFIG)
        self.assertIn('source_patch_displaced', flags)
        self.assertNotIn('source_edge_not_preserved', flags)

    def test_segment_distance_is_metric_and_rigid_transform_invariant(self):
        segments = np.array([[[0.,0,0],[1,0,0]]]);point = np.array([.5,.02,0])
        self.assertAlmostEqual(segment_distance(point, segments), .02)
        matrix = Rotation.from_rotvec([.3,-.6,.1]).as_matrix();translation = np.array([.7,-.3,.8])
        self.assertAlmostEqual(segment_distance(point@matrix.T+translation,segments@matrix.T+translation), .02)
        self.assertIsNone(segment_distance(point,np.empty((0,2,3))))


if __name__ == '__main__': unittest.main()
