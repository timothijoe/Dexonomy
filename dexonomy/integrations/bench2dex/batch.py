"""Bounded single-worker local grasp jobs with immutable resume identities."""
from pathlib import Path
from types import SimpleNamespace
from time import monotonic
import json

from .common import atomic_json
from .local_grasp import generate_grasp


BALL_ASSETS = ['a053_mini_soccer_ball', 'a056_tennis_ball', 'a058_golf_ball', 'a144_table_tennis']


def run_batch(cfg, args):
    if args.max_cases < 1 or args.seeds < 1:
        raise ValueError('Batch case/seed budgets must be positive')
    sides = ['right', 'left'] if args.side == 'both' else [args.side]
    assets = args.assets or BALL_ASSETS
    if set(assets) - set(BALL_ASSETS):
        raise ValueError('First batch supports task-27 balls only')
    output = Path(args.output)
    if not args.check_only:
        output.mkdir(parents=True, exist_ok=True)
    rows, started = [], monotonic()
    cases = [(asset, side, category, seed) for asset in assets for side in sides for category in args.categories for seed in range(args.start_seed, args.start_seed + args.seeds)]
    selected = cases[:args.max_cases]
    for asset, side, category, seed in selected:
        case_id = f'{asset}__{side}__{category}__seed{seed}'
        folder = output / case_id
        params = SimpleNamespace(task='27_ball_box_loading', asset=asset, side=side, category=category, seed=seed,
                                 models=args.models, grasp_config=args.grasp_config, output=str(folder), execute=args.execute,
                                 check_only=args.check_only, resume=args.resume)
        before = monotonic()
        try:
            result = generate_grasp(cfg, params)
            row = {'case_id': case_id, **result, 'seconds': monotonic() - before}
        except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
            row = {'case_id': case_id, 'status': 'rejected', 'failure_reason': str(exc), 'seconds': monotonic() - before}
        if (folder / 'execution_report.json').exists():
            physical = json.loads((folder / 'execution_report.json').read_text())
            row.update(physical_failure_reasons=physical['failure_reasons'], lift_m=physical['lift_m'],
                       max_relative_translation_m=physical['max_relative_translation_m'], max_relative_angle_deg=physical['max_relative_angle_deg'])
        rows.append(row)
        if not args.check_only:
            atomic_json(output / 'summary.json', summarize(rows, len(cases), len(selected), monotonic() - started))
            (output / 'summary.md').write_text(summary_markdown(rows))
    return summarize(rows, len(cases), len(selected), monotonic() - started)


def summarize(rows, planned, selected, seconds):
    return {'schema_version': 1, 'validation_scope': 'mujoco_hand_only', 'worker_count': 1,
            'planned_cases': planned, 'budgeted_cases': selected, 'attempted_cases': len(rows), 'seconds': seconds,
            'geometry_only_valid': sum(r['status'] == 'geometry_valid' for r in rows),
            'dynamic_valid': sum(r['status'] == 'dynamic_valid' for r in rows), 'rejected': sum(r['status'] == 'rejected' for r in rows),
            'cases': rows, 'isaaclab_passed': None, 'full_task_passed': None,
            'note': 'Development cases, not a benchmark success-rate estimate; no unbounded retries'}


def summary_markdown(rows):
    lines = ['# MuJoCo 本地抓取运行清单', '', '仅单手局部验证；不代表 Isaac 或完整任务通过。', '',
             '| 样本 | 状态 | 抬起 m | 失败原因 |', '| --- | --- | ---: | --- |']
    for row in rows:
        reasons = ', '.join(row.get('physical_failure_reasons', [])) or row.get('failure_reason', '')
        lines.append(f'| {row["case_id"]} | {row["status"]} | {row.get("lift_m", 0):.4f} | {reasons} |')
    return '\n'.join(lines) + '\n'
