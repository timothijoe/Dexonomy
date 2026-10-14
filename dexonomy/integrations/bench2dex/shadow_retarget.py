"""Three-phase Shadow -> original Wuji v1 posture and geometry prototype.

This is a kinematic optimization. It deliberately has no physical success label.
Source and target share the extracted Dexonomy object and exact scene scale.
"""
import json
from pathlib import Path
from time import monotonic

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
import yaml

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.util.file_util import load_scene_cfg
from .common import atomic_json, file_receipt, sha256

PHASES = ['pregrasp','grasp','squeeze']
FINGERS = ['thumb','index','middle','ring','pinky']
SOURCE_CHAINS = {
    'thumb':['rh_thbase','rh_thproximal','rh_thmiddle','rh_thdistal'],
    'index':['rh_ffknuckle','rh_ffproximal','rh_ffmiddle','rh_ffdistal'],
    'middle':['rh_mfknuckle','rh_mfproximal','rh_mfmiddle','rh_mfdistal'],
    'ring':['rh_rfknuckle','rh_rfproximal','rh_rfmiddle','rh_rfdistal'],
    'pinky':['rh_lfknuckle','rh_lfproximal','rh_lfmiddle','rh_lfdistal']}


def budgeted_solve(residual, initial, bounds, max_nfev, deadline):
    """Keep a finite, bounded checkpoint when a numeric solve reaches its budget."""
    best = np.asarray(initial,dtype=float).copy()
    initial_residual = residual(best)
    best_cost = float(np.dot(initial_residual,initial_residual)/2)
    evaluations = 1
    def evaluate(value):
        nonlocal best,best_cost,evaluations
        if monotonic() >= deadline: raise TimeoutError('Retarget numeric time budget exhausted')
        errors = residual(value)
        cost = float(np.dot(errors,errors)/2)
        evaluations += 1
        if np.isfinite(cost) and cost < best_cost:
            best,best_cost = value.copy(),cost
        return errors
    try:
        fit = least_squares(evaluate,initial,bounds=bounds,max_nfev=max_nfev,ftol=1e-6)
        return fit.x,{'success':bool(fit.success),'nfev':int(fit.nfev),'cost':float(fit.cost),
                      'residual_evaluations':evaluations,
                      'termination':'converged' if fit.success else 'evaluation_limit'}
    except TimeoutError:
        return best,{'success':False,'nfev':None,'cost':best_cost,
                     'residual_evaluations':evaluations,'termination':'time_budget_checkpoint'}


def minimum_surface_distance(model,data,hand_geoms,object_geoms,contact_depths=None):
    """Prune only pairs whose enclosing spheres cannot beat the current gap."""
    if not hand_geoms or not object_geoms:raise ValueError('Both contact regions must contain collision geometry')
    if contact_depths is None:
        contact_depths = {}
        for contact in data.contact:
            pair=tuple(sorted([int(contact.geom1),int(contact.geom2)]))
            contact_depths[pair]=min(contact_depths.get(pair,1.),float(contact.dist))
    pairs=[]
    for h in hand_geoms:
        for o in object_geoms:
            lower=float(np.linalg.norm(data.geom_xpos[h]-data.geom_xpos[o])-model.geom_rbound[h]-model.geom_rbound[o])
            # Planes have unbounded extent; they cannot use sphere pruning.
            if model.geom_type[h]==mujoco.mjtGeom.mjGEOM_PLANE or model.geom_type[o]==mujoco.mjtGeom.mjGEOM_PLANE: lower=-np.inf
            pairs.append((lower,h,o))
    best=1.
    for lower,h,o in sorted(pairs):
        if lower>best+1e-10:continue
        value=float(mujoco.mj_geomDistance(model,data,h,o,1.,None))
        value=min(value,contact_depths.get(tuple(sorted([h,o])),1.))
        best=min(best,value)
    return best


def resample_chain(points, fractions=(.25,.5,.75,1.)):
    points = np.asarray(points,dtype=float)
    length = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    keep = np.r_[True,np.diff(length)>1e-9]
    points,length = points[keep],length[keep]
    if length[-1] < 1e-6: raise ValueError('Degenerate finger chain')
    return np.array([np.interp(np.asarray(fractions)*length[-1],length,points[:,axis]) for axis in range(3)]).T,length[-1]


