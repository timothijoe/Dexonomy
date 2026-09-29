#!/usr/bin/env python3
"""Export a separate two-hand viewer for the object-independent finger fit."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import mujoco
import numpy as np

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from tools.export_wuji2_comparison import (
    CAMERAS, ORBIT_AZIMUTHS, ORBIT_ELEVATIONS, canonical_root,
    export_glb, hand_only_q, render_image, shared_bounds,
)
from tools.retarget_wuji2_sample import PHASES, SOURCE_SPECS, WUJI, source_scene


def export_case(case, result, action, output, width, height):
    data = np.load(case["source"], allow_pickle=True).item()  # trusted fixed manifest
    scene, _, _ = source_scene(data, case["hand"], case["index"])
    source = MuJoCo_VisEnv(HandCfg(str(SOURCE_SPECS[case["hand"]]["xml"]), freejoint=True), scene, vis_mode="visual")
    wuji = MuJoCo_VisEnv(HandCfg(str(WUJI), freejoint=True), scene, vis_mode="visual")
    source_q = [np.asarray(result["source_qpos"][phase], dtype=float) for phase in PHASES]
    fitted_q = [np.asarray(action["hand_only_fit"]["wuji_qpos"][phase], dtype=float) for phase in PHASES]
    roots = (canonical_root(source, source_q[1], case["hand"]), canonical_root(wuji, fitted_q[1], "wuji"))
    poses = ([hand_only_q(q, roots[0]) for q in source_q], [hand_only_q(q, roots[1]) for q in fitted_q])
    bounds = shared_bounds((source, wuji), poses, False)
    assets = {phase: {} for phase in PHASES}
    for role, env, sequence in (("source", source, poses[0]), ("wuji", wuji, poses[1])):
        env._model.vis.global_.offwidth = width
        env._model.vis.global_.offheight = height
        with mujoco.Renderer(env._model, height=height, width=width) as renderer:
            for phase, pose in zip(PHASES, sequence):
                stem = Path("assets") / case["id"] / f"{phase}_{role}"
                glb = stem.with_suffix(".glb")
                export_glb(env, pose, False, role, output / glb)
                images = []
                for view, angles in enumerate(CAMERAS):
                    path = stem.with_name(f"{stem.name}_view{view}").with_suffix(".webp")
                    render_image(env, renderer, pose, bounds, angles, role, False, output / path)
                    images.append(path.as_posix())
                grid = []
                for pitch, elevation in enumerate(ORBIT_ELEVATIONS):
                    row = []
                    for yaw, azimuth in enumerate(ORBIT_AZIMUTHS):
                        angles = (azimuth % 360, elevation)
                        if angles in CAMERAS:
                            row.append(images[CAMERAS.index(angles)])
                        else:
                            path = Path("orbit") / case["id"] / f"{phase}_{role}_p{pitch:02d}_y{yaw:02d}.webp"
                            render_image(env, renderer, pose, bounds, angles, role, False, output / path, quality=76)
                            row.append(path.as_posix())
                    grid.append(row)
                assets[phase][role] = {"images": images, "orbit_grid": grid, "glb": glb.as_posix()}
    return {"id": case["id"], "hand": case["hand"], "split": case["split"], "family": case["family"],
            "category": case["category"], "source": case["source"], "sample_index": case["index"],
            "assets": assets, "object_fit": action["object_fit"],
            "hand_only_fit": action["hand_only_fit"]["comparison"],
            "solver": action["hand_only_fit"]["solver"],
            "world_tip_error_mm": action["world_tip_error_mm"],
            "unmapped_wuji_fingers": action["unmapped_wuji_fingers"]}


def write_site(output, index):
    (output / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    template = Path(__file__).with_name("wuji2_hand_only.html").read_text(encoding="utf-8")
    embedded = json.dumps(index, ensure_ascii=False).replace("<", "\\u003c")
    (output / "index.html").write_text(template.replace("__HAND_ONLY_INDEX_JSON__", embedded), encoding="utf-8")
    shutil.copyfile(Path(__file__).with_name("wuji2_hand_only.js"), output / "app.js")
    vendor = output / "vendor"
    vendor.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("vendor") / "model-viewer.min.js", vendor / "model-viewer.min.js")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/wuji2_retarget_v1.json"))
    parser.add_argument("--results", type=Path, default=Path("output/wuji2_benchmark/baseline"))
    parser.add_argument("--actions", type=Path, default=Path("output/wuji2_hand_action_v1"))
    parser.add_argument("--output", type=Path, default=Path("output/wuji2_hand_only_viewer"))
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--width", type=int, default=480)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--index-only", action="store_true", help="Refresh the page shell from an existing export")
    args = parser.parse_args()
    if args.index_only:
        index = json.loads((args.output / "index.json").read_text(encoding="utf-8"))
        write_site(args.output, index)
        print(f"refreshed {args.output / 'index.html'}")
        return
    manifest = json.loads(args.manifest.read_text())
    cases = [case for case in manifest["cases"] if not args.ids or case["id"] in args.ids]
    if args.ids and len(cases) != len(set(args.ids)):
        raise ValueError("Unknown or duplicate case ID")
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for case in cases:
        if hashlib.sha256(Path(case["source"]).read_bytes()).hexdigest() != case["sha256"]:
            raise ValueError(f"Source changed: {case['id']}")
        result = json.loads((args.results / case["id"] / "result.json").read_text())
        action = json.loads((args.actions / (case["id"] + ".json")).read_text())
        if (result["source"], result["sample_index"], result["source_hand"]) != (case["source"], case["index"], case["hand"]):
            raise ValueError(f"Baseline result differs from manifest: {case['id']}")
        if (action["id"], action["hand"], action["split"]) != (case["id"], case["hand"], case["split"]):
            raise ValueError(f"Hand-only result differs from manifest: {case['id']}")
        if "hand_only_fit" not in action:
            raise ValueError(f"Hand-only fit missing: {case['id']}")
        records.append(export_case(case, result, action, args.output, args.width, args.height))
        print(f"exported {case['id']}", flush=True)
    index = {"title": "Wuji2 hand-only action fit", "phases": PHASES,
             "orbit_azimuths": ORBIT_AZIMUTHS, "orbit_elevations": ORBIT_ELEVATIONS,
             "records": records}
    write_site(args.output, index)
    print(f"wrote {args.output / 'index.html'}")


if __name__ == "__main__":
    main()
