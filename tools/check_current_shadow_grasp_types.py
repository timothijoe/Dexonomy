#!/usr/bin/env python3
"""Validate fixed object/category coverage and all reused source identities."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json,sha256
from dexonomy.integrations.bench2dex.current_grasp_types import PARENTS,INVENTORY
from dexonomy.integrations.bench2dex.shadow_batch import digest,verify_plan


def validate_pairs(models,entries,catalog):
    expected={(name,cat) for name in models for cat in catalog[name]['categories']}
    actual=[(r['object'],r['category']) for r in entries]
    if len(actual)!=len(set(actual)):raise ValueError('Duplicate model/category coverage')
    if set(actual)!=expected:raise ValueError('Missing categories or unexpected objects')
    if len({r['case_id'] for r in entries})!=len(entries):raise ValueError('Duplicate case identifier')
    return len(expected)


def check(root):
    root=Path(root);plan=json.loads((root/'coverage_plan.json').read_text());copy=dict(plan);expected=copy.pop('identity')
    if digest(copy)!=expected:raise ValueError('Coverage plan identity changed')
    inventory=json.loads(INVENTORY.read_text());catalog={r['object']:r for r in inventory['objects']}
    current=set()
    for parent in PARENTS:
        for j in json.loads((parent/'plan.json').read_text())['jobs']:current.add(j['selection']['dexonomy_object'])
    if set(plan['models'])!=current:raise ValueError('Object scope changed')
    total=validate_pairs(plan['models'],plan['entries'],catalog)
    for receipt in [plan['inventory'],*plan['parents']]:
        if sha256(receipt['path'])!=receipt['sha256']:raise ValueError('Parent/inventory changed')
    reused=0
    for e in plan['entries']:
        if e['kind']!='reused':continue
        for key in ['result','postures']:
            if sha256(e[key]['path'])!=e[key]['sha256']:raise ValueError('Reused source changed')
        r=json.loads(Path(e['result']['path']).read_text())
        if r['status']!='kinematic_candidate' or not r['selected_quality']['passed'] or not r['selected_natural']['passed']:
            raise ValueError('Rejected pose reused as accepted')
        if (r['source_selection']['dexonomy_object'],r['source_selection']['category'])!=(e['object'],e['category']):
            raise ValueError('Reused result belongs to another model/category')
        reused+=1
    v1=json.loads((root/'v1/plan.json').read_text());verify_plan(v1)
    if {j['case_id'] for j in v1['jobs']}!={e['case_id'] for e in plan['entries'] if e['kind']=='new'}:raise ValueError('Missing new optimization jobs')
    report={'models':len(current),'model_category_pairs':total,'reused_accepted_pairs':reused,
        'new_jobs':len(v1['jobs']),'no_new_objects':True,'all_available_categories_covered_by_plan':True,
        'sources_models_and_reused_outputs_verified':True,'physical_passed':None}
    atomic_json(root/'plan_check.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_all_types/current44_2026-10-16'))
    a=p.parse_args();print(json.dumps(check(a.output),ensure_ascii=False,indent=2))
