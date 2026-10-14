"""Source-guided thumb refinement with explicit V1 comparison and rollback.

Geometry-derived pad references are proxies, not hardware contact calibration.
This optimizer produces static poses, never physical execution labels.
"""
import json
from pathlib import Path
from time import monotonic

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh
import yaml

from dexonomy.sim import HandCfg,MuJoCo_VisEnv
from dexonomy.util.file_util import load_scene_cfg
from .common import atomic_json,file_receipt,sha256
from .shadow_retarget import HandGeometry,PHASES,budgeted_solve,resample_chain,pose_variables,variables_pose,render_comparison,render_hand_only


def unit(vector):
    length=float(np.linalg.norm(vector))
    if length<1e-9:raise ValueError('Degenerate thumb direction')
    return np.asarray(vector)/length


def pad_calibration(sh,w,annotation_path):
    annotation=yaml.safe_load(Path(annotation_path).read_text())
    pose=np.r_[0,0,0,1,0,0,0,annotation['qpos']]
    sh.set_pose(pose)
    contact=np.asarray(annotation['contact']['rh_thdistal'],dtype=float)
    bid=sh.tip_bodies['thumb'];rotation=sh.data.xmat[bid].reshape(3,3)
    source_point=rotation.T@(contact[:3]-sh.data.xpos[bid])
    source_normal=unit(rotation.T@contact[3:])
    source_mesh=sh.env.get_body_mesh('rh_thdistal')
    _,distance,_=trimesh.proximity.closest_point_naive(source_mesh,source_point[None])
    if distance[0]>.002:raise ValueError('Source pad annotation does not fit the installed collision mesh')
    w.set_pose(w.neutral)
    _,tips,_=w.features(w.neutral)
    points=w.points('thumb');long=unit(points[-1]-points[-2])
    inward=tips[1:3].mean(axis=0)-tips[0];inward=unit(inward-long*np.dot(long,inward))
    target_bid=w.tip_bodies['thumb'];target_rotation=w.data.xmat[target_bid].reshape(3,3)
    target_mesh=w.env.get_body_mesh('right_finger1_tip_link')
    normal_hint=target_rotation.T@inward
    scores=target_mesh.face_normals@normal_hint;face=int(np.argmax(scores))
    target_normal=unit(target_mesh.face_normals[face])
    target_point=target_mesh.triangles_center[face].copy()
    return {'source_normal_local':source_normal,'target_normal_local':target_normal,
            'target_patch_local':target_point,'source_annotation_point_local':source_point,
            'source_annotation_surface_distance_m':float(distance[0]),'target_normal_alignment':float(scores[face]),
            'annotation':file_receipt(Path(annotation_path)),
            'method':'Shadow human-annotated distal contact normal; Wuji collision face facing index/middle in neutral pose',
            'limitation':'Wuji pad face is an anatomical geometry proxy; actual sensor/contact patch uncalibrated'}


def thumb_features(hand,q,normal_local):
    shape,tips,frame=hand.features(q)
    points=hand.points('thumb');samples,_=resample_chain(points)
    base=points[0];length=hand.lengths[0]
    palm=(samples-hand.data.xpos[hand.palm])@frame/length
    chain=np.vstack([base,samples]);directions=np.diff(chain,axis=0)
    directions=directions/np.linalg.norm(directions,axis=1)[:,None]
    directions=directions@frame
    opposition=np.array([(tips[i]-tips[0])@frame/((length+hand.lengths[i])/2) for i in [1,2]])
    normal=unit(hand.data.xmat[hand.tip_bodies['thumb']].reshape(3,3)@normal_local)@frame
    return {'palm':palm,'directions':directions,'opposition':opposition,'pad_normal':normal},shape/hand.lengths[:,None,None],tips


