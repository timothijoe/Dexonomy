"""Multi-region repair of source contact patches, with explicit protection gates."""
import json
from pathlib import Path
from time import monotonic

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh
import yaml

from dexonomy.sim import HandCfg,MuJoCo_VisEnv
from .common import atomic_json,file_receipt,sha256
from .gravity_hold_probe import context
from .shadow_retarget import HandGeometry,pose_variables,variables_pose,budgeted_solve,PHASES,FINGERS
from .shadow_thumb_v2 import thumb_features,geometry_quality
from .shadow_thumb_v3 import BendDomain,natural_quality,bone_directions
from .contact_region_audit import point_to_hand,corresponding_geoms,native_nearest,feature_segments,segment_distance,CONFIG


def edge_shift(row,cfg=CONFIG):
    """Only reliable source-interior to target-edge displacement, not every rim touch."""
    source,target=row['source'],row['target'];se=source['edge_distance_m'];te=target['edge_distance_m']
    return bool(row['source_near_reference'] and se is not None and te is not None
        and se>cfg['edge_band_m'] and te<=cfg['edge_band_m']
        and abs(target['full']['gap_m'])<=cfg['near_m']
        and target['raw_object_surface_gap_m']<=cfg['near_m']
        and target['anchor']['distance_m']>cfg['anchor_drift_m'])


def region_geoms(hand,finger):
    prefix='hand-right_palm_link' if finger=='palm' else f'hand-right_finger{FINGERS.index(finger)+1}_'
    return [g for g in hand.hand_geom_list if hand.model.body(int(hand.model.geom_bodyid[g])).name.startswith(prefix)]


def protection_passed(before,after,near=.002,regression=.001):
    return all(after[k]<=max(near,before[k]+regression)+1e-10 for k in before)


