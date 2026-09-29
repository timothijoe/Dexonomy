#!/usr/bin/env python3
"""Measure and optionally fit object-independent source/Wuji2 hand actions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from tools.retarget_wuji2_sample import PHASES, SOURCE_SPECS, WUJI, joint_limits, jsonable, source_scene


def landmarks(env, q, spec, tip_definitions):
    env.reset_qpos(q)
    model, data = env._model, env._data

    def body(name):
        return data.xpos[model.body("hand-" + name).id].copy()

    palm = body(spec["palm_body"])
    index, middle, ring = (body(spec["frame_bodies"][key]) for key in ("index", "middle", "ring"))
    right = index - ring
    right /= np.linalg.norm(right)
    forward = middle - palm
    forward -= right * np.dot(forward, right)
    forward /= np.linalg.norm(forward)
    frame = np.stack((right, forward, np.cross(right, forward)), axis=1)
    bases = {finger: body(name) for finger, name in spec["finger_bases"].items()}
    tips = {}
    for finger, entry in spec["tips"].items():
        if entry["kind"] == "site":
            tips[finger] = data.site_xpos[model.site(entry["name"]).id].copy()
        else:
            point = tip_definitions[finger]
            if entry["body"] != point["body"]:
                raise ValueError(f"Tip body changed for {finger}")
            body_id = model.body("hand-" + entry["body"]).id
            tips[finger] = data.xpos[body_id] + data.xmat[body_id].reshape(3, 3) @ np.asarray(point["local_point_m"])
    return {finger: frame.T @ (tips[finger] - bases[finger]) for finger in tips}


def world_tips(env, q, spec, tip_definitions):
    env.reset_qpos(q)
    model, data = env._model, env._data
    tips = {}
    for finger, entry in spec["tips"].items():
        if entry["kind"] == "site":
            tips[finger] = data.site_xpos[model.site(entry["name"]).id].copy()
        else:
            point = tip_definitions[finger]
            body_id = model.body("hand-" + entry["body"]).id
            tips[finger] = data.xpos[body_id] + data.xmat[body_id].reshape(3, 3) @ np.asarray(point["local_point_m"])
    return tips


def world_tip_error(source_env, target_env, source_poses, target_poses, source_spec, target_spec, tip_definitions, mapping):
    output = {}
    for phase, source_q, target_q in zip(PHASES, source_poses, target_poses):
        source = world_tips(source_env, source_q, source_spec, tip_definitions)
        target = world_tips(target_env, target_q, target_spec, {})
        output[phase] = {finger: float(np.linalg.norm(source[finger] - target[other]) * 1000)
                         for finger, other in mapping.items()}
    return output


def neutral_q(env, reference):
    q = np.asarray(reference, dtype=float).copy()
    for joint in range(env._model.njnt):
        address = int(env._model.jnt_qposadr[joint])
        if address < 7 or address >= len(q):
            continue
        if env._model.jnt_type[joint] != 3:  # scalar hinge joints
            raise ValueError("Expected scalar hand joints")
        value = 0.0
        if env._model.jnt_limited[joint]:
            value = np.clip(value, *env._model.jnt_range[joint])
        q[address] = value
    return q


def descriptors(env, poses, spec, tip_definitions):
    neutral = landmarks(env, neutral_q(env, poses[1]), spec, tip_definitions)
    lengths = {finger: float(np.linalg.norm(vector)) for finger, vector in neutral.items()}
    if any(length < 1e-5 for length in lengths.values()):
        raise ValueError("Finger neutral reach is degenerate")
    reference = {finger: neutral[finger] / lengths[finger] for finger in neutral}
    phases = {}
    for phase, q in zip(PHASES, poses):
        vectors = landmarks(env, q, spec, tip_definitions)
        phases[phase] = {finger: {
            "shape": vectors[finger] / lengths[finger],
            "action": vectors[finger] / lengths[finger] - reference[finger],
            "closure": 1 - np.linalg.norm(vectors[finger]) / lengths[finger],
        } for finger in vectors}
    return lengths, phases


def compare(source, target, mapping):
    phases = {}
    for phase in PHASES:
        phases[phase] = {finger: {
            "shape_error": float(np.linalg.norm(source[phase][finger]["shape"] - target[phase][other]["shape"])),
            "action_error": float(np.linalg.norm(source[phase][finger]["action"] - target[phase][other]["action"])),
            "closure_error": float(abs(source[phase][finger]["closure"] - target[phase][other]["closure"])),
        } for finger, other in mapping.items()}
    transitions = {}
    for before, after in zip(PHASES, PHASES[1:]):
        transitions[f"{before}_to_{after}"] = {finger: float(np.linalg.norm(
            (source[after][finger]["action"] - source[before][finger]["action"])
            - (target[after][other]["action"] - target[before][other]["action"])
        )) for finger, other in mapping.items()}
    means = {metric: float(np.mean([phases[p][f][metric] for p in PHASES for f in mapping]))
             for metric in ("shape_error", "action_error", "closure_error")}
    means["transition_error"] = float(np.mean([value for row in transitions.values() for value in row.values()]))
    return {"phases": phases, "transitions": transitions, "mean": means}


def root_invariance_error(env, q, spec, tip_definitions):
    """Check that a rigid world transform leaves hand landmarks unchanged."""
    original = landmarks(env, q, spec, tip_definitions)
    rotation = Rotation.from_euler("xyz", [23, -31, 47], degrees=True)
    moved = q.copy()
    moved[:3] = rotation.apply(q[:3]) + [0.13, -0.08, 0.21]
    moved[3:7] = (rotation * Rotation.from_quat(q[3:7], scalar_first=True)).as_quat(scalar_first=True)
    transformed = landmarks(env, moved, spec, tip_definitions)
    return float(max(np.linalg.norm(original[finger] - transformed[finger]) for finger in original))


def fit_hand_only(env, initial, source_descriptors, spec, mapping, tip_definitions, max_nfev):
    """Fit only Wuji finger joints; wrist/world pose is inherited but unused by the loss."""
    limits, _ = joint_limits(env._model)
    lower, upper = limits[:, 0] + 1e-4, limits[:, 1] - 1e-4
    poses = [np.asarray(initial[phase], dtype=float).copy() for phase in PHASES]
    neutral_vectors = landmarks(env, neutral_q(env, poses[1]), spec, tip_definitions)
    lengths = {finger: np.linalg.norm(vector) for finger, vector in neutral_vectors.items()}
    neutral_shape = {finger: neutral_vectors[finger] / lengths[finger] for finger in neutral_vectors}
    results = {}
    for index, phase in enumerate(PHASES):
        base = poses[index].copy()
        x0 = np.clip(base[7:], lower, upper)

        def residual(x):
            current = base.copy()
            current[7:] = x
            vectors = landmarks(env, current, spec, tip_definitions)
            parts = []
            for finger, other in mapping.items():
                src = source_descriptors[phase][finger]
                shape = vectors[other] / lengths[other]
                action = shape - neutral_shape[other]
                parts.extend((action - src["action"]) * 2.0)
                parts.extend((shape - src["shape"]) * 0.6)
            parts.extend((x - x0) * 0.025)
            return np.asarray(parts)

        fit = least_squares(residual, x0, bounds=(lower, upper), max_nfev=max_nfev)
        poses[index][7:] = fit.x
        results[phase] = {"success": bool(fit.success), "nfev": fit.nfev, "cost": float(fit.cost),
                          "min_limit_margin_rad": float(np.min(np.minimum(fit.x - limits[:, 0], limits[:, 1] - fit.x))),
                          "joints_within_1mrad_of_limit": int(np.sum(np.minimum(fit.x - limits[:, 0], limits[:, 1] - fit.x) < 0.001))}
    return dict(zip(PHASES, poses)), results


def analyze_case(case, result, correspondence, fit, max_nfev):
    data = np.load(case["source"], allow_pickle=True).item()  # fixed local manifest
    scene, _, _ = source_scene(data, case["hand"], case["index"])
    source = MuJoCo_VisEnv(HandCfg(str(SOURCE_SPECS[case["hand"]]["xml"]), freejoint=True), scene, vis_mode="visual")
    wuji = MuJoCo_VisEnv(HandCfg(str(WUJI), freejoint=True), scene, vis_mode="visual")
    source_spec, wuji_spec = correspondence["hands"][case["hand"]], correspondence["hands"]["wuji2"]
    mapping = correspondence["pairs"][case["hand"] + "_to_wuji2"]
    if set(mapping) != set(source_spec["tips"]) or not set(mapping.values()) <= set(wuji_spec["tips"]):
        raise ValueError("Incomplete finger correspondence")
    if result["wuji_tip_sites"] != {finger: wuji_spec["tips"][other]["name"] for finger, other in mapping.items()}:
        raise ValueError("Wuji tip sites differ from correspondence")
    src_poses = [np.asarray(result["source_qpos"][p], dtype=float) for p in PHASES]
    dst_poses = [np.asarray(result["wuji_qpos"][p], dtype=float) for p in PHASES]
    src_lengths, src_desc = descriptors(source, src_poses, source_spec, result["source_tip_definition"])
    dst_lengths, dst_desc = descriptors(wuji, dst_poses, wuji_spec, {})
    invariant_error = max(root_invariance_error(source, src_poses[1], source_spec, result["source_tip_definition"]),
                          root_invariance_error(wuji, dst_poses[1], wuji_spec, {}))
    if invariant_error > 1e-6:
        raise AssertionError(f"Hand descriptor depends on world root: {invariant_error}")
    record = {"id": case["id"], "split": case["split"], "hand": case["hand"],
              "mapped_fingers": mapping, "unmapped_wuji_fingers": sorted(set(wuji_spec["tips"]) - set(mapping.values())),
              "neutral_reach_m": {"source": src_lengths, "wuji2": dst_lengths},
              "root_invariance_error_m": invariant_error,
              "object_fit": compare(src_desc, dst_desc, mapping),
              "world_tip_error_mm": {"object_fit": world_tip_error(source, wuji, src_poses, dst_poses, source_spec, wuji_spec,
                                                                     result["source_tip_definition"], mapping)}}
    if fit:
        fitted, solver = fit_hand_only(wuji, result["wuji_qpos"], src_desc, wuji_spec, mapping, {}, max_nfev)
        _, fit_desc = descriptors(wuji, [fitted[p] for p in PHASES], wuji_spec, {})
        record["hand_only_fit"] = {"comparison": compare(src_desc, fit_desc, mapping),
                                   "solver": solver, "wuji_qpos": fitted}
        record["world_tip_error_mm"]["hand_only_fit"] = world_tip_error(
            source, wuji, src_poses, [fitted[p] for p in PHASES], source_spec, wuji_spec,
            result["source_tip_definition"], mapping)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/wuji2_retarget_v1.json"))
    parser.add_argument("--correspondence", type=Path, default=Path("benchmarks/hand_action_correspondence_v1.json"))
    parser.add_argument("--results", type=Path, default=Path("output/wuji2_benchmark/baseline"))
    parser.add_argument("--output", type=Path, default=Path("output/wuji2_hand_action_v1"))
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--fit-hand-only", action="store_true")
    parser.add_argument("--max-nfev", type=int, default=80)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    correspondence = json.loads(args.correspondence.read_text())
    cases = [case for case in manifest["cases"] if not args.ids or case["id"] in args.ids]
    if args.ids and len(cases) != len(set(args.ids)):
        raise ValueError("Unknown or duplicate case ID")
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for case in cases:
        if hashlib.sha256(Path(case["source"]).read_bytes()).hexdigest() != case["sha256"]:
            raise ValueError(f"Source changed: {case['id']}")
        result = json.loads((args.results / case["id"] / "result.json").read_text())
        if (result["source"], result["sample_index"], result["source_hand"]) != (case["source"], case["index"], case["hand"]):
            raise ValueError(f"Result differs from manifest: {case['id']}")
        record = analyze_case(case, result, correspondence, args.fit_hand_only, args.max_nfev)
        records.append(record)
        (args.output / (case["id"] + ".json")).write_text(json.dumps(jsonable(record), indent=2), encoding="utf-8")
        print(case["id"], record["object_fit"]["mean"], flush=True)
    summary = {"version": correspondence["version"], "correspondence_sha256": hashlib.sha256(args.correspondence.read_bytes()).hexdigest(),
               "fit_hand_only": args.fit_hand_only, "records": records}
    (args.output / "summary.json").write_text(json.dumps(jsonable(summary), indent=2), encoding="utf-8")
    with (args.output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "split", "hand", "fit", "shape_error", "action_error", "closure_error", "transition_error"])
        writer.writeheader()
        for record in records:
            for key, item in (("object_fit", record["object_fit"]), ("hand_only_fit", record.get("hand_only_fit", {}).get("comparison"))):
                if item:
                    writer.writerow({"id": record["id"], "split": record["split"], "hand": record["hand"], "fit": key, **item["mean"]})
    print(f"wrote {args.output / 'summary.csv'}")


if __name__ == "__main__":
    main()