def thumb_metrics(source,target):
    parts={}
    for key in ['palm','directions','opposition']:
        parts[key]=float(np.linalg.norm(target[key]-source[key],axis=1).mean())
    parts['pad_chord']=float(np.linalg.norm(target['pad_normal']-source['pad_normal']))
    parts['pad_angle_deg']=float(np.rad2deg(np.arccos(np.clip(np.dot(source['pad_normal'],target['pad_normal']),-1,1))))
    parts['score']=parts['palm']+parts['opposition']+.5*parts['directions']+.5*parts['pad_chord']
    return parts


def closest_source_thumb_region(sh,q):
    sh.set_pose(q);best=None
    for h in sh.allowed['thumb']:
        for obj in sh.object_geoms:
            points=np.zeros(6);distance=float(mujoco.mj_geomDistance(sh.model,sh.data,h,obj,1.,points))
            contacts=[c for c in sh.data.contact if {int(c.geom1),int(c.geom2)}=={h,obj}]
            if contacts:
                c=min(contacts,key=lambda c:c.dist)
                if float(c.dist)<distance:
                    distance=float(c.dist)
                    normal=np.asarray(c.frame[:3])*(1 if c.geom1==h else -1)
                    points[3:]=np.asarray(c.pos)+.5*distance*normal
            if best is None or distance<best[0]:best=(distance,points[3:].copy())
    return best


def geometry_quality(w,poses,source_shapes,source_tips,source_neutral,required,category,cfg):
    phases={};shapes=[];failures=[]
    for index,(phase,q) in enumerate(zip(PHASES,poses)):
        shape,tips,_=w.features(q);shape=shape/w.lengths[:,None,None];shapes.append(shape)
        penetration,self_penetration,bodies=w.collision();gaps=w.distances(category)
        metrics={'mean_shape_error':float(np.linalg.norm(shape-source_shapes[index],axis=2).mean()),
                 'mean_action_error':float(np.linalg.norm((shape-w.neutral_shape)-(source_shapes[index]-source_neutral),axis=2).mean()),
                 'mean_world_tip_error_m':float(np.linalg.norm(tips-source_tips[index],axis=1).mean()),
                 'max_hand_object_penetration_m':float(penetration.max()),'max_self_penetration_m':self_penetration,
                 'contact_bodies':bodies,'finger_surface_gaps_m':gaps.tolist(),
                 'min_joint_margin_rad':float(np.minimum(q[7:]-w.limits[:,0],w.limits[:,1]-q[7:]).min())}
        phases[phase]=metrics
        if max(metrics['max_hand_object_penetration_m'],self_penetration)>cfg['penetration_tolerance_m']:failures.append(phase+'_penetration')
        if metrics['mean_shape_error']>cfg['max_shape_error']:failures.append(phase+'_shape_deviation')
        if metrics['mean_action_error']>cfg['max_action_error']:failures.append(phase+'_action_deviation')
        if index and np.max(abs(gaps[required]))>.002:failures.append(phase+'_required_contact_missing')
    transitions=[float(np.linalg.norm((shapes[i]-shapes[i-1])-(source_shapes[i]-source_shapes[i-1]),axis=2).mean()) for i in [1,2]]
    if max(transitions)>cfg['max_transition_error']:failures.append('stage_action_deviation')
    return {'phases':phases,'transition_errors':transitions,'failure_reasons':failures,'passed':not failures}


def choose_refinement(baseline_quality,proposed_quality,baseline_thumb,proposed_thumb,cfg):
    if baseline_quality['passed'] and not proposed_quality['passed']:
        return False,'baseline_geometry_preserved'
    old=float(np.mean([m['score'] for m in baseline_thumb]));new=float(np.mean([m['score'] for m in proposed_thumb]))
    if new>old*(1-cfg['minimum_thumb_score_improvement_fraction']):return False,'thumb_improvement_below_threshold'
    for key in ['palm','opposition','directions','pad_chord']:
        before=float(np.mean([m[key] for m in baseline_thumb]));after=float(np.mean([m[key] for m in proposed_thumb]))
        allowed=before*(1+cfg['maximum_component_regression_fraction'])+cfg['maximum_component_regression_absolute']
        if after>allowed:return False,'thumb_component_regression_'+key
    for phase,(before,after) in enumerate(zip(baseline_thumb,proposed_thumb)):
        if after['score']>before['score']*1.05+.02:return False,'thumb_phase_regression_'+PHASES[phase]
    if not proposed_quality['passed']:
        return False,'proposal_geometry_still_rejected'
    return True,'thumb_fidelity_improved_with_geometry_pass'


