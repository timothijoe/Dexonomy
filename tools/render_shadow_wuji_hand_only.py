#!/usr/bin/env python3
"""Render existing posture results in a shared palm frame, without the object."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MUJOCO_GL','egl')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.spatial.transform import Rotation

from dexonomy.sim import HandCfg,MuJoCo_VisEnv
from dexonomy.util.file_util import load_scene_cfg
from dexonomy.integrations.bench2dex.common import atomic_json,file_receipt,sha256
from dexonomy.integrations.bench2dex.shadow_retarget import HandGeometry,render_comparison


def render(folder,output):
    if output.exists():raise ValueError('Render output exists; use a new directory')
    r=json.loads((folder/'result.json').read_text())
    selection=r['source_selection']
    if sha256(selection['source']['path'])!=selection['source']['sha256']:raise ValueError('Source changed')
    if sha256(r['target_model']['path'])!=r['target_model']['sha256']:raise ValueError('Target model changed')
    raw=np.load(selection['source']['path'],allow_pickle=True).item()
    scene=load_scene_cfg(str(raw['scene_path']))
    name=scene['task']['obj_name']
    scene['scene'][name]['scale']=np.asarray(scene['scene'][name]['scale'])*float(np.asarray(raw['scene_scale'])[selection['source_index']])
    sh=HandGeometry(MuJoCo_VisEnv(HandCfg(r['source_hand_model']['path'],freejoint=True),scene,vis_mode='collision'),'shadow')
    w=HandGeometry(MuJoCo_VisEnv(HandCfg(r['target_model']['path'],freejoint=True),scene,vis_mode='collision'),'wuji')
    with np.load(folder/'postures.npz',allow_pickle=False) as data:
        source,initial,optimized=(data[k].copy() for k in ['source_qpos','wuji_initial_qpos','wuji_optimized_qpos'])
    def palm_aligned(hand,poses):
        result=[]
        for q in poses:
            hand.set_pose(q)
            frame,palm=hand.frame(),hand.data.xpos[hand.palm].copy()
            oldrot=Rotation.from_quat(q[3:7][[1,2,3,0]]).as_matrix()
            pose=q.copy()
            pose[:3]=frame.T@(q[:3]-palm)
            pose[3:7]=Rotation.from_matrix(frame.T@oldrot).as_quat()[[3,0,1,2]]
            result.append(pose)
        return np.asarray(result)
    source,initial,optimized=palm_aligned(sh,source),palm_aligned(w,initial),palm_aligned(w,optimized)
    for hand in [sh,w]:
        hand.object_geoms=set()
        hand.env._body_mesh_dict={name:mesh for name,mesh in hand.env._body_mesh_dict.items() if name.startswith('hand-')}
    output.mkdir(parents=True)
    render_comparison(sh,w,source,initial,optimized,output)
    atomic_json(output/'view.json',{'source_result':file_receipt(folder/'result.json'),
                                  'image':file_receipt(output/'comparison.png'),
                                  'frame':'each posture rigidly aligned to its anatomical palm frame',
                                  'scale':'original hand dimensions unchanged',
                                  'note':'Object hidden for hand-shape comparison; does not show physical execution'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    render(args.result,args.output)
