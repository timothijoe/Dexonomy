"""Controlled suspended-hold probe: fixed wrist, free object, native torques.

Diagnostic simulation only; not a table approach/lift or hardware success label.
"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from dexonomy.sim import HandCfg, MuJoCo_VisEnv, MuJoCo_EvalCfg
from dexonomy.util.file_util import load_scene_cfg
from .common import atomic_json, file_receipt, sha256

CONFIG = {'dt_s': .0005, 'duration_s': 1.2, 'pressure_ramp_s': .15,
          'finger_kp': 20., 'finger_kv': .2, 'condim': 3,
          'solref': [.005, 1.], 'solimp': [.95, .99, .001],
          'max_translation_m': .01, 'max_rotation_deg': 10.,
          'max_penetration_m': .002, 'minimum_force_weight_ratio': .8,
          'maximum_force_weight_ratio': 1.2}


def context(folder):
    folder = Path(folder); r = json.loads((folder / 'result.json').read_text())
    v2 = json.loads(Path(r['baseline_result']['path']).read_text())
    original = json.loads(Path(v2['baseline_result']['path']).read_text())
    scene = load_scene_cfg(r['source_selection']['scene_path'])
    obj = scene['scene'][scene['task']['obj_name']]
    obj['scale'] = np.asarray(obj['scale']) * r['source_selection']['scene_scale_multiplier']
    if sha256(original['target_model']['path']) != original['target_model']['sha256']:
        raise ValueError('Original target model changed')
    return r, original, scene


def build_model(folder, pose, friction, destination, cfg=CONFIG):
    r, original, scene = context(folder)
    env = MuJoCo_VisEnv(HandCfg(original['target_model']['path'], freejoint=False), scene,
                       sim_cfg=MuJoCo_EvalCfg(obj_freejoint=True, timestep=cfg['dt_s']), vis_mode='collision')
    root = ET.fromstring(env._spec.to_xml())
    option = root.find('option')
    if option is None: option = ET.SubElement(root, 'option')
    option.set('gravity', '0 0 -9.81'); option.set('timestep', str(cfg['dt_s']))
    option.set('integrator', 'implicitfast'); option.set('cone', 'elliptic')
    flags = option.find('flag')
    if flags is None: flags = ET.SubElement(option, 'flag')
    flags.set('gravity', 'enable')
    hand = next(b for b in root.iter('body') if b.get('name') == 'hand-world')
    hand.set('pos', ' '.join(map(str, pose[:3]))); hand.set('quat', ' '.join(map(str, pose[3:7])))
    for joint in root.iter('joint'): joint.set('margin', '0')
    for geom in root.iter('geom'):
        if geom.get('contype') == '0': continue
        geom.set('condim', str(cfg['condim'])); geom.set('margin', '0')
        geom.set('friction', f'{friction} .005 .0001')
        geom.set('solref', ' '.join(map(str, cfg['solref'])))
        geom.set('solimp', ' '.join(map(str, cfg['solimp'])))
    actuator = root.find('actuator')
    if actuator is not None: root.remove(actuator)
    actuator = ET.SubElement(root, 'actuator')
    for name in r['joint_names']:
        ET.SubElement(actuator, 'position', name='probe_' + name, joint=name,
                      kp=str(cfg['finger_kp']), kv=str(cfg['finger_kv']))
    contacts = root.find('contact')
    if contacts is None: contacts = ET.SubElement(root, 'contact')
    for finger in range(1, 6):
        for link in ['link1', 'link2']:
            ET.SubElement(contacts, 'exclude', body1='hand-right_palm_link', body2=f'hand-right_finger{finger}_{link}')
    destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(destination, encoding='unicode')
    model = mujoco.MjModel.from_xml_path(str(destination))
    joints = [model.joint(n).id for n in r['joint_names']]
    qidx = [int(model.jnt_qposadr[j]) for j in joints]
    vidx = [int(model.jnt_dofadr[j]) for j in joints]
    hand_geoms = {g for g in range(model.ngeom) if model.geom_contype[g] and model.body(int(model.geom_bodyid[g])).name.startswith('hand-')}
    object_geoms = {g for g in range(model.ngeom) if model.geom_contype[g] and model.body(int(model.geom_bodyid[g])).name.startswith('obj-')}
    free = [j for j in range(model.njnt) if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE]
    if len(free) != 1 or model.nu != 20 or model.neq != 0: raise ValueError('Object must be free, wrist fixed, no hidden welds')
    obj_bid = int(model.jnt_bodyid[free[0]])
    if model.body(obj_bid).name.startswith('hand-'): raise ValueError('Wrong free body')
    if model.opt.disableflags & int(mujoco.mjtDisableBit.mjDSBL_GRAVITY): raise ValueError('Gravity still disabled')
    if np.any(model.body_gravcomp): raise ValueError('Hidden gravity compensation')
    return model, qidx, vidx, joints, hand_geoms, object_geoms, obj_bid


def probe(folder, pose, output, friction=.5, pressure_rad=0., control_enabled=True, cfg=CONFIG, hand_collision_enabled=True):
    output = Path(output)
    if output.exists(): raise ValueError('Use fresh probe output')
    output.mkdir(parents=True)
    model, qidx, vidx, joints, hand_geoms, object_geoms, obj_bid = build_model(folder, pose, friction, output/'model.xml', cfg)
    if not hand_collision_enabled:
        model.geom_contype[list(hand_geoms)]=0;model.geom_conaffinity[list(hand_geoms)]=0
    data = mujoco.MjData(model); data.qpos[qidx] = pose[7:]; data.ctrl[:] = pose[7:]
    if not control_enabled:
        model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_ACTUATION)
    mujoco.mj_forward(model, data)
    initial_com = data.xipos[obj_bid].copy(); initial_rotation = data.xmat[obj_bid].reshape(3,3).copy()
    initial_qpos=data.qpos.copy()
    weight = model.body_subtreemass[obj_bid] * 9.81
    limits = model.jnt_range[joints]; effort = np.max(np.abs(model.jnt_actfrcrange[joints]), axis=1)
    if not np.all(model.jnt_actfrclimited[joints]) or np.any(effort <= 0): raise ValueError('Native torque limits must be active')
    target = np.asarray(pose[7:]).copy()
    for i in range(5):
        # Only flexion axes, never abduction or thumb opposition axes.
        target[4*i+2:4*i+4] += pressure_rad
    target = np.clip(target, limits[:,0]+1e-5, limits[:,1]-1e-5)
    rows=[]; qpos=[]; controls=[]; peak_penetration=0.; peak_translation=0.; peak_rotation=0.; peak_effort_ratio=0.
    early_reason=None
    for step in range(int(round(cfg['duration_s']/cfg['dt_s']))):
        amount=min(1., (step+1)*cfg['dt_s']/cfg['pressure_ramp_s'])
        data.ctrl[:]=pose[7:]+amount*(target-pose[7:])
        # No qpos reset, object forces, teleportation or object attachment after initialization.
        mujoco.mj_step(model,data)
        if not np.isfinite(data.qpos).all(): early_reason='nonfinite_state';break
        pen=max([max(0.,-float(c.dist)) for c in data.contact if
                 (int(c.geom1) in hand_geoms and int(c.geom2) in object_geoms) or
                 (int(c.geom2) in hand_geoms and int(c.geom1) in object_geoms)],default=0.)
        peak_penetration=max(peak_penetration,pen)
        peak_effort_ratio=max(peak_effort_ratio,float(np.max(np.abs(data.qfrc_actuator[vidx])/effort)))
        if step%10==0 or step==int(round(cfg['duration_s']/cfg['dt_s']))-1:
            mujoco.mj_forward(model,data)
            delta=float(np.linalg.norm(data.xipos[obj_bid]-initial_com))
            rotation=Rotation.from_matrix(data.xmat[obj_bid].reshape(3,3)@initial_rotation.T).magnitude()
            force=np.zeros(3);loaded=set()
            for ci,c in enumerate(data.contact):
                a,b=int(c.geom1),int(c.geom2)
                if not ((a in hand_geoms and b in object_geoms) or (b in hand_geoms and a in object_geoms)):continue
                local=np.zeros(6);mujoco.mj_contactForce(model,data,ci,local)
                if c.efc_address<0 or local[0]<=1e-8:continue
                force+=c.frame.reshape(3,3).T@local[:3]*(1 if b in object_geoms else -1)
                loaded.add(model.body(int(model.geom_bodyid[a if a in hand_geoms else b])).name)
            peak_translation=max(peak_translation,delta);peak_rotation=max(peak_rotation,float(np.rad2deg(rotation)))
            rows.append({'time_s':float(data.time),'translation_m':delta,'rotation_deg':float(np.rad2deg(rotation)),
                         'hand_up_force_n':float(force[2]),'loaded_links':sorted(loaded),'object_com_z_m':float(data.xipos[obj_bid,2])})
            qpos.append(data.qpos.copy());controls.append(data.ctrl.copy())
            if delta>.05:early_reason='object_left_grasp';break
    final_window=[r for r in rows if r['time_s']>=cfg['duration_s']-.3]
    ratio=float(np.mean([r['hand_up_force_n'] for r in final_window])/weight) if final_window else None
    failures=[]
    if early_reason:failures.append(early_reason)
    if peak_translation>cfg['max_translation_m']:failures.append('slipped_or_dropped')
    if peak_rotation>cfg['max_rotation_deg']:failures.append('rotation_exceeded')
    if peak_penetration>cfg['max_penetration_m']:failures.append('penetration_exceeded')
    if ratio is None or not cfg['minimum_force_weight_ratio']<=ratio<=cfg['maximum_force_weight_ratio']:failures.append('insufficient_steady_support')
    trace=output/'trace.npz';np.savez_compressed(trace,qpos=np.asarray(qpos),qpos_initial=initial_qpos,ctrl=np.asarray(controls),time_s=[r['time_s'] for r in rows])
    report={'scope':'fixed-wrist suspended hold probe, not table closure/lift','passed':not failures,
            'failure_reasons':failures,'friction_coefficient':friction,'pressure_rad':pressure_rad,
            'native_torque_limits_nm':effort.tolist(),'finger_kp':cfg['finger_kp'],'finger_kv':cfg['finger_kv'],
            'object_mass_kg':float(weight/9.81),'object_weight_n':float(weight),'duration_s':float(data.time),
            'max_translation_m':peak_translation,'max_rotation_deg':peak_rotation,
            'max_hand_object_penetration_m':peak_penetration,'max_joint_effort_fraction':peak_effort_ratio,
            'steady_hand_force_weight_ratio':ratio,'control_enabled':control_enabled,
            'input_hand_pose_qpos':np.asarray(pose).tolist(),
            'hand_collision_enabled':hand_collision_enabled,
            'gravity_enabled':True,'object_free':True,'object_attached':False,'object_gravity_compensation':False,
            'object_external_force_n':0,'wrist_fixed':True,'config':cfg,'rows':rows,
            'trace':file_receipt(trace),'model':file_receipt(output/'model.xml'),
            'limitations':['Scene mass is a Dexonomy density/decomposition estimate',
                           'No table, pregrasp approach, lift or disturbance tested',
                           'Contact parameters have not been calibrated to hardware or Isaac']}
    atomic_json(output/'result.json',report)
    return report
