"""Gravity probes must free the object and respect original joint torques."""
import json
from pathlib import Path
import tempfile
import unittest

import mujoco
import numpy as np

from dexonomy.integrations.bench2dex.gravity_hold_probe import build_model,probe,CONFIG


class GravityProbeBoundaryTest(unittest.TestCase):
    folder=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/samples/case_0091__24_Tip_Pinch')

    @classmethod
    def setUpClass(cls):
        with np.load(cls.folder/'postures.npz',allow_pickle=False) as z:cls.pose=z['wuji_selected_qpos'][2].copy()

    def test_model_has_a_free_object_fixed_wrist_and_native_torque_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            m,qidx,vidx,joints,hands,objects,obj=build_model(self.folder,self.pose,.5,Path(tmp)/'model.xml')
            self.assertEqual(m.nu,20);self.assertEqual(m.neq,0)
            self.assertFalse(m.opt.disableflags&int(mujoco.mjtDisableBit.mjDSBL_GRAVITY))
            self.assertTrue(m.body(obj).name.startswith('obj-'))
            self.assertTrue(np.all(m.jnt_actfrclimited[joints]))
            self.assertLess(np.abs(m.jnt_actfrcrange[joints]).max(),1.)
            self.assertTrue(np.all(m.body_gravcomp==0))
            self.assertTrue(all(m.geom_condim[g]==3 for g in hands|objects))

    def test_without_hand_collisions_object_falls_at_gravitational_acceleration(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=probe(self.folder,self.pose,Path(tmp)/'probe',cfg={**CONFIG,'duration_s':.1},hand_collision_enabled=False)
            delta=r['rows'][-1]['object_com_z_m']-r['rows'][0]['object_com_z_m']
            self.assertAlmostEqual(delta,-.5*9.81*.1**2,delta=.001)
            self.assertEqual(r['rows'][-1]['hand_up_force_n'],0.)
            self.assertFalse(r['passed'])


if __name__=='__main__':unittest.main()
