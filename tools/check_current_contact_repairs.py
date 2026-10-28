#!/usr/bin/env python3
"""Check exact inputs, actual FK/limits and all adopted repair quality gates."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import sys
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import yaml
from dexonomy.sim import HandCfg,MuJoCo_VisEnv
from dexonomy.integrations.bench2dex.common import atomic_json
from dexonomy.integrations.bench2dex.gravity_hold_probe import context
from dexonomy.integrations.bench2dex.shadow_retarget import HandGeometry,FINGERS,PHASES
from dexonomy.integrations.bench2dex.shadow_thumb_v2 import thumb_features,geometry_quality
from dexonomy.integrations.bench2dex.shadow_thumb_v3 import BendDomain,natural_quality,bone_directions
from dexonomy.integrations.bench2dex.current_contact_repair import audit_gate,validate_audit_binding
from tools.audit_shadow_thumb_angles import signed_turns
from tools.repair_current_shadow_contacts import verify,DEFAULT


def inspect(args):
    job,row=args;verify(job['inputs']);verify(row['artifacts'])
    folder=Path(row['proposal_folder']);r,original,scene=context(folder)
    verify([r['config'],original['target_model'],original['source_hand_model'],r['source_selection']['source']])
    before=json.loads(Path(job['audit']).read_text());validate_audit_binding(job['baseline_folder'],before)
    after=json.loads(Path(row['artifacts'][-1]['path']).read_text());validate_audit_binding(folder,after)
    gate=audit_gate(before,after)
    assert json.loads(json.dumps(gate))==row['audit_gate'],job['case_id']
    report=json.loads(Path(row['artifacts'][0]['path']).read_text())
    with np.load(folder/'postures.npz',allow_pickle=False) as z,np.load(Path(job['baseline_folder'])/'postures.npz',allow_pickle=False) as old:
        source=z['source_qpos'].copy();q=z['wuji_selected_qpos'].copy()
        np.testing.assert_array_equal(source,old['source_qpos'])
        np.testing.assert_array_equal(z['wuji_v2_qpos'],old['wuji_selected_qpos'])
        np.testing.assert_array_equal(q[0],old['wuji_selected_qpos'][0])
        for i,p in [(1,'grasp'),(2,'squeeze')]:
            if not job['focus_by_phase'][p]:np.testing.assert_array_equal(q[i],old['wuji_selected_qpos'][i])
    assert q.shape==(3,27) and np.isfinite(q).all()
    np.testing.assert_allclose(np.linalg.norm(q[:,3:7],axis=1),1,atol=1e-10)
    hand=HandGeometry(MuJoCo_VisEnv(HandCfg(original['target_model']['path'],freejoint=True),scene,vis_mode='collision'),'wuji')
    assert np.all(q[:,7:]>=hand.limits[:,0]-1e-9) and np.all(q[:,7:]<=hand.limits[:,1]+1e-9)
    bends=np.array([signed_turns(hand,pose) for pose in q])*r['bend_calibration']['target']['flexion_sign']
    assert bends.min()>=-1e-5 and bends.sum(axis=1).max()<=r['bend_calibration']['combined_cap_deg']+1e-5
    np.testing.assert_allclose(bends,np.array([r['selected_natural']['phases'][p]['bend_deg'] for p in PHASES]),atol=1e-5)
    restored=all(d['reference_gap_after_m']<=.002 for d in report['details'] if d['focus'])
    assert restored==report['patch_restored']
    adopted=bool(report['static_proposal_passed'] and gate['passed']);assert adopted==row['adopted']
    assert row['selected_folder']==(str(folder.resolve()) if adopted else job['baseline_folder'])
    gaps=[]
    if adopted:
        sh=HandGeometry(MuJoCo_VisEnv(HandCfg(original['source_hand_model']['path'],freejoint=True),scene,vis_mode='collision'),'shadow')
        features=[thumb_features(sh,p,np.array(r['calibration']['source_normal_local'])) for p in source]
        bones=[bone_directions(sh,p) for p in source];cal=r['bend_calibration']['target']
        domain=BendDomain(hand.limits[2:4],cal,np.deg2rad(r['bend_calibration']['combined_cap_deg']))
        cfg=yaml.safe_load(Path(r['config']['path']).read_text());pad=np.array(r['calibration']['target_normal_local'])
        g=geometry_quality(hand,q,np.array([f[1] for f in features]),np.array([f[2] for f in features]),sh.neutral_shape,
            np.array([f in original['required_fingers'] for f in FINGERS]),r['source_selection']['category'],cfg)
        n=natural_quality(hand,q,bones,[f[0] for f in features],cal,domain,{**cfg,'_pad_normal':pad})
        assert g['passed'] and n['passed']
        np.testing.assert_allclose(g['transition_errors'],r['selected_quality']['transition_errors'],atol=1e-10)
        for phase in PHASES:
            for key in ['mean_shape_error','mean_action_error','max_hand_object_penetration_m','max_self_penetration_m']:
                np.testing.assert_allclose(g['phases'][phase][key],r['selected_quality']['phases'][phase][key],atol=1e-10)
        index={(z['phase'],z['finger']):z for z in after['rows'] if z['version']=='selected'}
        for p,fingers in job['focus_by_phase'].items():
            for finger in fingers:
                gap=index[p,finger]['target']['anchor']['distance_m'];assert gap<=.002+1e-10;gaps.append(gap)
        for key,b in report['protected_before_m'].items():
            p,finger=key.split(':');assert index[p,finger]['target']['anchor']['distance_m']<=max(.002,b+.001)+1e-10
    assert r['physical_passed'] is None and r['full_task_passed'] is None
    return {'case_id':job['case_id'],'adopted':adopted,'focus_gaps_m':gaps,
        'max_combined_bend_deg':float(bends.sum(axis=1).max()),'max_oriented_angle_deg':float((180-bends).max())}


def check(root,workers=8):
    root=Path(root);plan=json.loads((root/'plan.json').read_text());verify(plan['inputs'])
    summary=json.loads((root/'summary.json').read_text());assert summary['finished']
    baseline=json.loads((Path(plan['base'])/'results.json').read_text())
    expected={x['case_id'] for x in baseline['cases'] if x['status']=='kinematic_candidate' and x['required_source_patch_displaced']}
    assert len(plan['jobs'])==len(expected) and {j['case_id'] for j in plan['jobs']}==expected
    rows={r['case_id']:r for r in summary['rows']};assert set(rows)==expected
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as ex:
        checked=list(ex.map(inspect,[(j,rows[j['case_id']]) for j in plan['jobs']]))
    adopted=[r for r in checked if r['adopted']];gaps=[g for r in adopted for g in r['focus_gaps_m']]
    report={'cases_verified':len(checked),'adopted':len(adopted),'retained':len(checked)-len(adopted),
        'max_adopted_focus_gap_m':max(gaps,default=None),'repaired_phase_finger_references':len(gaps),
        'max_proposal_combined_bend_deg':max(r['max_combined_bend_deg'] for r in checked),
        'max_proposal_oriented_angle_deg':max(r['max_oriented_angle_deg'] for r in checked),
        'failure_reason_counts':dict(Counter(f for r in rows.values() if not r['adopted'] for f in r['failure_reasons'])),
        'all_baseline_input_hashes_unchanged':True,'actual_fk_and_native_limits_verified':True,
        'adopted_geometry_natural_and_protected_contacts_rechecked':True,
        'pregrasp_and_unaffected_phases_exactly_preserved':True,'physical_passed':None,'full_task_passed':None}
    verify(plan['inputs']);atomic_json(root/'check.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--workers',type=int,default=8);a=p.parse_args();print(json.dumps(check(a.output,a.workers),indent=2))