class HandGeometry:
    def __init__(self, env, kind):
        self.env,self.kind,self.model,self.data = env,kind,env._model,env._data
        self.palm_name = 'rh_palm' if kind=='shadow' else 'right_palm_link'
        self.chains = SOURCE_CHAINS if kind=='shadow' else {
            f:[f'right_finger{i}_{link}' for link in ['link1','link2','link3','link4']]
            for i,f in enumerate(FINGERS,1)}
        self.bodies = {f:[self.model.body('hand-'+n).id for n in chain] for f,chain in self.chains.items()}
        self.palm = self.model.body('hand-'+self.palm_name).id
        self.qidx = [int(self.model.jnt_qposadr[j]) for j in range(self.model.njnt)
                     if self.model.jnt_type[j]==mujoco.mjtJoint.mjJNT_HINGE and self.model.joint(j).name.startswith('hand-')]
        self.names = [self.model.joint(j).name for j in range(self.model.njnt)
                      if self.model.jnt_type[j]==mujoco.mjtJoint.mjJNT_HINGE and self.model.joint(j).name.startswith('hand-')]
        self.limits = np.array([self.model.jnt_range[self.model.joint(n).id] for n in self.names])
        expected = 22 if kind=='shadow' else 20
        if len(self.names)!=expected or self.qidx != list(range(7,7+expected)):
            raise ValueError('Hand state layout disagrees with explicit original model')
        self.neutral = np.r_[0,0,0,1,0,0,0,np.clip(np.zeros(expected),self.limits[:,0]+1e-5,self.limits[:,1]-1e-5)]
        self.set_pose(self.neutral)
        self.tip_bodies,self.tip_local = {},{}
        for i,f in enumerate(FINGERS,1):
            name = self.chains[f][-1] if kind=='shadow' else f'right_finger{i}_tip_link'
            bid = self.model.body('hand-'+name).id
            mesh = env.get_body_mesh(name)
            axis_world = self.data.xpos[bid]-self.data.xpos[self.bodies[f][0]]
            axis_local = self.data.xmat[bid].reshape(3,3).T @ axis_world
            axis_local /= np.linalg.norm(axis_local)
            projections = mesh.vertices @ axis_local
            self.tip_bodies[f] = bid
            self.tip_local[f] = mesh.vertices[projections >= np.quantile(projections,.9)].mean(axis=0)
        self.neutral_frame = self.frame()
        neutral_points,_,_ = self.features(self.neutral)
        self.lengths = np.array([resample_chain(self.points(f))[1] for f in FINGERS])
        self.neutral_shape = neutral_points / self.lengths[:,None,None]
        self.hand_geoms = {i for i in range(self.model.ngeom) if self.model.geom_contype[i] and self.model.body(int(self.model.geom_bodyid[i])).name.startswith('hand-')}
        self.object_geoms = {i for i in range(self.model.ngeom) if self.model.geom_contype[i] and self.model.body(int(self.model.geom_bodyid[i])).name.startswith('obj-')}
        self.hand_geom_list = sorted(self.hand_geoms)
        self.allowed = {}
        for i,f in enumerate(FINGERS,1):
            names = ['hand-'+self.chains[f][-1]] if kind=='shadow' else [f'hand-right_finger{i}_{link}' for link in ['link3','link4','tip_link']]
            self.allowed[f] = [gid for gid in self.hand_geom_list if self.model.body(int(self.model.geom_bodyid[gid])).name in names]
        self.exclusions = {frozenset([i,int(self.model.body_parentid[i])]) for i in range(1,self.model.nbody)}
        if kind=='wuji':
            for i in range(1,6):
                for link in ['link1','link2']:
                    self.exclusions.add(frozenset([self.palm,self.model.body(f'hand-right_finger{i}_{link}').id]))

    def set_pose(self,q):
        # Kinematics only; never used as an execution or physical replay.
        self.data.qpos[:] = np.r_[q,self.env._obj_init_qpos]
        mujoco.mj_fwdPosition(self.model,self.data)
        self.contact_depths = {}
        for contact in self.data.contact:
            pair=tuple(sorted([int(contact.geom1),int(contact.geom2)]))
            self.contact_depths[pair]=min(self.contact_depths.get(pair,1.),float(contact.dist))

    def frame(self):
        p = self.data.xpos
        index,middle,ring = (p[self.bodies[f][0]] for f in ['index','middle','ring'])
        right=index-ring; right=right/np.linalg.norm(right)
        forward=middle-p[self.palm]; forward=forward-right*np.dot(right,forward)
        forward=forward/np.linalg.norm(forward)
        return np.stack([right,forward,np.cross(right,forward)],axis=1)

    def points(self,f):
        bid=self.tip_bodies[f]
        tip=self.data.xpos[bid]+self.data.xmat[bid].reshape(3,3)@self.tip_local[f]
        return np.vstack([self.data.xpos[self.bodies[f]],tip])

    def features(self,q):
        self.set_pose(q); frame=self.frame()
        sampled=[];tips=[]
        for f in FINGERS:
            points=self.points(f)
            sample,_=resample_chain(points)
            sampled.append((sample-points[0])@frame)
            tips.append(points[-1])
        return np.array(sampled),np.array(tips),frame

    def distances(self, category):
        regions=self.allowed
        if self.kind=='wuji' and category=='13_Precision_Sphere':
            regions={f:[gid for gid in gids if self.model.body(int(self.model.geom_bodyid[gid])).name.endswith('tip_link')] for f,gids in regions.items()}
        return np.array([minimum_surface_distance(self.model,self.data,regions[f],self.object_geoms,self.contact_depths) for f in FINGERS])

    def collision(self):
        ho=np.zeros(len(self.hand_geom_list)); hh=0.; contact_bodies=set()
        for c in self.data.contact:
            a,b=int(c.geom1),int(c.geom2)
            if (a in self.hand_geoms and b in self.object_geoms) or (b in self.hand_geoms and a in self.object_geoms):
                h=a if a in self.hand_geoms else b
                ho[self.hand_geom_list.index(h)] = max(ho[self.hand_geom_list.index(h)],-float(c.dist))
                contact_bodies.add(self.model.body(int(self.model.geom_bodyid[h])).name)
            elif a in self.hand_geoms and b in self.hand_geoms:
                pair=frozenset([int(self.model.geom_bodyid[a]),int(self.model.geom_bodyid[b])])
                if pair not in self.exclusions: hh=max(hh,-float(c.dist))
        return ho,hh,sorted(contact_bodies)


