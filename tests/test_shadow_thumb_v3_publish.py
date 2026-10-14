"""Publishing repairs must never downgrade a candidate or hide a failed trial."""
import unittest

from tools.finalize_shadow_thumb_v3 import choose_repair


class RepairSelectionTest(unittest.TestCase):
    def test_passing_primary_cannot_be_replaced_by_a_repair(self):
        self.assertFalse(choose_repair({'status': 'kinematic_candidate'}, {'status': 'kinematic_candidate'}))

    def test_repaired_candidate_is_selected_over_rejected_primary(self):
        self.assertTrue(choose_repair({'status': 'kinematic_rejected'}, {'status': 'kinematic_candidate'}))

    def test_failed_or_absent_execution_keeps_recorded_primary(self):
        self.assertFalse(choose_repair({'status': 'kinematic_rejected'}, {'status': 'error'}))
        self.assertFalse(choose_repair({'status': 'kinematic_rejected'}, None))

    def test_both_rejected_prioritize_passing_geometric_thumb_policy(self):
        self.assertTrue(choose_repair({'status': 'kinematic_rejected', 'selected_policy_passed': False},
                                      {'status': 'kinematic_rejected', 'selected_policy_passed': True}))
        self.assertFalse(choose_repair({'status': 'kinematic_rejected', 'selected_policy_passed': True},
                                       {'status': 'kinematic_rejected', 'selected_policy_passed': False}))


if __name__ == '__main__': unittest.main()
