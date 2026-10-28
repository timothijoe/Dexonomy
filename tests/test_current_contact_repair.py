"""A repair must use the right baseline, preserve good stages, and add no flags."""
import copy
import tempfile
from pathlib import Path
import unittest
from dexonomy.integrations.bench2dex.common import file_receipt
from dexonomy.integrations.bench2dex.current_contact_repair import focus_by_phase,audit_gate,validate_audit_binding


def row(phase='grasp',finger='index',gap=.008,required=True,reliable=True,flags=()):
    return {'phase':phase,'finger':finger,'version':'selected','required':required,
        'source_near_reference':reliable,'target':{'anchor':{'distance_m':gap}},'flags':list(flags)}


class CurrentContactRepairTest(unittest.TestCase):
    def test_only_reliable_required_fingers_in_the_affected_phase(self):
        a={'rows':[row(),row('squeeze',gap=.001),row(finger='palm'),
            row(finger='ring',required=False),row(finger='thumb',reliable=False)]}
        self.assertEqual(focus_by_phase(a),{'grasp':['index'],'squeeze':[]})

    def test_threshold_is_strict_and_stages_remain_distinct(self):
        a={'rows':[row(gap=.005),row('squeeze',gap=.005001)]}
        self.assertEqual(focus_by_phase(a),{'grasp':[],'squeeze':['index']})

    def test_improving_patch_cannot_create_new_required_edge_or_segment_loss(self):
        old={'rows':[row(flags=['source_patch_displaced'])]}
        for flag in ['source_edge_not_preserved','contact_segment_substitution','finger_contact_lost','deep_penetration']:
            self.assertFalse(audit_gate(old,{'rows':[row(gap=.001,flags=[flag])]})['passed'])
        self.assertTrue(audit_gate(old,{'rows':[row(gap=.001)]})['passed'])

    def test_residual_drift_cannot_be_adopted(self):
        a={'rows':[row(flags=['source_patch_displaced'])]}
        self.assertFalse(audit_gate(a,copy.deepcopy(a))['passed'])

    def test_matching_case_id_or_identical_content_does_not_bind_wrong_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folders=[Path(tmp)/v for v in ['a','b']]
            for folder in folders:
                folder.mkdir()
                for name in ['postures.npz','result.json']:(folder/name).write_text('identical')
            a={'inputs':[file_receipt(folders[0]/n) for n in ['postures.npz','result.json']]}
            validate_audit_binding(folders[0],a)
            with self.assertRaisesRegex(ValueError,'baseline folder'):validate_audit_binding(folders[1],a)
            (folders[0]/'postures.npz').write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed'):validate_audit_binding(folders[0],a)


if __name__=='__main__':unittest.main()
