#!/usr/bin/env python3
"""Build a file-compatible rotation viewer from verified completed grids."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.common import atomic_json
from dexonomy.integrations.bench2dex.shadow_batch import verify_completed
from dexonomy.integrations.bench2dex.thumb_v3_rotation import verify, identity


def build(root):
    root = Path(root)
    plan = json.loads((root / 'plan.json').read_text()); verify(plan)
    summary = json.loads((root / 'summary.json').read_text())
    if not summary['all_complete']: raise ValueError('Rotation export is incomplete')
    cases = set()
    for job in plan['jobs']:
        row = verify_completed(root / 'frames' / job['case_id'], identity(plan, job))
        if row is None or row['frames'] != 360: raise ValueError('Incomplete rotation case')
        cases.add(job['case_id'])
    review = json.loads((Path(plan['batch']) / 'review.json').read_text())
    entries = []
    for e in review['entries']:
        cid = Path(e['result']).parent.name
        if cid not in cases: continue
        entries.append({k: e[k] for k in ['asset', 'assetLabel', 'category', 'categoryLabel', 'status', 'versionLabel', 'selectedVersion', 'source', 'matchLabel']} |
                       {'caseId': cid, 'entryId': e['asset'] + '::' + e['category']})
    data = {'caseCount': len(cases), 'scope': plan['scope'], 'entries': entries,
            'width': plan['config']['width'], 'height': plan['config']['height'],
            'azimuths': plan['azimuths'], 'elevations': plan['elevations'],
            'back': Path(os.path.relpath(Path(plan['batch']) / 'index.html', root)).as_posix()}
    template = Path(__file__).with_name('shadow_thumb_v3_rotation.html').read_text()
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', r'\u003c')
    (root / 'index.html').write_text(template.replace('__ROTATION_DATA__', payload), encoding='utf-8')
    shutil.copyfile(Path(__file__).with_name('shadow_thumb_v3_rotation.js'), root / 'app.js')
    atomic_json(root / 'viewer.json', data)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('output/shadow_wuji_v3/all_matched_thumb_v3_final/rotation'))
    args = parser.parse_args(); r = build(args.output)
    print(json.dumps({k: v for k, v in r.items() if k != 'entries'}, ensure_ascii=False))
