"""Physical/data-boundary regressions for the local grasp generator."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import trimesh
from pxr import Usd, UsdGeom, UsdPhysics, Gf

from dexonomy.integrations.bench2dex.local_grasp import geometric_measurements, signed_distance, usd_object_mesh, load_grasp_config, execute_candidate
from dexonomy.integrations.bench2dex.catalog import object_relative_path


class CollisionDepthTest(unittest.TestCase):
    def setUp(self):
        self.model = mujoco.MjModel.from_xml_string('<mujoco><worldbody><body name="hand"><freejoint/><geom name="hand" type="sphere" size=".01"/></body><body name="object" pos=".015 0 0"><freejoint/><geom name="object" type="sphere" size=".01"/></body></worldbody></mujoco>')
        self.data = mujoco.MjData(self.model); mujoco.mj_forward(self.model, self.data)

    def test_real_overlap_is_not_zero_distance_geometry_success(self):
        with patch('dexonomy.integrations.bench2dex.local_grasp.mujoco.mj_geomDistance', return_value=0.0):
            result = geometric_measurements(self.model, self.data, {0}, 1)
            self.assertAlmostEqual(result['max_hand_object_penetration_m'], .005)
            self.assertLess(signed_distance(self.model, self.data, 0, 1), -.004)

    def test_separated_surfaces_still_use_positive_distance(self):
        self.data.qpos[7] = .04; mujoco.mj_forward(self.model, self.data)
        self.assertAlmostEqual(signed_distance(self.model, self.data, 0, 1), .02)


class ObjectConversionTest(unittest.TestCase):
    def test_usd_root_placement_units_scale_and_authored_mass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'box.usda'; stage = Usd.Stage.CreateNew(str(path))
            UsdGeom.SetStageMetersPerUnit(stage, .01)
            root = UsdGeom.Xform.Define(stage, '/Object'); root.AddTranslateOp().Set(Gf.Vec3d(10, 0, 0)); stage.SetDefaultPrim(root.GetPrim())
            UsdPhysics.MassAPI.Apply(root.GetPrim()).CreateMassAttr(.03)
            parent = UsdGeom.Xform.Define(stage, '/Object/Geometry'); parent.AddTranslateOp().Set(Gf.Vec3d(1, 2, 3))
            mesh = UsdGeom.Mesh.Define(stage, '/Object/Geometry/Mesh')
            points = [[x, y, z] for x in [-.5, .5] for y in [-.5, .5] for z in [-.5, .5]]
            mesh.CreatePointsAttr(points)
            mesh.CreateFaceVertexCountsAttr([4] * 6)
            mesh.CreateFaceVertexIndicesAttr([0,1,3,2, 4,6,7,5, 0,4,5,1, 2,3,7,6, 0,2,6,4, 1,5,7,3])
            UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
            stage.GetRootLayer().Save()
            result = usd_object_mesh(path, [2, 1, 3], Path(tmp) / 'object.obj')
            np.testing.assert_allclose(result['bounds_object_m'], [[.01,.015,.075],[.03,.025,.105]], atol=1e-8)
            self.assertAlmostEqual(result['mass_kg'], .03, places=6)

    def test_path_and_scale_do_not_silently_guess(self):
        self.assertEqual(object_relative_path('../../dex2bench_dataset/Objects/056_tennis_ball/a.usd').as_posix(), 'Objects/056_tennis_ball/a.usd')
        with self.assertRaises(ValueError):
            object_relative_path('unknown/object.usd')

    def test_control_rate_must_be_integral_physics_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cfg.yaml'; p.write_text('schema_version: 1\ncontroller:\n  physics_dt_s: 0.003\n  control_dt_s: 0.02\n')
            with self.assertRaises(ValueError):
                load_grasp_config(p)

    def test_inherited_parameter_changes_invalidate_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); base=root/'base.yaml'; child=root/'child.yaml'
            base.write_text('schema_version: 1\ncontroller:\n  physics_dt_s: 0.001\n  control_dt_s: 0.02\n  finger_kp: 10\n')
            child.write_text('base_config: base.yaml\noverrides:\n  controller:\n    finger_kv: 1\n')
            first=load_grasp_config(child)['config_sha256']
            base.write_text(base.read_text().replace('finger_kp: 10','finger_kp: 20'))
            self.assertNotEqual(first,load_grasp_config(child)['config_sha256'])

    def test_cyclic_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'a.yaml').write_text('base_config: b.yaml\noverrides: {}\n'); (root/'b.yaml').write_text('base_config: a.yaml\noverrides: {}\n')
            with self.assertRaises(ValueError):
                load_grasp_config(root/'a.yaml')


class PhysicalValidatorTest(unittest.TestCase):
    def test_real_two_jaw_lift_hold_fixture(self):
        # A positive physical fixture tests the evaluator independently of the
        # unsolved Wuji synthesis problem; it is never a Wuji success sample.
        repo = Path(__file__).resolve().parents[1]
        cfg = {'semantics': repo / 'assets/hand/wuji/bench2dex.yaml',
               'validation': {'joint_tolerance_rad': .0001, 'penetration_tolerance_m': .002,
                              'lift_height_m': .05, 'hold_duration_s': 1., 'hold_translation_m': .01, 'hold_angle_deg': 10.}}
        gcfg = load_grasp_config(repo / 'configs/bench2dex/mujoco_grasp.yaml')
        gcfg['controller'].update(physics_dt_s=.001, control_dt_s=.02, finger_kp=1000., finger_kv=5., contact_latched_closure=False,
                                  wrist_position_kp=1000., wrist_position_kd=30., wrist_rotation_kp=20., wrist_rotation_kd=.2)
        gcfg['execution'].update(palm_rotation_y_deg=0., approach_offset_m=.005)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            trimesh.creation.icosphere(subdivisions=2, radius=.01).export(folder / 'object.obj')
            trimesh.creation.box(extents=[.008,.025,.015]).export(folder / 'jaw.obj')
            root = ET.Element('mujoco'); ET.SubElement(root, 'compiler', angle='radian')
            ET.SubElement(root, 'option', timestep='.001', integrator='implicitfast', cone='elliptic', noslip_iterations='10')
            asset = ET.SubElement(root, 'asset'); ET.SubElement(asset, 'mesh', name='object', file=str(folder/'object.obj')); ET.SubElement(asset, 'mesh', name='jaw', file=str(folder/'jaw.obj'))
            world = ET.SubElement(root, 'worldbody'); palm = ET.SubElement(world, 'body', name='right_palm_link')
            ET.SubElement(palm, 'inertial', pos='0 0 0', mass='.5', diaginertia='.01 .01 .01')
            names = [f'right_finger{i}_joint{j}' for i in range(1,6) for j in range(1,5)]
            for index, name in enumerate(names):
                if index in (0,4):
                    left = index == 0
                    body = ET.SubElement(palm, 'body', name=f'right_finger{1 if left else 2}_tip_link', pos=f'{-.016 if left else .016} 0 -.03')
                    ET.SubElement(body, 'joint', name=name, type='slide', axis='1 0 0' if left else '-1 0 0', range='-.01 .02')
                    ET.SubElement(body, 'geom', name=f'jaw{index}', type='mesh', mesh='jaw', mass='.01', friction='2 .005 .0001', condim='4', solref='.002 1', solimp='.95 .99 .001')
                else:
                    body = ET.SubElement(palm, 'body', name=f'dummy{index}')
                    ET.SubElement(body, 'inertial', pos='0 0 0', mass='.001', diaginertia='.000001 .000001 .000001')
                    ET.SubElement(body, 'joint', name=name, axis='0 0 1', range='-1 1')
            obj = ET.SubElement(world, 'body', name='target_object'); ET.SubElement(obj, 'freejoint', name='object_free')
            ET.SubElement(obj, 'geom', name='target_object_collision', type='mesh', mesh='object', mass='.02', friction='2 .005 .0001', condim='4', solref='.002 1', solimp='.95 .99 .001')
            ET.ElementTree(root).write(folder/'geometry.xml', encoding='unicode')
            pre=np.zeros(20); grasp=pre.copy(); grasp[[0,4]]=.003
            record={'side':'right','joint_names':names,'object_pose_in_palm_wxyz':[0,0,-.03,1,0,0,0],
                    'pregrasp_qpos_rad':pre.tolist(),'grasp_qpos_rad':grasp.tolist(),'squeeze_target_qpos_rad':grasp.tolist(), 'object':{'mass_kg':.02}}
            with patch('dexonomy.integrations.bench2dex.local_grasp._render_execution'):
                result=execute_candidate(cfg,gcfg,record,root,folder,.75)
            if not result['passed']:
                trace=np.load(folder/'execution_trace.npz')
                physical=np.load(folder/'physics_trace.npz')
                model=mujoco.MjModel.from_xml_path(str(folder/'execution.xml'));data=mujoco.MjData(model)
                for phase in ['close','lift','hold','disturbance_0','disturbance_1','disturbance_2','disturbance_3','disturbance_4','disturbance_5']:
                    index=np.flatnonzero(trace['phase']==phase)[-1]
                    pindex=np.searchsorted(physical['sim_step'],trace['sim_step'][index]+20)-1
                    data.qpos[:]=physical['qpos_after'][pindex];mujoco.mj_forward(model,data)
                    print('fixture',phase,'q',data.qpos[[model.joint(names[i]).qposadr[0] for i in [0,4]]],
                          'object',data.xipos[model.body('target_object').id],
                          'contacts',[(model.geom(c.geom1).name,model.geom(c.geom2).name,c.dist) for c in data.contact])
            self.assertTrue(result['passed'], {k:result[k] for k in ['failure_reasons','lift_m','supported_hold_frames','max_relative_translation_m','max_relative_angle_deg']})
            self.assertGreater(result['lift_m'],.05)


if __name__ == '__main__':
    unittest.main()