def pose_variables(q):
    return np.r_[q[:3],Rotation.from_quat(q[3:7][[1,2,3,0]]).as_rotvec(),q[7:]]


def variables_pose(x):
    return np.r_[x[:3],Rotation.from_rotvec(x[3:6]).as_quat()[[3,0,1,2]],x[6:]]


def transfer(selection, target_model, config_path, output, render=True):
    output=Path(output)
    if output.exists(): raise ValueError('Transfer output exists; use a new directory')
    output.mkdir(parents=True)
    started=monotonic()
    cfg=yaml.safe_load(Path(config_path).read_text())
    if cfg.get('schema_version')!=1 or cfg.get('target_model_family')!='wuji_v1_bench2dex':
        raise ValueError('Expected original Wuji v1 retarget configuration')
    deadline=started+cfg['timeout_s_per_source']
    source=Path(selection['source']['path'])
    if sha256(source)!=selection['source']['sha256']: raise ValueError('Shadow source checksum changed')
    raw=np.load(source,allow_pickle=True).item()
    index=selection['source_index']
    count=len(np.asarray(raw['grasp_qpos']))
    if not isinstance(index,int) or not 0<=index<count:
        raise ValueError('Source index outside selected Shadow file')
    if any(np.asarray(raw[p+'_qpos']).shape!=(count,29) for p in PHASES):
        raise ValueError('Shadow source must contain named three-phase 29D poses')
    source_poses=[np.asarray(raw[p+'_qpos'])[index].astype(float) for p in PHASES]
    if not all(np.isfinite(q).all() and abs(np.linalg.norm(q[3:7])-1)<1e-4 for q in source_poses):
        raise ValueError('Invalid source pose or wxyz quaternion')
    scene=load_scene_cfg(str(raw['scene_path']))
    object_name=scene['task']['obj_name']; obj=scene['scene'][object_name]
    obj['scale']=np.asarray(obj['scale'],dtype=float)*float(np.asarray(raw['scene_scale'])[index])
    source_env=MuJoCo_VisEnv(HandCfg('assets/hand/shadow/right.xml',freejoint=True),scene,vis_mode='collision')
    target_env=MuJoCo_VisEnv(HandCfg(str(target_model),freejoint=True),scene,vis_mode='collision')
    sh,w=HandGeometry(source_env,'shadow'),HandGeometry(target_env,'wuji')
    source_shape,source_tips,anchors,source_quality=[],[],[],{}
    for phase,q in zip(PHASES,source_poses):
        shape,tips,frame=sh.features(q)
        source_shape.append(shape/sh.lengths[:,None,None]); source_tips.append(tips)
        rot=frame@w.neutral_frame.T
        w.set_pose(w.neutral)
        pos=sh.data.xpos[sh.palm]-rot@w.data.xpos[w.palm]
        anchors.append(np.r_[pos,Rotation.from_matrix(rot).as_quat()[[3,0,1,2]],w.neutral[7:]])
        ho,hh,bodies=sh.collision()
        source_quality[phase]={'max_hand_object_penetration_m':float(ho.max()),'max_self_penetration_m':hh,'contact_bodies':bodies}
    source_shape=np.asarray(source_shape); source_tips=np.asarray(source_tips); anchors=np.asarray(anchors)
    shape_fit=[];shape_solvers=[]
    for i,anchor in enumerate(anchors):
        def residual(qj):
            shape,_,_=w.features(np.r_[anchor[:7],qj]); shape=shape/w.lengths[:,None,None]
            return np.r_[(cfg['shape_weight']*(shape-source_shape[i])).ravel(),
                         (cfg['action_weight']*((shape-w.neutral_shape)-(source_shape[i]-sh.neutral_shape))).ravel(),
                         cfg['joint_prior_weight']*(qj-anchor[7:])]
        fitted,info=budgeted_solve(residual,anchor[7:],(w.limits[:,0]+1e-5,w.limits[:,1]-1e-5),cfg['max_nfev_shape'],deadline)
        shape_fit.append(np.r_[anchor[:7],fitted]);shape_solvers.append(info)
    shape_fit=np.asarray(shape_fit)
    initial=np.array([pose_variables(q) for q in shape_fit])
    lower=np.array([np.r_[x[:3]-.08,x[3:6]-.8,w.limits[:,0]+1e-5] for x in initial])
    upper=np.array([np.r_[x[:3]+.08,x[3:6]+.8,w.limits[:,1]-1e-5] for x in initial])
    # Corresponding source fingers are required for sphere grasps. Other
    # categories use source near-contact fingers, avoiding five-finger inflation.
    sh.features(source_poses[1]); near=sh.distances(selection['category'])<.002
    required=np.ones(5,dtype=bool) if selection['category'] in ['13_Precision_Sphere','11_Power_Sphere'] else near
    if not required.any(): required[np.argsort(sh.distances(selection['category']))[:3]]=True
    def joint_residual(flat):
        variables=flat.reshape(3,26); residuals=[];shapes=[]
        for i,x in enumerate(variables):
            shape,tips,_=w.features(variables_pose(x)); shape=shape/w.lengths[:,None,None];shapes.append(shape)
            ho,hh,_=w.collision()
            residuals += [(cfg['shape_weight']*(shape-source_shape[i])).ravel(),
                          (cfg['action_weight']*((shape-w.neutral_shape)-(source_shape[i]-sh.neutral_shape))).ravel(),
                          ((tips-source_tips[i])/cfg['world_tip_scale_m']).ravel(),
                          (x[:3]-initial[i,:3])/cfg['palm_scale_m'],
                          cfg['orientation_weight']*(x[3:6]-initial[i,3:6]),
                          cfg['joint_prior_weight']*(x[6:]-initial[i,6:]),
                          np.maximum(ho-.0005,0)/cfg['collision_scale_m'],np.array([max(hh-.0005,0)/cfg['collision_scale_m']])]
            if i>0:
                desired=cfg['target_grasp_gap_m'] if i==1 else cfg['target_squeeze_gap_m']
                residuals.append((w.distances(selection['category'])[required]-desired)/cfg['contact_scale_m'])
        for i in [1,2]: residuals.append((cfg['transition_weight']*((shapes[i]-shapes[i-1])-(source_shape[i]-source_shape[i-1]))).ravel())
        return np.concatenate(residuals)
    solved,solver_info=budgeted_solve(joint_residual,initial.ravel(),(lower.ravel(),upper.ravel()),cfg['max_nfev_joint'],deadline)
    result=np.array([variables_pose(x) for x in solved.reshape(3,26)])
    def measurements(poses):
        metrics={}; shapes=[]
        for i,(phase,q) in enumerate(zip(PHASES,poses)):
            shape,tips,_=w.features(q);shape=shape/w.lengths[:,None,None];shapes.append(shape)
            ho,hh,bodies=w.collision()
            metrics[phase]={'mean_shape_error':float(np.linalg.norm(shape-source_shape[i],axis=2).mean()),
                           'mean_action_error':float(np.linalg.norm((shape-w.neutral_shape)-(source_shape[i]-sh.neutral_shape),axis=2).mean()),
                           'mean_world_tip_error_m':float(np.linalg.norm(tips-source_tips[i],axis=1).mean()),
                           'max_hand_object_penetration_m':float(ho.max()),'max_self_penetration_m':hh,
                           'contact_bodies':bodies,'finger_surface_gaps_m':w.distances(selection['category']).tolist(),
                           'min_joint_margin_rad':float(np.minimum(q[7:]-w.limits[:,0],w.limits[:,1]-q[7:]).min())}
        transitions=[float(np.linalg.norm((shapes[i]-shapes[i-1])-(source_shape[i]-source_shape[i-1]),axis=2).mean()) for i in [1,2]]
        return {'phases':metrics,'transition_errors':transitions}
    initial_quality,final_quality=measurements(shape_fit),measurements(result)
    reasons=[]
    for phase,m in final_quality['phases'].items():
        if max(m['max_hand_object_penetration_m'],m['max_self_penetration_m'])>cfg['penetration_tolerance_m']:reasons.append(phase+'_penetration')
        if m['mean_shape_error']>cfg['max_shape_error']:reasons.append(phase+'_shape_deviation')
        if m['mean_action_error']>cfg['max_action_error']:reasons.append(phase+'_action_deviation')
        if phase!='pregrasp' and max(abs(np.asarray(m['finger_surface_gaps_m'])[required]))>.002:reasons.append(phase+'_required_contact_missing')
    if max(final_quality['transition_errors'])>cfg['max_transition_error']:reasons.append('stage_action_deviation')
    np.savez_compressed(output/'postures.npz',source_qpos=source_poses,wuji_initial_qpos=shape_fit,wuji_optimized_qpos=result,phase=PHASES)
    report={'schema_version':1,'status':'kinematic_candidate' if not reasons else 'kinematic_rejected',
            'bench_targets':[selection['bench_object']],'source_selection':selection,
            'target_model_family':'wuji_v1_bench2dex','target_model':file_receipt(Path(target_model)),
            'source_hand_model':file_receipt(Path('assets/hand/shadow/right.xml')),
            'config':file_receipt(Path(config_path)),'implementation':file_receipt(Path(__file__)),
            'object_scene':file_receipt(Path(raw['scene_path'])),'object_scale_xyz':obj['scale'].tolist(),
            'object_geometry':file_receipt(Path(obj['file_path'])),
            'joint_names':w.names,'finger_mapping':dict(zip(FINGERS,[f'right_finger{i}' for i in range(1,6)])),
            'tip_definition':'distal 10% cap of actual collision mesh along neutral base-to-tip direction',
            'shape_definition':'four arc-length-resampled chain points per finger, in anatomical palm frame, divided by neutral chain length',
            'source_quality':source_quality,'initial_quality':initial_quality,'optimized_quality':final_quality,
            'required_fingers':[f for f,yes in zip(FINGERS,required) if yes],
            'failure_reasons':reasons,'solver':solver_info,'shape_solvers':shape_solvers,
            'seconds':monotonic()-started,'physical_passed':None,'full_task_passed':None,
            'limitations':['Static three-pose optimization, no actual control execution',
                           'Uses matched Dexonomy source geometry, not Bench2Dex USD geometry',
                           'Shared YCB identifier does not certify mesh identity',
                           'Declared palm/root assembly pairs excluded from self-penetration metrics',
                           'Source squeeze contacts must be revalidated before physical use']}
    atomic_json(output/'result.json',report)
    if render:
        try:
            render_comparison(sh,w,source_poses,shape_fit,result,output)
            render_hand_only(sh,w,source_poses,shape_fit,result,output/'hand_only')
        except Exception as exc:
            report['render_error']=f'{type(exc).__name__}: {exc}'
            atomic_json(output/'result.json',report)
    return report


