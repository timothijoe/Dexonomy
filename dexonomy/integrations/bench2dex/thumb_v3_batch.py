"""Fixed V2-to-V3 batch with verified sources and explicit policy rejections."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
from pathlib import Path

import yaml

from .common import atomic_json, file_receipt, sha256
from .shadow_batch import digest, verify_completed
from .thumb_v2_batch import verify_v2, identity as v2_identity
from .shadow_thumb_v3 import refine_case


def prepare_v3(baseline_root, config_path, output):
    baseline_root, config_path, output = map(Path, (baseline_root, config_path, output))
    if output.exists(): raise ValueError('V3 output exists; use resume or a fresh directory')
    base = json.loads((baseline_root / 'plan.json').read_text()); verify_v2(base)
    cfg = yaml.safe_load(config_path.read_text())
    if cfg.get('schema_version') != 3: raise ValueError('V3 configuration required')
    jobs = []
    for job in base['jobs']:
        folder = baseline_root / 'samples' / job['case_id']
        row = verify_completed(folder, v2_identity(base, job))
        if not row or not row['postures_available'] or row['status'] == 'error':
            raise ValueError('Missing verified V2 posture: ' + job['case_id'])
        jobs.append({**job, 'baseline_folder': str(folder),
                     'baseline_receipt': file_receipt(folder / 'receipt.json'),
                     'baseline_result': file_receipt(folder / 'result.json'),
                     'baseline_postures': file_receipt(folder / 'postures.npz')})
    directory = Path(__file__).parent
    dependencies = ['shadow_thumb_v3.py', 'shadow_thumb_v2.py', 'shadow_retarget.py',
                    'thumb_v3_batch.py', 'thumb_v2_batch.py', 'shadow_batch.py', 'common.py']
    plan = {'schema_version': 3, 'asset_count': base['asset_count'],
            'coverage_entries': base['coverage_entries'], 'unique_source_cases': len(jobs),
            'assets': base['assets'], 'jobs': jobs, 'deferred_assets': base['deferred_assets'],
            'baseline_root': str(baseline_root), 'baseline_plan': file_receipt(baseline_root / 'plan.json'),
            'baseline_plan_identity': base['plan_identity'], 'side': 'right',
            'inputs': {'config': file_receipt(config_path),
                       'annotation': file_receipt(Path(cfg['source_pad_annotation'])),
                       **{name: file_receipt(directory / name) for name in dependencies}},
            'physical_passed': None, 'full_task_passed': None}
    plan['plan_identity'] = digest(plan)
    output.mkdir(parents=True); atomic_json(output / 'plan.json', plan)
    return plan


def verify_v3(plan):
    copy = dict(plan); expected = copy.pop('plan_identity')
    if digest(copy) != expected: raise ValueError('V3 plan changed')
    receipts = [plan['baseline_plan'], *plan['inputs'].values(),
                *[j[k] for j in plan['jobs'] for k in ['baseline_receipt', 'baseline_result', 'baseline_postures']]]
    for receipt in receipts:
        if sha256(receipt['path']) != receipt['sha256']:
            raise ValueError('V3 input changed: ' + receipt['path'])
    verify_v2(json.loads(Path(plan['baseline_plan']['path']).read_text()))


def identity(plan, job):
    return digest({'plan': plan['plan_identity'], 'case': job['case_id']})


def run_case(job, config, folder, expected):
    folder = Path(folder)
    try:
        result = refine_case(job['baseline_folder'], config, folder, render=True)
        result['bench_targets'] = sorted({a['bench_object'] for a in job['aliases']})
        result['batch_aliases'] = job['aliases']; atomic_json(folder / 'result.json', result)
        row = {'case_id': job['case_id'], 'status': result['status'],
               'selected_version': result['selected_version'], 'selection_reason': result['selection_reason'],
               'failure_reasons': result['failure_reasons'],
               'baseline_geometry_passed': result['baseline_quality']['passed'],
               'baseline_policy_passed': result['baseline_natural']['passed'],
               'selected_geometry_passed': result['selected_quality']['passed'],
               'selected_policy_passed': result['selected_natural']['passed'],
               'thumb_score_before': sum(m['score'] for m in result['baseline_thumb'].values()) / 3,
               'thumb_score_selected': sum(m['score'] for m in result['selected_thumb'].values()) / 3,
               'seconds': result['seconds'], 'postures_available': True,
               'solver_termination': result['joint_solver']['termination']}
    except Exception as exc:
        folder.mkdir(parents=True, exist_ok=True)
        row = {'case_id': job['case_id'], 'status': 'error', 'error': f'{type(exc).__name__}: {exc}',
               'postures_available': (folder / 'postures.npz').is_file()}
        atomic_json(folder / 'failure.json', row)
    artifacts = [{'path': str(p.relative_to(folder)), 'sha256': sha256(p)}
                 for p in sorted(folder.rglob('*')) if p.is_file()]
    atomic_json(folder / 'receipt.json', {'identity': expected, 'row': row, 'artifacts': artifacts})
    return row


def summary(plan, rows):
    ordered = [rows[j['case_id']] for j in plan['jobs'] if j['case_id'] in rows]
    return {'schema_version': 3, 'asset_count': plan['asset_count'],
            'coverage_entries': plan['coverage_entries'], 'unique_source_cases': len(plan['jobs']),
            'completed_source_cases': len(ordered), 'all_cases_terminal': len(ordered) == len(plan['jobs']),
            'status_counts': dict(Counter(r['status'] for r in ordered)),
            'selection_counts': dict(Counter(r.get('selected_version', 'error') for r in ordered)),
            'cases_with_postures': sum(r['postures_available'] for r in ordered),
            'physical_passed': None, 'full_task_passed': None, 'results': ordered}


def run_v3(plan, output, workers=4):
    if not 1 <= workers <= 4: raise ValueError('One to four workers supported')
    verify_v3(plan); output = Path(output); rows, pending = {}, []
    for job in plan['jobs']:
        folder = output / 'samples' / job['case_id']; expected = identity(plan, job)
        completed = verify_completed(folder, expected)
        if completed: rows[job['case_id']] = completed
        elif folder.exists(): raise ValueError('Incomplete case cannot be silently reused: ' + str(folder))
        else: pending.append((job, folder, expected))
    atomic_json(output / 'summary.json', summary(plan, rows))
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as executor:
        futures = [executor.submit(run_case, job, plan['inputs']['config']['path'], str(folder), expected)
                   for job, folder, expected in pending]
        for future in as_completed(futures):
            row = future.result(); rows[row['case_id']] = row
            atomic_json(output / 'summary.json', summary(plan, rows))
            print(json.dumps({'completed': len(rows), 'total': len(plan['jobs']), **row}, ensure_ascii=False), flush=True)
    return summary(plan, rows)
