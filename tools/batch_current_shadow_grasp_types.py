#!/usr/bin/env python3
"""Fill all available grasp types on the existing 44 meshes; no new objects."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
os.environ.setdefault('MUJOCO_GL','egl')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dexonomy.integrations.bench2dex.current_grasp_types import prepare,run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('output/shadow_wuji_all_types/current44_2026-10-16'))
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--workers',type=int,default=8,choices=range(1,9));a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with (a.output.parent/('.'+a.output.name+'.run.lock')).open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('This batch is already running; inspect progress.json instead of starting a duplicate.')
        plan=json.loads((a.output/'coverage_plan.json').read_text()) if a.resume else prepare(a.output)
        print(json.dumps({k:plan[k] for k in ['total_types','reused_types','new_types']}),flush=True)
        if not a.prepare_only:run(a.output,a.workers)