def refine_case(baseline_folder,config_path,output,render=True):
    baseline_folder,output=Path(baseline_folder),Path(output)
    if output.exists():raise ValueError('V2 output exists; use a fresh directory')
    output.mkdir(parents=True)
    started=monotonic();cfg=yaml.safe_load(Path(config_path).read_text())
    if cfg.get('schema_version')!=2:raise ValueError('Expected V2 thumb refinement configuration')
    if cfg.get('initialization') not in ['v1_optimized','v1_shape_initial']:raise ValueError('Unknown V2 initialization')
    baseline=json.loads((baseline_folder/'result.json').read_text())
    for key in ['target_model','source_hand_model']:
        if sha256(baseline[key]['path'])!=baseline[key]['sha256']:raise ValueError('Baseline hand model changed')
    selection=baseline['source_selection'];source=Path(selection['source']['path'])
    if sha256(source)!=selection['source']['sha256']:raise ValueError('Source changed since V1')
    raw=np.load(source,allow_pickle=True).item();scene=load_scene_cfg(selection['scene_path'])
    obj=scene['scene'][scene['task']['obj_name']]
    obj['scale']=np.asarray(obj['scale'])*selection['scene_scale_multiplier']
    sh=HandGeometry(MuJoCo_VisEnv(HandCfg(baseline['source_hand_model']['path'],freejoint=True),scene,vis_mode='collision'),'shadow')
    w=HandGeometry(MuJoCo_VisEnv(HandCfg(baseline['target_model']['path'],freejoint=True),scene,vis_mode='collision'),'wuji')
    calibration=pad_calibration(sh,w,cfg['source_pad_annotation'])
    with np.load(baseline_folder/'postures.npz',allow_pickle=False) as stored:
        source_poses=stored['source_qpos'].copy();v1=stored['wuji_optimized_qpos'].copy();reseed=stored['wuji_initial_qpos'].copy()
    source_thumb=[];source_shapes=[];source_tips=[]
    for q in source_poses:
        descriptor,shape,tips=thumb_features(sh,q,calibration['source_normal_local'])
        source_thumb.append(descriptor);source_shapes.append(shape);source_tips.append(tips)
    source_shapes=np.asarray(source_shapes);source_tips=np.asarray(source_tips)
    required=np.array([f in baseline['required_fingers'] for f in ['thumb','index','middle','ring','pinky']])
    region_distance,region_point=closest_source_thumb_region(sh,source_poses[1])
    contact_pin=bool(required[0] and region_distance<=.002)
    deadline=started+cfg['timeout_s_per_case']
    anchor=v1.copy()
    start=v1.copy() if cfg['initialization']=='v1_optimized' else reseed.copy()
    shape_weights=np.ones((5,1,1));shape_weights[0]=cfg['thumb_shape_multiplier']
    action_weights=np.ones((5,1,1));action_weights[0]=cfg['thumb_action_multiplier']
    def residual(poses):
        terms=[];shapes=[];thumbs=[]
        for i,q in enumerate(poses):
            th,shape,tips=thumb_features(w,q,calibration['target_normal_local']);thumbs.append(th);shapes.append(shape)
            source_th=source_thumb[i];ho,hh,_=w.collision()
            margin=np.minimum(q[7:11]-w.limits[:4,0],w.limits[:4,1]-q[7:11])
            terms.extend([(cfg['shape_weight']*shape_weights*(shape-source_shapes[i])).ravel(),
                (cfg['action_weight']*action_weights*((shape-w.neutral_shape)-(source_shapes[i]-sh.neutral_shape))).ravel(),
                (cfg['thumb_palm_weight']*(th['palm']-source_th['palm'])).ravel(),
                (cfg['thumb_opposition_weight']*(th['opposition']-source_th['opposition'])).ravel(),
                (cfg['thumb_direction_weight']*(th['directions']-source_th['directions'])).ravel(),
                cfg['thumb_pad_weight']*(th['pad_normal']-source_th['pad_normal']),
                cfg['thumb_margin_weight']*np.maximum(cfg['thumb_margin_rad']-margin,0)/cfg['thumb_margin_rad'],
                ((tips-source_tips[i])/cfg['world_tip_scale_m']).ravel(),
                (q[:3]-anchor[i,:3])/cfg['wrist_translation_scale_m'],
                cfg['wrist_rotation_weight']*(Rotation.from_quat(q[3:7][[1,2,3,0]])*Rotation.from_quat(anchor[i,3:7][[1,2,3,0]]).inv()).as_rotvec(),
                cfg['other_joint_prior_weight']*(q[11:]-anchor[i,11:])/cfg['other_joint_prior_scale_rad'],
                np.maximum(ho-.0005,0)/cfg['collision_scale_m'],np.array([max(hh-.0005,0)/cfg['collision_scale_m']])])
            if i:
                target=cfg['target_grasp_gap_m'] if i==1 else cfg['target_squeeze_gap_m']
                terms.append((w.distances(selection['category'])[required]-target)/cfg['contact_scale_m'])
                if contact_pin:
                    bid=w.tip_bodies['thumb'];point=w.data.xpos[bid]+w.data.xmat[bid].reshape(3,3)@calibration['target_patch_local']
                    terms.append(cfg['contact_patch_weight']*(point-region_point)/cfg['contact_patch_scale_m'])
        for i in [1,2]:
            terms.append((cfg['transition_weight']*((shapes[i]-shapes[i-1])-(source_shapes[i]-source_shapes[i-1]))).ravel())
            for key in ['palm','opposition','pad_normal']:
                terms.append((cfg['thumb_transition_weight']*((thumbs[i][key]-thumbs[i-1][key])-(source_thumb[i][key]-source_thumb[i-1][key]))).ravel())
        return np.concatenate(terms)
    thumb_initial=np.clip(start[:,7:11],w.limits[:4,0]+1e-5,w.limits[:4,1]-1e-5)
    def thumb_residual(value):
        q=start.copy();q[:,7:11]=value.reshape(3,4);return residual(q)
    thumb_angles,thumb_solver=budgeted_solve(thumb_residual,thumb_initial.ravel(),
        (np.tile(w.limits[:4,0]+1e-5,3),np.tile(w.limits[:4,1]-1e-5,3)),cfg['thumb_only_nfev'],deadline)
    initialized=start.copy();initialized[:,7:11]=thumb_angles.reshape(3,4)
    variables=np.array([pose_variables(q) for q in initialized]);reference=np.array([pose_variables(q) for q in anchor])
    lower=np.array([np.r_[x[:3]-cfg['max_wrist_translation_change_m'],x[3:6]-cfg['max_wrist_rotvec_change_rad'],w.limits[:,0]+1e-5] for x in reference])
    upper=np.array([np.r_[x[:3]+cfg['max_wrist_translation_change_m'],x[3:6]+cfg['max_wrist_rotvec_change_rad'],w.limits[:,1]-1e-5] for x in reference])
    variables=np.clip(variables,lower+1e-10,upper-1e-10)
    solved,joint_solver=budgeted_solve(lambda flat:residual(np.array([variables_pose(x) for x in flat.reshape(3,26)])),
        variables.ravel(),(lower.ravel(),upper.ravel()),cfg['joint_nfev'],deadline)
    proposed=np.array([variables_pose(x) for x in solved.reshape(3,26)])
    baseline_quality=geometry_quality(w,v1,source_shapes,source_tips,sh.neutral_shape,required,selection['category'],cfg)
    proposed_quality=geometry_quality(w,proposed,source_shapes,source_tips,sh.neutral_shape,required,selection['category'],cfg)
    def evaluate_thumb(poses):
        return [thumb_metrics(source_thumb[i],thumb_features(w,q,calibration['target_normal_local'])[0]) for i,q in enumerate(poses)]
    old_thumb,new_thumb=evaluate_thumb(v1),evaluate_thumb(proposed)
    selected_new,decision=choose_refinement(baseline_quality,proposed_quality,old_thumb,new_thumb,cfg)
    selected=proposed if selected_new else v1.copy()
    quality=proposed_quality if selected_new else baseline_quality
    np.savez_compressed(output/'postures.npz',source_qpos=source_poses,wuji_v1_qpos=v1,
        wuji_v2_initialized_qpos=initialized,wuji_v2_proposed_qpos=proposed,wuji_selected_qpos=selected,phase=PHASES)
    report={'schema_version':2,'status':'kinematic_candidate' if quality['passed'] else 'kinematic_rejected',
        'selected_version':'v2' if selected_new else 'v1_retained','selection_reason':decision,
        'source_selection':selection,'bench_targets':baseline['bench_targets'],'joint_names':w.names,
        'baseline_result':file_receipt(baseline_folder/'result.json'),'baseline_postures':file_receipt(baseline_folder/'postures.npz'),
        'config':file_receipt(Path(config_path)),'implementation':file_receipt(Path(__file__)),
        'calibration':{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in calibration.items()},
        'source_thumb_contact_region':{'enabled':contact_pin,'source_gap_m':region_distance,'point_world_m':region_point.tolist()},
        'baseline_quality':baseline_quality,'proposed_quality':proposed_quality,'selected_quality':quality,
        'baseline_thumb':dict(zip(PHASES,old_thumb)),'proposed_thumb':dict(zip(PHASES,new_thumb)),
        'selected_thumb':dict(zip(PHASES,new_thumb if selected_new else old_thumb)),
        'thumb_solver':thumb_solver,'joint_solver':joint_solver,'seconds':monotonic()-started,
        'physical_passed':None,'full_task_passed':None,
        'limitations':['Static poses only','Thumb pad references are geometry-derived proxies',
            'Original Wuji joint limits unchanged','V1 retained when geometry/fidelity checks reject V2']}
    atomic_json(output/'result.json',report)
    if render:
        # Existing renderer layout becomes Source / V1 / selected V2, and a
        # separate proposal view prevents rolled-back results being hidden.
        render_comparison(sh,w,source_poses,v1,selected,output)
        render_hand_only(sh,w,source_poses,v1,selected,output/'hand_only')
        label_comparison(output/'comparison.png','Wuji V2 selected' if selected_new else 'Wuji V1 retained')
        label_comparison(output/'hand_only/comparison.png','Wuji V2 selected' if selected_new else 'Wuji V1 retained')
        if not selected_new:
            (output/'proposal').mkdir()
            render_comparison(sh,w,source_poses,v1,proposed,output/'proposal')
            label_comparison(output/'proposal/comparison.png','Wuji V2 proposed - gate rejected')
    return report


def label_comparison(path,last_row):
    from PIL import Image,ImageDraw
    image=Image.open(path).convert('RGB');draw=ImageDraw.Draw(image)
    for row,label in enumerate(['Shadow source','Wuji V1 optimized baseline',last_row]):
        for column,phase in enumerate(PHASES):
            x,y=column*640,row*480
            draw.rectangle((x,y,x+639,y+45),fill=(15,20,28))
            draw.text((x+10,y+10),label+' | '+phase,fill='white')
            draw.text((x+10,y+28),'STATIC THUMB REFINEMENT - physical execution not tested',fill='white')
    image.save(path)
