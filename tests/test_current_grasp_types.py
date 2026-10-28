"""Category expansion must not silently add objects, drop types, or duplicate work."""
import unittest
from tools.check_current_shadow_grasp_types import validate_pairs


class CoveragePlanTest(unittest.TestCase):
    def setUp(self):
        self.catalog={'one':{'categories':['1_Type','2_Type']},'two':{'categories':['2_Type']}}
        self.entries=[{'object':'one','category':'1_Type','case_id':'a'},
            {'object':'one','category':'2_Type','case_id':'b'},{'object':'two','category':'2_Type','case_id':'c'}]

    def test_complete_per_object_types_are_counted_separately(self):
        self.assertEqual(validate_pairs(['one','two'],self.entries,self.catalog),3)

    def test_missing_type_cannot_be_reported_as_full_coverage(self):
        with self.assertRaises(ValueError):validate_pairs(['one','two'],self.entries[:-1],self.catalog)

    def test_duplicate_model_type_cannot_inflate_coverage(self):
        with self.assertRaises(ValueError):validate_pairs(['one','two'],self.entries+[self.entries[0]],self.catalog)

    def test_new_object_is_outside_the_authorized_scope(self):
        with self.assertRaises(ValueError):validate_pairs(['one'],self.entries,self.catalog)

    def test_case_id_collision_cannot_alias_different_objects(self):
        self.entries[2]['case_id']='a'
        with self.assertRaises(ValueError):validate_pairs(['one','two'],self.entries,self.catalog)


if __name__=='__main__':unittest.main()
