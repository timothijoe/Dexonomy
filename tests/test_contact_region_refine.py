"""Contact repair gates preserve intentional edge grasps and supported patches."""
import copy
import unittest
from dexonomy.integrations.bench2dex.contact_region_refine import edge_shift,protection_passed


class RegionRepairGateTest(unittest.TestCase):
    def setUp(self):
        self.row={'source_near_reference':True,'source':{'edge_distance_m':.012},
            'target':{'edge_distance_m':.001,'full':{'gap_m':.0002},
                'raw_object_surface_gap_m':.0001,'anchor':{'distance_m':.009}}}

    def test_interior_patch_shifted_to_edge_is_flagged(self):
        self.assertTrue(edge_shift(self.row))

    def test_original_edge_grasp_is_not_pushed_inward(self):
        row=copy.deepcopy(self.row);row['source']['edge_distance_m']=.001
        self.assertFalse(edge_shift(row))

    def test_nearest_edge_does_not_imply_lost_contact_when_source_patch_is_present(self):
        row=copy.deepcopy(self.row);row['target']['anchor']['distance_m']=.0002
        self.assertFalse(edge_shift(row))

    def test_unreliable_surface_projection_is_not_claimed_as_edge_shift(self):
        for key in ['raw_object_surface_gap_m','gap_m']:
            row=copy.deepcopy(self.row)
            if key=='gap_m':row['target']['full'][key]=.009
            else:row['target'][key]=.009
            self.assertFalse(edge_shift(row))

    def test_restoring_one_finger_cannot_discard_an_already_preserved_patch(self):
        before={'grasp:thumb':.0004,'squeeze:palm':.0017}
        self.assertTrue(protection_passed(before,{'grasp:thumb':.0019,'squeeze:palm':.0025}))
        self.assertFalse(protection_passed(before,{'grasp:thumb':.004,'squeeze:palm':.0017}))


if __name__=='__main__':unittest.main()
