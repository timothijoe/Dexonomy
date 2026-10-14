"""Small source-patch repair proposals, preserving the frozen V3 baseline."""
import json
from pathlib import Path
from time import monotonic

import numpy as np
from scipy.spatial.transform import Rotation
import yaml

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from .common import atomic_json, file_receipt
from .gravity_hold_probe import context
from .shadow_retarget import HandGeometry, pose_variables, variables_pose, budgeted_solve, PHASES, FINGERS
from .shadow_thumb_v2 import thumb_features, geometry_quality
from .shadow_thumb_v3 import BendDomain, natural_quality, bone_directions
from .contact_region_audit import point_to_hand, corresponding_geoms


def refine(folder, audit_path, finger, output, max_nfev=60):
    folder, output = Path(folder), Path(output)
    if output.exists(): raise ValueError('Proposal output exists')
    output.mkdir(parents=True); started=monotonic()
    baseline, original, scene=context(folder)
    audit=json.loads(Path(audit_path).read_text())
    cfg=yaml.safe_load(Path(baseline['config']['path']).read_text())
    w=HandGeometry(MuJoCo_VisEnv(HandCfg(original['target_model']['path'],freejoint=True),scene,vis_mode='collision'),'wuji')
    sh=HandGeometry(MuJoCo_VisEnv(HandCfg(original['source_hand_model']['path'],freejoint=True),scene,vis_mode='collision'),'shadow')
    with np.load(folder/'postures.npz',allow_pickle=False) as z:
        source=z['source_qpos'].copy();old=z['wuji_selected_qpos'].copy()
    source_thumb=[];source_shape=[];source_tips=[];source_bones=[]
    for q in source:
        th,shape,tips=thumb_features(sh,q,np.asarray(baseline['calibration']['source_normal_local']))
        source_thumb.append(th);source_shape.append(shape);source_tips.append(tips);source_bones.append(bone_directions(sh,q))
    source_shape=np.asarray(source_shape);source_tips=np.asarray(source_tips)
    required=np.array([f in original['required_fingers'] for f in FINGERS])
    calibration=baseline['bend_calibration']['target']
    domain=BendDomain(w.limits[2:4],calibration,np.deg2rad(baseline['bend_calibration']['combined_cap_deg']))
    pad=np.asarray(baseline['calibration']['target_normal_local'])
    repaired=old.copy();details=[]
    for pi,phase in [(1,'grasp'),(2,'squeeze')]:
        row=next(x for x in audit['rows'] if x['version']=='selected' and x['phase']==phase and x['finger']==finger)
        if not row['source_near_reference']:
            details.append({'phase':phase,'skipped':'source_reference_not_reliable'});continue
        point=np.asarray(row['source']['object_point_world_m'])
        geoms=corresponding_geoms(w,finger,row['source']['hand_body'])
        anchor=old[pi];w.set_pose(anchor)
        baseline_shape=w.features(anchor)[0]/w.lengths[:,None,None]
        baseline_thumb=thumb_features(w,anchor,pad)[0]
        start=pose_variables(anchor);start[8:10]=domain.encode(anchor[9:11])
        lower=np.r_[start[:3]-.02,start[3:6]-.2,w.limits[:,0]+1e-5]
        upper=np.r_[start[:3]+.02,start[3:6]+.2,w.limits[:,1]-1e-5]
        lower[8:10],upper[8:10]=0,1
        start=np.clip(start,lower+1e-10,upper-1e-10)
        def decode(value):
            value=value.copy();value[8:10]=domain.decode(value[8:10]);return variables_pose(value)
        def residual(value):
            q=decode(value);th,shape,tips=thumb_features(w,q,pad)
            nearest=point_to_hand(w,point,geoms);ho,hh,_=w.collision()
            gaps=w.distances(baseline['source_selection']['category'])
            return np.r_[(np.asarray(nearest['hand_point_world_m'])-point)/.0015,
                (gaps[required]-.0002)/.0015,
                np.maximum(ho-.0005,0)/.0005,max(hh-.0005,0)/.0005,
                (2.*(shape-baseline_shape)).ravel(),
                (1.*(shape-source_shape[pi])).ravel(),
                (2.*(th['directions']-baseline_thumb['directions'])).ravel(),
                2.*(th['pad_normal']-baseline_thumb['pad_normal']),
                (q[:3]-anchor[:3])/.02,
                .2*(Rotation.from_quat(q[3:7][[1,2,3,0]])*Rotation.from_quat(anchor[3:7][[1,2,3,0]]).inv()).as_rotvec(),
                .3*(q[7:]-anchor[7:])/.12]
        fit,solver=budgeted_solve(residual,start,(lower,upper),max_nfev,started+180)
        repaired[pi]=decode(fit);w.set_pose(repaired[pi]);nearest=point_to_hand(w,point,geoms)
        details.append({'phase':phase,'source_reference_point_m':point.tolist(),
                        'reference_gap_before_m':row['target']['anchor']['distance_m'],
                        'reference_gap_after_m':nearest['distance_m'],'target_body':nearest['hand_body'],'solver':solver})
    geometry=geometry_quality(w,repaired,source_shape,source_tips,sh.neutral_shape,required,baseline['source_selection']['category'],cfg)
    natural=natural_quality(w,repaired,source_bones,source_thumb,calibration,domain,{**cfg,'_pad_normal':pad})
    restored=all(d.get('reference_gap_after_m',float('inf'))<=.002 for d in details)
    passed=geometry['passed'] and natural['passed'] and restored
    np.savez_compressed(output/'postures.npz',source_qpos=source,baseline_qpos=old,proposed_qpos=repaired,phase=PHASES)
    report={'case_id':audit['case_id'],'finger':finger,'static_proposal_passed':passed,
            'patch_restored':restored,'geometry':geometry,'natural':natural,'details':details,
            'baseline_status':baseline['status'],'baseline_input':file_receipt(folder/'postures.npz'),
            'audit_input':file_receipt(Path(audit_path)),'implementation':file_receipt(Path(__file__)),
            'seconds':monotonic()-started,'physical_passed':None,
            'limitations':['Proposal only; original V3 not modified','Single focus region repair does not validate all contacts']}
    atomic_json(output/'result.json',report)
    return report
