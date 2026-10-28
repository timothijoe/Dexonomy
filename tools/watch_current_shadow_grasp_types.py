#!/usr/bin/env python3
"""Refresh read-only review progress while the numerical batch runs."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.review_current_shadow_grasp_types import review
from dexonomy.integrations.bench2dex.common import atomic_json

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_all_types/current44_2026-10-16'))
    p.add_argument('--interval',type=int,default=30);a=p.parse_args();previous=None
    while True:
        path=a.output/'progress.json'
        if path.is_file():
            progress=json.loads(path.read_text());review_root=a.output/'review';review_root.mkdir(exist_ok=True)
            payload=json.dumps(progress,ensure_ascii=False).replace('<',r'\u003c')
            (review_root/'batch_progress.js').write_text('window.updateBatchProgress&&window.updateBatchProgress('+payload+');')
            marker=(progress.get('stage'),progress.get('completed'),progress.get('finished'))
            if marker!=previous:
                if progress.get('stage') in ['v3','repair','optimization_complete'] or previous is None:review(a.output)
                print(json.dumps(progress,ensure_ascii=False),flush=True);previous=marker
            if progress.get('finished'):review(a.output);break
        time.sleep(max(5,a.interval))
