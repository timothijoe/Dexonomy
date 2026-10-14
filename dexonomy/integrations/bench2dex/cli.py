"""Small reproducible integration commands, independent of Isaac Lab imports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

from .common import atomic_json, load_config


def expected_joint_names(cfg):
    maps = yaml.safe_load((cfg['bench2dex_root'] / 'robots/active_dof_maps.yml').read_text())
    names = maps['robots'][cfg['robot_key']]['full_joint_names']
    if len(names) != 52 or len(set(names)) != 52:
        raise ValueError('Expected 52 unique explicitly named Wuji robot joints')
    return names


def main(argv=None):
    parser = argparse.ArgumentParser(description='Wuji v1 / Bench2Dex asset and dataset integration')
    parser.add_argument('--config', default=str(Path(__file__).resolve().parents[3] / 'configs/bench2dex/default.yaml'))
    parser.add_argument('--bench2dex-root')
    parser.add_argument('--asset-root')
    parser.add_argument('--demo-root')
    sub = parser.add_subparsers(dest='command', required=True)
    audit = sub.add_parser('inspect-assets', help='Write asset/URDF/USD dependency reports without simulation')
    audit.add_argument('--output', required=True)
    audit.add_argument('--require-ready', action='store_true', help='Exit 2 unless M0 acceptance is complete')
    resources = sub.add_parser('verify-resources', help='Verify selected official assets and demos against a pinned manifest')
    resources.add_argument('--manifest', default=str(Path(__file__).resolve().parents[3] / 'manifests/bench2dex-resources.json'))
    resources.add_argument('--output', required=True)
    catalog = sub.add_parser('catalog-assets', help='Build a task/asset/skill catalog without granting success labels')
    catalog.add_argument('--roles', default=str(Path(__file__).resolve().parents[3] / 'configs/bench2dex/task_roles.yaml'))
    catalog.add_argument('--output', required=True)
    grasp = sub.add_parser('generate-grasp', help='Generate one MuJoCo hand-only collision-surface grasp candidate')
    grasp.add_argument('--task', default='27_ball_box_loading')
    grasp.add_argument('--asset', default='a056_tennis_ball')
    grasp.add_argument('--side', choices=['right', 'left'], default='right')
    grasp.add_argument('--category', default='13_Precision_Sphere')
    grasp.add_argument('--seed', type=int, default=0)
    grasp.add_argument('--models', required=True)
    grasp.add_argument('--grasp-config', default=str(Path(__file__).resolve().parents[3] / 'configs/bench2dex/mujoco_grasp.yaml'))
    grasp.add_argument('--output', required=True)
    grasp.add_argument('--execute', action='store_true')
    grasp.add_argument('--check-only', action='store_true')
    grasp.add_argument('--resume', action='store_true')
    batch = sub.add_parser('batch-grasps', help='Bounded serial task-27 local grasp generation with per-case receipts')
    batch.add_argument('--assets', nargs='+')
    batch.add_argument('--side', choices=['right', 'left', 'both'], default='both')
    batch.add_argument('--categories', nargs='+', default=['13_Precision_Sphere'])
    batch.add_argument('--seeds', type=int, default=1)
    batch.add_argument('--start-seed', type=int, default=0)
    batch.add_argument('--max-cases', type=int, default=8)
    batch.add_argument('--models', required=True)
    batch.add_argument('--grasp-config', default=str(Path(__file__).resolve().parents[3] / 'configs/bench2dex/mujoco_grasp.yaml'))
    batch.add_argument('--output', required=True)
    batch.add_argument('--execute', action='store_true')
    batch.add_argument('--check-only', action='store_true')
    batch.add_argument('--resume', action='store_true')
    replay = sub.add_parser('replay-physics', help='Replay recorded motor targets and forces through actual physics steps')
    replay.add_argument('sample')
    replay.add_argument('--output', required=True)
    bundle = sub.add_parser('export-grasp', help='Verify checksums and export a self-contained local sample package')
    bundle.add_argument('sample')
    bundle.add_argument('--output', required=True)
    convert = sub.add_parser('convert-hands', help='Convert original hands and compare persisted MJCF FK against URDF')
    convert.add_argument('--output', required=True)
    convert.add_argument('--side', choices=['left', 'right', 'both'], default='both')
    runtime = sub.add_parser('compare-runtime', help='Compare externally captured Isaac Lab fixed postures to converted hands')
    runtime.add_argument('snapshot')
    runtime.add_argument('--models', required=True)
    runtime.add_argument('--output', required=True)
    validate = sub.add_parser('validate-episode', help='Check schema, cameras, homing and action alignment')
    validate.add_argument('episode')
    validate.add_argument('--output', required=True)
    validate.add_argument('--require-act', action='store_true')
    prepare = sub.add_parser('prepare-act', help='Prepare a separate ACT-compatible copy, preserving homing')
    prepare.add_argument('episode')
    prepare.add_argument('--output', required=True)
    prepare.add_argument('--check-only', action='store_true')
    prepare.add_argument('--resume', action='store_true')
    preview = sub.add_parser('preview-hands', help='Render original hands at a recorded named-joint posture; kinematics only')
    preview.add_argument('episode')
    preview.add_argument('--frame', type=int, default=400)
    preview.add_argument('--models', required=True)
    preview.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config, bench2dex_root=args.bench2dex_root, asset_root=args.asset_root, demo_root=args.demo_root)
        if args.command in ('replay-physics','export-grasp'):
            from .artifacts import replay_physics, export_sample
            report = replay_physics(args.sample,args.output) if args.command == 'replay-physics' else export_sample(args.sample,args.output)
            print(json.dumps(report,ensure_ascii=False))
            return 0 if args.command == 'export-grasp' or report['same_version_replay_passed'] else 2
        if args.command == 'catalog-assets':
            from .catalog import build_catalog, catalog_markdown
            report = build_catalog(cfg, args.roles)
            out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
            atomic_json(out / 'catalog.json', report)
            (out / 'catalog.md').write_text(catalog_markdown(report))
            print(json.dumps({'tasks': report['task_count'], 'object_directories': report['object_directory_count'], 'usd_entries': report['usd_entry_count']}))
            return 0
        if args.command == 'generate-grasp':
            from .local_grasp import generate_grasp
            report = generate_grasp(cfg, args)
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report.get('status') in ('geometry_valid', 'dynamic_valid', 'check_only') else 2
        if args.command == 'batch-grasps':
            from .batch import run_batch
            report = run_batch(cfg, args)
            print(json.dumps({key: value for key, value in report.items() if key != 'cases'}))
            return 0 if report['rejected'] == 0 else 2
        if args.command == 'verify-resources':
            from .provenance import verify_resources
            report = verify_resources(args.manifest, cfg['asset_root'], cfg['demo_root'])
            atomic_json(args.output, report)
            print(json.dumps({'verified': report['verified'], 'file_count': len(report['files']),
                              'failed': [r['path'] for r in report['files'] if r['status'] != 'verified']}))
            return 0 if report['verified'] else 2
        if args.command == 'inspect-assets':
            from .assets import inspect_assets, asset_markdown
            report = inspect_assets(cfg)
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=True)
            atomic_json(out / 'asset_report.json', report)
            (out / 'asset_report.md').write_text(asset_markdown(report), encoding='utf-8')
            print(json.dumps({'report': str(out / 'asset_report.md'), 'missing': len(report['missing']), 'm0_accepted': report['m0_accepted']}))
            return 2 if args.require_ready and not report['m0_accepted'] else 0
        if args.command == 'convert-hands':
            from .models import convert_hand
            semantics = yaml.safe_load(cfg['semantics'].read_text())
            sides = ['right', 'left'] if args.side == 'both' else [args.side]
            reports = {side: convert_hand(cfg['asset_root'] / cfg['hand_urdf'][side], Path(args.output) / side,
                                          semantics['sides'][side], cfg['validation']) for side in sides}
            print(json.dumps({side: {'urdf_mujoco_fk_passed': r['urdf_mujoco_fk_passed'], 'isaaclab_fk_passed': r['isaaclab_fk_passed'],
                                   'max_position_error_m': max(row['position_error_m'] for row in r['fk'])} for side, r in reports.items()}))
            return 0 if all(r['urdf_mujoco_fk_passed'] for r in reports.values()) else 2
        if args.command == 'compare-runtime':
            from .runtime import compare_runtime
            report = compare_runtime(json.loads(Path(args.snapshot).read_text()), cfg, args.models)
            atomic_json(args.output, report)
            print(json.dumps({'runtime_fk_passed': report['runtime_fk_passed'], 'm0_accepted': report['m0_accepted']}))
            return 0 if report['runtime_fk_passed'] else 2
        if args.command == 'preview-hands':
            from .preview import preview_hands
            print(json.dumps(preview_hands(args.episode, args.frame, args.models, args.output, cfg)))
            return 0
        from .episodes import prepare_episode, validate_episode
        names = expected_joint_names(cfg)
        if args.command == 'validate-episode':
            report = validate_episode(args.episode, names, cfg['camera_names'], require_act=args.require_act)
            atomic_json(args.output, report)
            print(json.dumps({'valid': report['valid'], 'act_ready': report['act_ready'], 'errors': report['errors'], 'warnings': report['warnings']}))
            return 0 if report['valid'] else 2
        report = prepare_episode(args.episode, args.output, names, cfg['camera_names'], check_only=args.check_only, resume=args.resume)
        print(json.dumps({key: value for key, value in report.items() if key != 'inspection'}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, ImportError, TimeoutError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
