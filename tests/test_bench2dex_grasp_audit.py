"""Independent physical references for contact-force audit conventions."""
import unittest

import mujoco
import numpy as np

from tools.audit_bench2dex_grasp import object_contact_forces


class ContactForceAuditTest(unittest.TestCase):
    def test_settled_ball_table_force_balances_weight(self):
        model = mujoco.MjModel.from_xml_string('''<mujoco>
          <option timestep=".001"/>
          <worldbody><geom name="table" type="plane" size="1 1 .01"/>
            <body name="ball" pos="0 0 .04"><freejoint/>
              <geom name="object" type="sphere" size=".03" mass=".058"/>
            </body></worldbody></mujoco>''')
        data = mujoco.MjData(model)
        for _ in range(1000): mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        hand, table, links, points = object_contact_forces(model,data,model.geom('object').id,model.geom('table').id)
        np.testing.assert_allclose(hand,0,atol=1e-8)
        np.testing.assert_allclose(table,[0,0,.058*9.81],atol=1e-5)
        self.assertEqual(links,[])
        self.assertEqual(points,[])

    def test_detected_inactive_contact_has_no_support_force(self):
        model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
          <geom name="table" type="plane" size="1 1 .01" margin=".01" gap=".01"/>
          <body pos="0 0 .035"><freejoint/>
            <geom name="object" type="sphere" size=".03" mass=".058"/>
          </body></worldbody></mujoco>''')
        data = mujoco.MjData(model)
        mujoco.mj_forward(model,data)
        self.assertGreater(data.ncon,0)
        self.assertTrue(all(c.efc_address < 0 for c in data.contact))
        hand,table,links,points = object_contact_forces(model,data,model.geom('object').id,model.geom('table').id)
        np.testing.assert_allclose(hand,0)
        np.testing.assert_allclose(table,0)
        self.assertEqual(links,[])
        self.assertEqual(points,[])


if __name__ == '__main__':
    unittest.main()
