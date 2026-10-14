#!/usr/bin/env python3
"""Show source surface anchors and baseline/repaired contact geometry."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL','egl')
for n in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[n]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mujoco
import numpy as np
from PIL import Image,ImageDraw
from dexonomy.sim import HandCfg,MuJoCo_VisEnv
from dexonomy.integrations.bench2dex.shadow_retarget import HandGeometry
from dexonomy.integrations.bench2dex.gravity_hold_probe import context
from dexonomy.integrations.bench2dex.contact_region_audit import corresponding_geoms,point_to_hand

CASES=['case_0091__24_Tip_Pinch','case_0038__10_Power_Disk','case_0041__1_Large_Diameter']


def render(cid):
    original_folder=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/samples')/cid
    folder=Path('output/shadow_wuji_v3/contact_repair_pilot')/cid
    report=json.loads((folder/'result.json').read_text());finger=report['finger']
    audit=json.loads((Path('output/shadow_wuji_v3/contact_region_audit_2026-10-14/cases')/(cid+'.json')).read_text())
    _,source_models,scene=context(original_folder)
    hands=[HandGeometry(MuJoCo_VisEnv(HandCfg(source_models[k]['path'],freejoint=True),scene,vis_mode='collision'),kind)
           for k,kind in [('source_hand_model','shadow'),('target_model','wuji'),('target_model','wuji')]]
    with np.load(folder/'postures.npz') as z:poses=[z[k].copy() for k in ['source_qpos','baseline_qpos','proposed_qpos']]
    bounds=[]
    for h,sequence in zip(hands,poses):
        for q in sequence[1:]:
            h.set_pose(q)
            for name in h.env.get_all_body_names():
                b=h.env.get_body_id(name);m=h.env.get_body_mesh(name)
                p=m.vertices@h.data.xmat[b].reshape(3,3).T+h.data.xpos[b];bounds.extend([p.min(axis=0),p.max(axis=0)])
    lo,hi=np.min(bounds,axis=0),np.max(bounds,axis=0)
    for h,color in zip(hands,[[.8,.3,.15,1],[.2,.45,.75,1],[.12,.65,.72,1]]):
        h.model.vis.global_.offwidth=640;h.model.vis.global_.offheight=480
        for g in range(h.model.ngeom):
            h.model.geom_group[g]=0 if g in h.hand_geoms or g in h.object_geoms else 1
            if g in h.hand_geoms:h.model.geom_rgba[g]=color
            elif g in h.object_geoms:h.model.geom_rgba[g]=[.8,.7,.2,1]
    option=mujoco.MjvOption();option.geomgroup[1]=0
    with ExitStack() as stack:
        renderers=[stack.enter_context(mujoco.Renderer(h.model,height=480,width=640)) for h in hands]
        for zoom in [False,True]:
            for yaw in [135,45,225]:
                canvas=Image.new('RGB',(1920,960))
                for row,(pi,phase) in enumerate([(1,'grasp'),(2,'squeeze')]):
                    ref=next(x for x in audit['rows'] if x['version']=='selected' and x['finger']==finger and x['phase']==phase)
                    point=np.asarray(ref['source']['object_point_world_m'])
                    camera=mujoco.MjvCamera();camera.azimuth=yaw;camera.elevation=-25
                    camera.lookat[:]=point if zoom else (lo+hi)/2
                    camera.distance=.12 if zoom else max(.3,float((hi-lo).max())*2.1)
                    for col,(hand,renderer,sequence) in enumerate(zip(hands,renderers,poses)):
                        hand.set_pose(sequence[pi]);renderer.update_scene(hand.data,camera=camera,scene_option=option)
                        nearest=None
                        if col:
                            nearest=point_to_hand(hand,point,corresponding_geoms(hand,finger,ref['source']['hand_body']))
                        for position,color in [(point,[.15,1,.3,1])]+([(np.asarray(nearest['hand_point_world_m']),[1,.2,.2,1])] if nearest else []):
                            geom=renderer.scene.geoms[renderer.scene.ngeom]
                            mujoco.mjv_initGeom(geom,mujoco.mjtGeom.mjGEOM_SPHERE,np.array([.0015]*3),position,np.eye(3).ravel(),np.asarray(color,dtype=np.float32))
                            renderer.scene.ngeom+=1
                        im=Image.fromarray(renderer.render());draw=ImageDraw.Draw(im)
                        draw.rectangle((0,0,639,48),fill=(15,20,28))
                        label=['Shadow source','V3 baseline','Contact repair proposal'][col]
                        value=ref['source']['gap_m'] if col==0 else nearest['distance_m']
                        draw.text((10,9),f'{label} | {phase} | {finger}',fill='white')
                        draw.text((10,28),f'{"source object gap" if col==0 else "source patch gap"}: {value*1000:.2f} mm',fill='white')
                        canvas.paste(im,(col*640,row*480))
                canvas.save(folder/f'{"closeup" if zoom else "contact"}_yaw{yaw}.png')


if __name__=='__main__':
    for cid in CASES:render(cid);print(cid,flush=True)
