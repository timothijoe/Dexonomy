#!/usr/bin/env python3
"""Verify a terminal V2 batch and quantify paired thumb changes without success claims."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mujoco
import numpy as np
from PIL import Image

from dexonomy.integrations.bench2dex.common import atomic_json
from dexonomy.integrations.bench2dex.shadow_batch import verify_completed
from dexonomy.integrations.bench2dex.thumb_v2_batch import verify_v2,identity


def audit(root):
    root=Path(root);plan=json.loads((root/'plan.json').read_text());verify_v2(plan)
    summary=json.loads((root/'summary.json').read_text())
    if not summary['all_cases_terminal']:raise ValueError('V2 batch is not terminal')
    base=json.loads(Path(plan['baseline_plan']['path']).read_text())
    model=mujoco.MjModel.from_xml_path(base['inputs']['target_model']['path'])
    old_scores=[];new_scores=[];old_pad=[];new_pad=[];old_limit=[];new_limit=[];rows=[];png_count=0
    joint_limits=None
    for job in plan['jobs']:
        folder=root/'samples'/job['case_id'];terminal=verify_completed(folder,identity(plan,job))
        if terminal['status']=='error':raise ValueError('Case has an execution error: '+job['case_id'])
        r=json.loads((folder/'result.json').read_text())
        if joint_limits is None:joint_limits=np.array([model.joint(n.removeprefix('hand-')).range for n in r['joint_names']])
        with np.load(folder/'postures.npz',allow_pickle=False) as z:
            for name in ['wuji_v1_qpos','wuji_v2_initialized_qpos','wuji_v2_proposed_qpos','wuji_selected_qpos']:
                q=z[name];assert q.shape==(3,27) and np.isfinite(q).all()
                np.testing.assert_allclose(np.linalg.norm(q[:,3:7],axis=1),1,atol=1e-10)
                assert np.all(q[:,7:]>=joint_limits[:,0]-1e-9) and np.all(q[:,7:]<=joint_limits[:,1]+1e-9)
            old=z['wuji_v1_qpos'];new=z['wuji_selected_qpos']
            if r['selected_version']=='v1_retained':np.testing.assert_array_equal(old,new)
            old_limit.append(np.minimum(old[:,7:11]-joint_limits[:4,0],joint_limits[:4,1]-old[:,7:11]).min(axis=1)<.001)
            new_limit.append(np.minimum(new[:,7:11]-joint_limits[:4,0],joint_limits[:4,1]-new[:,7:11]).min(axis=1)<.001)
        before=np.mean([m['score'] for m in r['baseline_thumb'].values()]);after=np.mean([m['score'] for m in r['selected_thumb'].values()])
        assert r['physical_passed'] is None and r['full_task_passed'] is None
        assert not r['baseline_quality']['passed'] or r['selected_quality']['passed']
        if r['selected_version']=='v2':assert after<before and r['selected_quality']['passed']
        old_scores.append(before);new_scores.append(after)
        old_pad.append([r['baseline_thumb'][p]['pad_angle_deg'] for p in ['pregrasp','grasp','squeeze']])
        new_pad.append([r['selected_thumb'][p]['pad_angle_deg'] for p in ['pregrasp','grasp','squeeze']])
        for path in folder.rglob('*.png'):
            with Image.open(path) as image:image.verify()
            png_count+=1
        assert (folder/'comparison.png').exists() and (folder/'hand_only/comparison.png').exists()
        rows.append({'case_id':job['case_id'],'selected_version':r['selected_version'],'status':r['status'],
                     'baseline_passed':r['baseline_quality']['passed'],'selected_passed':r['selected_quality']['passed'],
                     'score_before':float(before),'score_after':float(after),'relative_improvement':float((before-after)/before),
                     'attempt_count':len(r['refinement_attempts'])})
    by_case={r['case_id']:r for r in rows}
    coverage=Counter(by_case[e['case_id']]['status'] for a in plan['assets'] for e in a['entries'])
    versions=Counter(by_case[e['case_id']]['selected_version'] for a in plan['assets'] for e in a['entries'])
    adopted=[r for r in rows if r['selected_version']=='v2']
    old_scores=np.asarray(old_scores);new_scores=np.asarray(new_scores)
    result={'schema_version':2,'source_cases_verified':len(rows),'coverage_entries':plan['coverage_entries'],
        'adoption_counts':dict(Counter(r['selected_version'] for r in rows)),
        'coverage_selection_counts':dict(versions),'coverage_status_counts':dict(coverage),
        'mean_thumb_score_before':float(old_scores.mean()),'mean_thumb_score_selected':float(new_scores.mean()),
        'mean_score_reduction_fraction':float(1-new_scores.mean()/old_scores.mean()),
        'mean_relative_reduction_adopted':float(np.mean([r['relative_improvement'] for r in adopted])) if adopted else 0.,
        'mean_pad_angle_before_deg':np.mean(old_pad,axis=0).tolist(),'mean_pad_angle_selected_deg':np.mean(new_pad,axis=0).tolist(),
        'thumb_near_limit_cases_before':np.asarray(old_limit).sum(axis=0).tolist(),
        'thumb_near_limit_cases_selected':np.asarray(new_limit).sum(axis=0).tolist(),
        'geometry_regressions':sum(r['baseline_passed'] and not r['selected_passed'] for r in rows),
        'static_recoveries':sum(not r['baseline_passed'] and r['selected_passed'] for r in rows),
        'fallback_attempts':sum(r['attempt_count']>1 for r in rows),'png_files_verified':png_count,
        'source_plan_and_all_output_checksums_verified':True,'finite_quaternions_and_joint_limits':True,
        'physical_passed':None,'limitations':['Geometry-proxy thumb metrics do not establish human-rated naturalness or physical success'],
        'cases':rows}
    atomic_json(root/'paired_check.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,default=Path('output/shadow_wuji_v2/all_matched_thumb_v2'))
    args=parser.parse_args();r=audit(args.batch)
    print(json.dumps({k:v for k,v in r.items() if k!='cases'},ensure_ascii=False,indent=2))