def render_hand_only(sh,w,source,initial,result,output):
    """Shared anatomical palm frame, with original hand sizes and object hidden."""
    def aligned(hand,poses):
        transformed=[]
        for q in poses:
            hand.set_pose(q);frame=hand.frame();palm=hand.data.xpos[hand.palm].copy()
            pose=q.copy();pose[:3]=frame.T@(q[:3]-palm)
            rotation=frame.T@Rotation.from_quat(q[3:7][[1,2,3,0]]).as_matrix()
            pose[3:7]=Rotation.from_matrix(rotation).as_quat()[[3,0,1,2]]
            transformed.append(pose)
        return np.asarray(transformed)
    poses=aligned(sh,source),aligned(w,initial),aligned(w,result)
    saved=[]
    for hand in [sh,w]:
        saved.append((hand.object_geoms,hand.env._body_mesh_dict))
        hand.object_geoms=set()
        hand.env._body_mesh_dict={name:mesh for name,mesh in hand.env._body_mesh_dict.items() if name.startswith('hand-')}
    output.mkdir(parents=True,exist_ok=True)
    try:render_comparison(sh,w,*poses,output)
    finally:
        for hand,(geoms,meshes) in zip([sh,w],saved):hand.object_geoms,hand.env._body_mesh_dict=geoms,meshes


