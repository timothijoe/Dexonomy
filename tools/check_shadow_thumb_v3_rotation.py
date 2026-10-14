#!/usr/bin/env python3
"""Verify every camera-frame receipt, header, and unchanged pose identity."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from dexonomy.integrations.bench2dex.common import atomic_json
from dexonomy.integrations.bench2dex.shadow_batch import verify_completed
from dexonomy.integrations.bench2dex.thumb_v3_rotation import verify, identity, frame_name, PHASES, MODES


def check(root):
    root = Path(root); plan = json.loads((root / 'plan.json').read_text()); verify(plan)
    summary = json.loads((root / 'summary.json').read_text())
    if not summary['all_complete']: raise ValueError('Rotation export is incomplete')
    width, height = plan['config']['width'], plan['config']['height']
    expected = {frame_name(phase, mode, pitch, yaw) for phase in PHASES for mode in MODES
                for pitch in range(5) for yaw in range(12)}
    checks = []
    for job in plan['jobs']:
        folder = root / 'frames' / job['case_id']
        row = verify_completed(folder, identity(plan, job))
        if row is None or row['frames'] != 360: raise ValueError('Missing complete case')
        if {p.name for p in folder.glob('*.webp')} != expected: raise ValueError('Camera grid differs from plan')
        for name in sorted(expected):
            # Decode and inspect all three panels at cardinal yaws and extreme pitches.
            inspect_pixels = any(f'_p{p:02d}_y{y:02d}' in name for p in (0, 2, 4) for y in (0, 3, 6, 9))
            checks.append((folder / name, inspect_pixels))
    def inspect(item):
        path, pixels = item
        with Image.open(path) as im:
            if im.size != (width * 3, height) or im.format != 'WEBP': raise ValueError('Bad frame size/format: ' + str(path))
            if pixels:
                im.load()
                for role in range(3):
                    if im.crop((role * width, 0, (role + 1) * width, height)).getbbox() is None:
                        raise ValueError('Blank comparison panel: ' + str(path))
            else: im.verify()
        return int(pixels)
    with ThreadPoolExecutor(max_workers=4) as executor:
        decoded = sum(executor.map(inspect, checks))
    result = {'scope': plan['scope'], 'cases_verified': len(plan['jobs']),
              'frame_headers_verified': len(checks), 'three_panel_frames_decoded': decoded,
              'image_panel_size': [width, height], 'source_pose_hashes_unchanged': True,
              'all_frame_checksums_verified': True, 'phases': PHASES,
              'azimuths': plan['azimuths'], 'elevations': plan['elevations']}
    atomic_json(root / 'export_check.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/rotation'))
    args = parser.parse_args(); print(json.dumps(check(args.output), ensure_ascii=False, indent=2))
