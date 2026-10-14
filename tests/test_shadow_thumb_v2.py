"""Thumb-reference invariance and V1 protection checks for V2 selection."""
from types import SimpleNamespace
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import yaml

import numpy as np
from scipy.spatial.transform import Rotation

from dexonomy.integrations.bench2dex.shadow_thumb_v2 import thumb_features,choose_refinement
from dexonomy.integrations.bench2dex.thumb_v2_batch import _run
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt


class ThumbDescriptorTest(unittest.TestCase):
    def test_palm_relations_and_pad_direction_are_rigid_transform_invariant(self):
        class Hand:
            lengths=np.array([.1,.11,.12,.11,.1])
            palm=0
            tip_bodies={'thumb':1}
            def features(self,q):
                self.rotation=Rotation.from_quat(q[3:7][[1,2,3,0]]).as_matrix()
                self.translation=q[:3]
                self.local_points=np.array([[.02,0,0],[.025,.02,.01],[.02,.04,.025],[.01,.06,.03],[0,.075,.04]])
                tips=np.array([self.local_points[-1],[.025,.09,.04],[0,.1,.04],[-.025,.09,.04],[-.045,.08,.03]])
                self.data=SimpleNamespace(xpos=np.array([q[:3],self.rotation@self.local_points[-1]+q[:3]]),
                    xmat=np.array([self.rotation.ravel(),self.rotation.ravel()]))
                return np.zeros((5,4,3)),tips@self.rotation.T+self.translation,self.rotation
            def points(self,f):return self.local_points@self.rotation.T+self.translation
        hand=Hand();q=np.r_[0.,0,0,1,0,0,0]
        before=thumb_features(hand,q,np.array([0.,1,0]))[0]
        q=np.r_[1.,-2.,3.,Rotation.from_euler('xyz',[.7,.4,-.2]).as_quat()[[3,0,1,2]]]
        after=thumb_features(hand,q,np.array([0.,1,0]))[0]
        for key in before:np.testing.assert_allclose(before[key],after[key],atol=1e-12)


class V2SelectionTest(unittest.TestCase):
    cfg={'minimum_thumb_score_improvement_fraction':.02,
         'maximum_component_regression_fraction':.1,'maximum_component_regression_absolute':.02}
    def metrics(self,value,**overrides):
        result={'score':value*3,'palm':value,'opposition':value,'directions':value,'pad_chord':value}
        result.update(overrides);return [result]*3

    def test_thumb_improvement_cannot_override_a_geometry_regression(self):
        accepted,reason=choose_refinement({'passed':True},{'passed':False},self.metrics(.5),self.metrics(.1),self.cfg)
        self.assertFalse(accepted);self.assertEqual(reason,'baseline_geometry_preserved')

    def test_aggregate_improvement_cannot_hide_a_pad_regression(self):
        accepted,reason=choose_refinement({'passed':True},{'passed':True},self.metrics(.5),self.metrics(.1,pad_chord=.8),self.cfg)
        self.assertFalse(accepted);self.assertEqual(reason,'thumb_component_regression_pad_chord')

    def test_fidelity_and_geometry_improvement_can_replace_v1(self):
        accepted,reason=choose_refinement({'passed':False},{'passed':True},self.metrics(.5),self.metrics(.3),self.cfg)
        self.assertTrue(accepted);self.assertEqual(reason,'thumb_fidelity_improved_with_geometry_pass')

    def test_other_phases_cannot_mask_a_grasp_score_regression(self):
        old=self.metrics(.5);new=self.metrics(.1)
        new=[dict(v) for v in new];new[1]['score']=2.
        accepted,reason=choose_refinement({'passed':True},{'passed':True},old,new,self.cfg)
        self.assertFalse(accepted);self.assertEqual(reason,'thumb_phase_regression_grasp')


class V2FallbackTest(unittest.TestCase):
    def test_fallback_keeps_primary_trial_and_publishes_selected_postures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'primary.yaml';fallback=root/'fallback.yaml'
            config.write_text(yaml.safe_dump({'fallback_config':str(fallback)}));fallback.write_text('{}')
            def fake_refine(baseline,path,folder,render):
                folder.mkdir(parents=True)
                adopted=path==fallback
                r={'selected_version':'v2' if adopted else 'v1_retained','selection_reason':'test',
                   'status':'kinematic_candidate','seconds':1.,'config':file_receipt(path),
                   'selected_quality':{'passed':True,'failure_reasons':[]},'baseline_quality':{'passed':True},
                   'proposed_quality':{'passed':adopted},'baseline_thumb':{'grasp':{'score':1.}},
                   'selected_thumb':{'grasp':{'score':.5 if adopted else 1.}},'joint_solver':{'termination':'converged'}}
                atomic_json(folder/'result.json',r)
                (folder/'postures.npz').write_bytes(b'fallback' if adopted else b'primary')
                (folder/'comparison.png').write_bytes(b'image')
                (folder/'hand_only').mkdir();(folder/'hand_only/comparison.png').write_bytes(b'image')
                return r
            job={'case_id':'case','baseline_folder':str(root/'baseline'),'aliases':[{'bench_object':'target'}]}
            with patch('dexonomy.integrations.bench2dex.thumb_v2_batch.refine_case',side_effect=fake_refine):
                row=_run(job,str(config),str(root/'output'),'identity')
            self.assertEqual(row['selected_version'],'v2');self.assertEqual(row['attempt_count'],2)
            self.assertEqual((root/'output/postures.npz').read_bytes(),b'fallback')
            self.assertEqual((root/'output/primary_trial/postures.npz').read_bytes(),b'primary')
            result=json.loads((root/'output/result.json').read_text());self.assertEqual(len(result['refinement_attempts']),2)


if __name__=='__main__':unittest.main()