def render_comparison(sh,w,source,initial,result,output):
    from PIL import Image,ImageDraw
    images=[]; bounds=[]
    for hand,poses in [(sh,source),(w,initial),(w,result)]:
        for q in poses:
            hand.set_pose(q)
            for name in hand.env.get_all_body_names():
                bid=hand.env.get_body_id(name); mesh=hand.env.get_body_mesh(name)
                points=mesh.vertices@hand.data.xmat[bid].reshape(3,3).T+hand.data.xpos[bid]
                bounds.extend([points.min(axis=0),points.max(axis=0)])
    lo,hi=np.min(bounds,axis=0),np.max(bounds,axis=0)
    camera=mujoco.MjvCamera();camera.lookat[:]=(lo+hi)/2
    camera.distance=max(.3,float((hi-lo).max())*2.1);camera.azimuth=135;camera.elevation=-25
    option=mujoco.MjvOption();option.geomgroup[1]=0
    for hand,poses,label in [(sh,source,'Shadow source'),(w,initial,'Wuji v1 shape initial'),(w,result,'Wuji v1 joint optimization')]:
        hand.model.vis.global_.offwidth=640;hand.model.vis.global_.offheight=480
        for gid in range(hand.model.ngeom):
            if gid in hand.hand_geoms:
                hand.model.geom_group[gid]=0
                hand.model.geom_rgba[gid]=[.8,.3,.15,1] if hand.kind=='shadow' else [.15,.55,.8,1]
            elif gid in hand.object_geoms:
                hand.model.geom_group[gid]=0
                hand.model.geom_rgba[gid]=[.8,.7,.2,1]
            else:hand.model.geom_group[gid]=1
        with mujoco.Renderer(hand.model,height=480,width=640) as renderer:
            for phase,q in zip(PHASES,poses):
                hand.set_pose(q); renderer.update_scene(hand.data,camera=camera,scene_option=option)
                image=Image.fromarray(renderer.render());draw=ImageDraw.Draw(image)
                draw.rectangle((0,0,640,45),fill=(15,20,28));draw.text((10,10),label+' | '+phase,fill='white')
                draw.text((10,28),'STATIC POSTURE COMPARISON - physical execution not tested',fill='white')
                images.append(image)
    canvas=Image.new('RGB',(1920,1440))
    for i,image in enumerate(images):canvas.paste(image,((i%3)*640,(i//3)*480))
    canvas.save(output/'comparison.png')
