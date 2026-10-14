"""Matching boundaries and geometry invariants for source-guided retargeting."""
import unittest
from time import monotonic

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from dexonomy.integrations.bench2dex.asset_matching import object_tokens, same_ycb_name
from dexonomy.integrations.bench2dex.shadow_retarget import resample_chain,budgeted_solve,minimum_surface_distance
from dexonomy.integrations.bench2dex.local_grasp import signed_distance


class AssetIdentityTest(unittest.TestCase):
    def test_shared_ycb_requires_full_id_and_name(self):
        self.assertTrue(same_ycb_name('056_tennis_ball','ddg_ycb_056_tennis_ball'))
        self.assertFalse(same_ycb_name('053_mini_soccer_ball','ddg_ycb_056_tennis_ball'))
        self.assertFalse(same_ycb_name('056_tennis_ball','ddg_ycb_056_tennis_ball_handle'))
        self.assertTrue(same_ycb_name('065-e_cups','ddg_ycb_065_e_cups'))

    def test_category_and_whole_tokens_prevent_false_matches(self):
        self.assertNotIn('ball',object_tokens('mujoco_Leather_Ballet_Flats'))
        self.assertEqual(object_tokens('core_bowl_abc123'),{'bowl'})
        self.assertNotIn('plate',object_tokens('sem_Hairdryer_plate_caption'))


class FingerChainTest(unittest.TestCase):
    def test_arc_sampling_is_rigid_transform_equivariant(self):
        points=np.array([[0,0,0],[0,0,.03],[.01,0,.05],[.03,0,.06]])
        rotation=Rotation.from_euler('xyz',[.4,.7,.2]).as_matrix()
        shift=np.array([1.,2.,3.])
        reference,length=resample_chain(points)
        transformed,new_length=resample_chain(points@rotation.T+shift)
        np.testing.assert_allclose(transformed,reference@rotation.T+shift,atol=1e-12)
        self.assertAlmostEqual(length,new_length)

    def test_collocated_joint_frames_do_not_create_nan(self):
        sampled,length=resample_chain([[0,0,0],[0,0,0],[0,0,.04],[0,0,.04]])
        np.testing.assert_allclose(sampled[:,2],[.01,.02,.03,.04])
        self.assertAlmostEqual(length,.04)
        with self.assertRaises(ValueError):resample_chain([[0,0,0],[0,0,0]])


class BudgetAndGeometryTest(unittest.TestCase):
    def test_expired_budget_returns_bounded_initial_checkpoint(self):
        initial=np.array([.3,-.2])
        value,info=budgeted_solve(lambda x:x-np.array([.1,.1]),initial,([-1,-1],[1,1]),10,monotonic()-1)
        np.testing.assert_array_equal(value,initial)
        self.assertEqual(info['termination'],'time_budget_checkpoint')
        self.assertFalse(info['success'])

    def test_pruned_distance_agrees_with_all_pairs_including_overlap(self):
        model=mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
          <body><freejoint/><geom name="hand" type="box" size=".012 .01 .008"/></body>
          <body pos=".015 0 0"><freejoint/><geom name="near" type="capsule" size=".01 .02"/></body>
          <body pos=".8 0 0"><geom name="far" type="sphere" size=".01"/></body>
          </worldbody></mujoco>''')
        data=mujoco.MjData(model)
        hand=[model.geom('hand').id];objects=[model.geom('near').id,model.geom('far').id]
        for shift in [.0,.04,-.06,.7]:
            data.qpos[0]=shift
            data.qpos[3:7]=Rotation.from_euler('xyz',[.1,.3,.5]).as_quat()[[3,0,1,2]]
            mujoco.mj_fwdPosition(model,data)
            expected=min(signed_distance(model,data,h,o) for h in hand for o in objects)
            self.assertAlmostEqual(minimum_surface_distance(model,data,hand,objects),expected,places=10)
            positions=data.geom_xpos.copy();contacts=[(int(c.geom1),int(c.geom2),float(c.dist)) for c in data.contact]
            mujoco.mj_forward(model,data)
            np.testing.assert_allclose(data.geom_xpos,positions,atol=1e-12)
            self.assertEqual([(int(c.geom1),int(c.geom2),float(c.dist)) for c in data.contact],contacts)


if __name__=='__main__':
    unittest.main()
