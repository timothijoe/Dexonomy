"""Fixed coverage, source deduplication and resume-integrity regressions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import yaml

from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256
from dexonomy.integrations.bench2dex.shadow_batch import ordered_categories,prepare_plan,verify_plan,verify_completed


class ShadowBatchTest(unittest.TestCase):
    def test_category_budget_keeps_priority_and_deduplicates(self):
        self.assertEqual(ordered_categories(['a','b','c'],['a','missing','a'],['b','c'],4),['a','b','c'])

    def test_alias_assets_share_cases_but_different_categories_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);objects=root/'objects';model=root/'hand.xml'
            model.write_text('<mujoco><worldbody/></mujoco>')
            atomic_json(root/'model_report.json',{'urdf_mujoco_fk_passed':True,'mjcf':file_receipt(model)})
            mesh=root/'mesh.obj';mesh.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
            scene_path=root/'scene.npy'
            np.save(scene_path,{'task':{'obj_name':'object'},'scene':{'object':{'scale':[1,1,1],
                    'type':'rigid_object','file_path':str(mesh),'xml_path':str(model)}}})
            categories=['a','b','c','d'];q=np.zeros((1,29));q[:,3]=1
            for category in categories:
                folder=objects/'Dexonomy_GRASP_shadow/succ_collect'/category/'source_object/floating'
                folder.mkdir(parents=True)
                np.save(folder/'scale005.npy',{'scene_path':str(scene_path),'scene_scale':np.array([1.]),
                        'pregrasp_qpos':q,'grasp_qpos':q,'squeeze_qpos':q})
            rows=[{'bench_object':name,'family':'family','tasks':[],'candidates':[{'dexonomy_object':'source_object',
                    'shadow_categories':categories,'match_level':'similar_geometry_family','mesh':file_receipt(mesh)}]}
                  for name in ['target_a','target_b']]
            matches=root/'matches.json';atomic_json(matches,{'initial_selection':[],'object_matches':rows})
            profile=root/'profile.yaml';profile.write_text(yaml.safe_dump({'schema_version':1,'grasps_per_asset':4,
                    'minimum_grasps_per_asset':3,'source_side':'right','target_side':'right',
                    'selection_index_if_target_size_unknown':0,'family_categories':{'family':categories},'fallback_categories':[]}))
            config=root/'config.yaml';config.write_text('schema_version: 1\n')
            with patch('dexonomy.integrations.bench2dex.shadow_batch.model_resources',return_value=[file_receipt(model)]):
                plan=prepare_plan(matches,profile,objects,model,config,root/'batch')
            self.assertEqual(plan['asset_count'],2)
            self.assertEqual(plan['coverage_entries'],8)
            self.assertEqual(plan['unique_source_cases'],4)
            self.assertTrue(all(len(j['aliases'])==2 for j in plan['jobs']))
            verify_plan(plan)
            (root/'config.yaml').write_text('schema_version: 2\n')
            with self.assertRaises(ValueError):verify_plan(plan)

    def test_completed_receipt_rejects_modified_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);artifact=folder/'result.json';artifact.write_text('{}')
            atomic_json(folder/'receipt.json',{'identity':'fixed','row':{'case_id':'case'},
                        'artifacts':[{'path':'result.json','sha256':sha256(artifact)}]})
            self.assertEqual(verify_completed(folder,'fixed'),{'case_id':'case'})
            artifact.write_text('{"changed":true}')
            with self.assertRaises(ValueError):verify_completed(folder,'fixed')


if __name__=='__main__':unittest.main()