def refine(folder,audit_path,focus_fingers,output,max_nfev=80,seconds=240):
    folder,output=Path(folder),Path(output)
    if output.exists():raise ValueError('Use a fresh multi-region proposal output')
    if not focus_fingers or len(set(focus_fingers))!=len(focus_fingers) or not set(focus_fingers)<=set([*FINGERS,'palm']):
        raise ValueError('Choose distinct valid focus regions')
    started=monotonic();baseline,original,scene=context(folder)
    audit=json.loads(Path(audit_path).read_text());cfg=yaml.safe_load(Path(baseline['config']['path']).read_text())
    if audit['case_id']!=baseline['source_selection']['id']:raise ValueError('Audit case mismatch')
    for receipt in audit['inputs']:
        if sha256(receipt['path'])!=receipt['sha256']:raise ValueError('Audit input changed')
    w=HandGeometry(MuJoCo_VisEnv(HandCfg(original['target_model']['path'],freejoint=True),scene,vis_mode='collision'),'wuji')
    sh=HandGeometry(MuJoCo_VisEnv(HandCfg(original['source_hand_model']['path'],freejoint=True),scene,vis_mode='collision'),'shadow')
    obj=scene['scene'][scene['task']['obj_name']];raw_mesh=trimesh.load(obj['file_path'],force='mesh',process=True)
    raw_mesh.vertices*=obj['scale'];rotation=Rotation.from_quat(np.asarray(obj['pose'])[3:][[1,2,3,0]]).as_matrix()
    raw_mesh.vertices=raw_mesh.vertices@rotation.T+obj['pose'][:3]
    edges=feature_segments(raw_mesh,CONFIG['sharp_angle_deg'],CONFIG['minimum_edge_length_m'])
    with np.load(folder/'postures.npz',allow_pickle=False) as z:source=z['source_qpos'].copy();old=z['wuji_selected_qpos'].copy()
    source_thumb=[];source_shape=[];source_tips=[];source_bones=[]
    for q in source:
        th,shape,tips=thumb_features(sh,q,np.asarray(baseline['calibration']['source_normal_local']))
        source_thumb.append(th);source_shape.append(shape);source_tips.append(tips);source_bones.append(bone_directions(sh,q))
    source_shape=np.asarray(source_shape);source_tips=np.asarray(source_tips)
    required=np.array([f in original['required_fingers'] for f in FINGERS]);calibration=baseline['bend_calibration']['target']
    domain=BendDomain(w.limits[2:4],calibration,np.deg2rad(baseline['bend_calibration']['combined_cap_deg']))
    pad=np.asarray(baseline['calibration']['target_normal_local']);repaired=old.copy();details=[];protect_before={};protect_after={}
    for pi,phase in [(1,'grasp'),(2,'squeeze')]:
        references=[r for r in audit['rows'] if r['version']=='selected' and r['phase']==phase and r['source_near_reference']]
        focuses=[r for r in references if r['finger'] in focus_fingers]
        if not focuses:raise ValueError('No reliable focus reference in '+phase)
        protected=[r for r in references if r['finger'] not in focus_fingers and r['required'] and r['target']['anchor']['distance_m']<=.002]
        terms=[(r,1.) for r in focuses]+[(r,.6) for r in protected]
        mapped=[(r,weight,corresponding_geoms(w,r['finger'],r['source']['hand_body'])) for r,weight in terms]
        anchor=old[pi];w.set_pose(anchor);baseline_shape=w.features(anchor)[0]/w.lengths[:,None,None];baseline_thumb=thumb_features(w,anchor,pad)[0]
        start=pose_variables(anchor);start[8:10]=domain.encode(anchor[9:11])
        lower=np.r_[start[:3]-.02,start[3:6]-.2,w.limits[:,0]+1e-5];upper=np.r_[start[:3]+.02,start[3:6]+.2,w.limits[:,1]-1e-5]
        lower[8:10],upper[8:10]=0,1;start=np.clip(start,lower+1e-10,upper-1e-10)
        def decode(value):
            value=value.copy();value[8:10]=domain.decode(value[8:10]);return variables_pose(value)
        def residual(value):
            q=decode(value);th,shape,tips=thumb_features(w,q,pad);patch=[]
            for r,weight,geoms in mapped:
                point=np.asarray(r['source']['object_point_world_m']);near=point_to_hand(w,point,geoms)
                patch.extend(weight*(np.asarray(near['hand_point_world_m'])-point)/.0015)
            ho,hh,_=w.collision();gaps=w.distances(baseline['source_selection']['category'])
            return np.r_[patch,(gaps[required]-.0002)/.0015,
                np.maximum(ho-.0005,0)/.0005,max(hh-.0005,0)/.0005,
                (2.*(shape-baseline_shape)).ravel(),(shape-source_shape[pi]).ravel(),
                (2.*(th['directions']-baseline_thumb['directions'])).ravel(),2.*(th['pad_normal']-baseline_thumb['pad_normal']),
                (q[:3]-anchor[:3])/.02,.2*(Rotation.from_quat(q[3:7][[1,2,3,0]])*Rotation.from_quat(anchor[3:7][[1,2,3,0]]).inv()).as_rotvec(),
                .3*(q[7:]-anchor[7:])/.12]
        fit,solver=budgeted_solve(residual,start,(lower,upper),max_nfev,started+seconds)
        repaired[pi]=decode(fit);w.set_pose(repaired[pi])
        for r in references:
            finger=r['finger'];key=phase+':'+finger
            near=point_to_hand(w,np.asarray(r['source']['object_point_world_m']),corresponding_geoms(w,finger,r['source']['hand_body']))
            full=native_nearest(w,region_geoms(w,finger));point=np.asarray(full['object_point_world_m'])
            closest,raw_gap,_=trimesh.proximity.closest_point(raw_mesh,point[None]);edge=segment_distance(closest[0],edges)
            if r in protected:protect_before[key]=r['target']['anchor']['distance_m'];protect_after[key]=near['distance_m']
            details.append({'phase':phase,'finger':finger,'focus':finger in focus_fingers,'protected':r in protected,
                'reference_gap_before_m':r['target']['anchor']['distance_m'],'reference_gap_after_m':near['distance_m'],
                'source_edge_distance_m':r['source']['edge_distance_m'],'target_edge_before_m':r['target']['edge_distance_m'],
                'target_edge_after_m':edge,'target_gap_after_m':full['gap_m'],'target_raw_surface_gap_after_m':float(raw_gap[0]),
                'solver':solver if finger in focus_fingers else None})
    geometry=geometry_quality(w,repaired,source_shape,source_tips,sh.neutral_shape,required,baseline['source_selection']['category'],cfg)
    natural=natural_quality(w,repaired,source_bones,source_thumb,calibration,domain,{**cfg,'_pad_normal':pad})
    focus_details=[d for d in details if d['focus']];restored=bool(focus_details) and all(d['reference_gap_after_m']<=.002 for d in focus_details)
    protected_ok=protection_passed(protect_before,protect_after);passed=geometry['passed'] and natural['passed'] and restored and protected_ok
    output.mkdir(parents=True);np.savez_compressed(output/'postures.npz',source_qpos=source,baseline_qpos=old,proposed_qpos=repaired,phase=PHASES)
    report={'case_id':audit['case_id'],'focus_fingers':focus_fingers,'static_proposal_passed':passed,'patch_restored':restored,
        'protected_patches_passed':protected_ok,'protected_before_m':protect_before,'protected_after_m':protect_after,
        'geometry':geometry,'natural':natural,'details':details,'baseline_status':baseline['status'],
        'baseline_input':file_receipt(folder/'postures.npz'),'audit_input':file_receipt(Path(audit_path)),
        'implementation':file_receipt(Path(__file__)),'seconds':monotonic()-started,'physical_passed':None,
        'adoption':'proposal_only' if passed else 'baseline_retained_proposal_rejected',
        'limitations':['Source patches reconstructed from geometry, not saved contact forces',
            'Sharp edge proxy and closest whole-finger point do not measure total support area',
            'Protects reliable already-near required patches, not every original contact',
            'No original V3 or physical success label overwritten']}
    atomic_json(output/'result.json',report);return report
