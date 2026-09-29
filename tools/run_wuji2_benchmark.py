#!/usr/bin/env python3
"""Run the fixed Wuji2 development/holdout sample manifest."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


MANIFEST = Path("benchmarks/wuji2_retarget_v1.json")
PROFILES = {
    "baseline": {"tip": 100, "palm": 25, "wrist": 8, "joint": .75},
    "flexible_wrist": {"tip": 100, "palm": 10, "wrist": 3, "joint": .25},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--profile", choices=PROFILES, default="baseline")
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="all")
    parser.add_argument("--output", type=Path, default=Path("output/wuji2_benchmark"))
    parser.add_argument("--eval", action="store_true", help="Run six-direction MuJoCo evaluation")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    cases = [c for c in manifest["cases"] if args.split == "all" or c["split"] == args.split]
    if not cases:
        raise ValueError("No cases selected")
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate case IDs")
    profile_dir = args.output / args.profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    environment = dict(os.environ, MUJOCO_GL=os.environ.get("MUJOCO_GL", "egl"), PYTHONPATH=".")
    for case in cases:
        path = Path(case["source"])
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if case.get("sha256") and digest != case["sha256"]:
            raise ValueError(f"Input changed for {case['id']}")
        destination = profile_dir / case["id"]
        command = [sys.executable, "tools/retarget_wuji2_sample.py", "--source", str(path),
                   "--source-hand", case["hand"], "--index", str(case["index"]),
                   "--output", str(destination), "--no-render"]
        if not args.eval:
            command.append("--no-eval")
        for name, value in PROFILES[args.profile].items():
            command.extend([f"--{name}-weight", str(value)])
        completed = subprocess.run(command, env=environment, text=True, capture_output=True)
        row = {"id": case["id"], "split": case["split"], "hand": case["hand"],
               "family": case["family"], "category": case["category"], "source_sha256": digest,
               "exit_code": completed.returncode}
        if completed.returncode:
            row["error"] = completed.stderr[-2000:]
        else:
            result = json.loads((destination / "result.json").read_text())
            phase = result["phase_stats"]["grasp"]
            errors = list(phase["finger_error_mm"].values())
            contact = phase["wuji_contact"]
            source = phase["source_contact"]
            refinement = result["local_contact_optimization"]
            row.update({
                "finger_mean_mm": sum(errors) / len(errors), "finger_max_mm": max(errors),
                "hand_object_penetration_mm": max(0, -(contact["min_hand_object_distance_m"] or 0) * 1000),
                "self_penetration_mm": max(0, -(contact["min_self_distance_m"] or 0) * 1000),
                "source_near_contacts": source["within_1mm_count"],
                "joint_limit_violations": phase["joint_limit_violations"],
                "contact_refinement_accepted": refinement.get("accepted", False),
                "evaluation_passed": result["evaluation"].get("passed"),
            })
        rows.append(row)
        print(f"{case['id']}: {'ok' if not completed.returncode else 'failed'}", flush=True)
    (profile_dir / "summary.json").write_text(json.dumps({"manifest": str(args.manifest),
        "profile": args.profile, "weights": PROFILES[args.profile], "evaluated": args.eval,
        "cases": rows}, indent=2), encoding="utf-8")
    with (profile_dir / "summary.csv").open("w", newline="") as handle:
        columns = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    if any(row["exit_code"] for row in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
