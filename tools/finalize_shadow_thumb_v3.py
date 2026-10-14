#!/usr/bin/env python3
"""Prepare one bounded repair trial, then publish a traceable V3 comparison."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

os.environ.setdefault('MUJOCO_GL', 'egl')
for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[name] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json, file_receipt, sha256
from dexonomy.integrations.bench2dex.shadow_batch import digest, verify_completed
from dexonomy.integrations.bench2dex.thumb_v3_batch import prepare_v3, verify_v3, identity, summary


def terminal_batch(root):
    root = Path(root)
    plan = json.loads((root / 'plan.json').read_text()); verify_v3(plan)
    result = json.loads((root / 'summary.json').read_text())
    if not result['all_cases_terminal']: raise ValueError('Parent batch is incomplete')
    rows = {}
    for job in plan['jobs']:
        row = verify_completed(root / 'samples' / job['case_id'], identity(plan, job))
        if row is None: raise ValueError('Missing completed case: ' + job['case_id'])
        rows[job['case_id']] = row
    return plan, rows


def prepare_repair(primary, config, output):
    primary, output = Path(primary), Path(output)
    base, rows = terminal_batch(primary)
    if any(r['status'] == 'error' for r in rows.values()): raise ValueError('Fix primary execution errors first')
    rejected = {cid for cid, row in rows.items() if row['status'] == 'kinematic_rejected'}
    # This is a new trial plan; the existing primary plan stays immutable.
    plan = prepare_v3(base['baseline_root'], config, output)
    plan.pop('plan_identity')
    plan['jobs'] = [j for j in plan['jobs'] if j['case_id'] in rejected]
    plan['assets'] = [{**a, 'entries': [e for e in a['entries'] if e['case_id'] in rejected]}
                      for a in plan['assets'] if any(e['case_id'] in rejected for e in a['entries'])]
    plan.update(asset_count=len(plan['assets']), unique_source_cases=len(plan['jobs']),
                coverage_entries=sum(len(a['entries']) for a in plan['assets']),
                repair_only=True, primary_root=str(primary))
    plan['inputs']['primary_plan'] = file_receipt(primary / 'plan.json')
    plan['inputs']['repair_orchestrator'] = file_receipt(Path(__file__))
    for cid in sorted(rejected):
        plan['inputs']['primary_decision_' + cid] = file_receipt(primary / 'samples' / cid / 'receipt.json')
    plan['plan_identity'] = digest(plan); atomic_json(output / 'plan.json', plan)
    return plan


def choose_repair(primary, repair):
    if repair is None or repair['status'] == 'error': return False
    if primary['status'] == 'kinematic_candidate': return False
    if repair['status'] == 'kinematic_candidate': return True
    return bool(repair['selected_policy_passed'] and not primary['selected_policy_passed'])


def publish(primary, repair, output):
    primary, repair, output = map(Path, (primary, repair, output))
    if output.exists(): raise ValueError('Publish to a fresh directory')
    main_plan, main_rows = terminal_batch(primary)
    repair_plan, repair_rows = terminal_batch(repair)
    if repair_plan['primary_root'] != str(primary): raise ValueError('Repair belongs to another primary batch')
    expected = {cid for cid, row in main_rows.items() if row['status'] == 'kinematic_rejected'}
    if set(repair_rows) != expected: raise ValueError('Repair scope does not match primary rejections')
    plan = {**main_plan, 'inputs': dict(main_plan['inputs'])}; plan.pop('plan_identity')
    plan.update(primary_root=str(primary), repair_root=str(repair), published_comparison=True)
    plan['inputs'].update(primary_plan=file_receipt(primary / 'plan.json'),
                          repair_plan=file_receipt(repair / 'plan.json'),
                          repair_config=repair_plan['inputs']['config'],
                          publisher=file_receipt(Path(__file__)))
    for cid in sorted(main_rows):
        plan['inputs']['primary_output_' + cid] = file_receipt(primary / 'samples' / cid / 'receipt.json')
    for cid in sorted(repair_rows):
        plan['inputs']['repair_output_' + cid] = file_receipt(repair / 'samples' / cid / 'receipt.json')
    plan['plan_identity'] = digest(plan); output.mkdir(parents=True)
    atomic_json(output / 'plan.json', plan)
    rows, adopted_repairs = {}, 0
    for job in plan['jobs']:
        cid = job['case_id']; main = primary / 'samples' / cid; trial = repair / 'samples' / cid
        use_repair = choose_repair(main_rows[cid], repair_rows.get(cid))
        chosen = trial if use_repair else main
        folder = output / 'samples' / cid; shutil.copytree(chosen, folder)
        r = json.loads((folder / 'result.json').read_text())
        attempts = [{'kind': 'primary', 'config': json.loads((main / 'result.json').read_text())['config'],
                     'result': file_receipt(main / 'result.json'), 'status': main_rows[cid]['status']}]
        if cid in repair_rows:
            shutil.copytree(main, folder / 'primary_trial')
            shutil.copytree(trial, folder / 'geometry_repair_trial')
            attempts.append({'kind': 'geometry_repair', 'config': repair_plan['inputs']['config'],
                             'result': file_receipt(trial / 'result.json') if (trial / 'result.json').is_file() else None,
                             'status': repair_rows[cid]['status']})
        r['refinement_attempts'] = attempts; r['geometry_repair_selected'] = use_repair
        if use_repair and r['status'] == 'kinematic_candidate':
            r['selection_reason'] = 'geometric_thumb_constraints_repaired_after_geometry_trial'
            adopted_repairs += 1
        atomic_json(folder / 'result.json', r)
        row = dict(repair_rows[cid] if use_repair else main_rows[cid])
        row.update(selection_reason=r['selection_reason'], attempt_count=len(attempts), geometry_repair_selected=use_repair)
        artifacts = [{'path': str(p.relative_to(folder)), 'sha256': sha256(p)}
                     for p in sorted(folder.rglob('*')) if p.is_file() and p != folder / 'receipt.json']
        atomic_json(folder / 'receipt.json', {'identity': identity(plan, job), 'row': row, 'artifacts': artifacts})
        rows[cid] = row
    result = summary(plan, rows)
    result.update(primary_attempts=len(main_rows), geometry_repair_attempts=len(repair_rows),
                  total_attempts=len(main_rows) + len(repair_rows), adopted_geometry_repairs=adopted_repairs)
    atomic_json(output / 'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare-repair', 'publish'])
    parser.add_argument('--primary', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3'))
    parser.add_argument('--repair', type=Path, default=Path('output/shadow_wuji_v3/geometry_repair_trial'))
    parser.add_argument('--config', type=Path, default=Path('configs/bench2dex/shadow_thumb_v3_geometry_repair.yaml'))
    parser.add_argument('--output', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final'))
    args = parser.parse_args()
    result = prepare_repair(args.primary, args.config, args.repair) if args.operation == 'prepare-repair' else publish(args.primary, args.repair, args.output)
    print(json.dumps({k: result[k] for k in ['asset_count', 'coverage_entries', 'unique_source_cases'] if k in result}, ensure_ascii=False))
