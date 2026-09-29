#!/usr/bin/env python3
"""Reproduce one Shadow -> Wuji Hand 2 Beta 2 grasp experiment.

Run from the repository root with MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python.
All generated data goes to an ignored output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
import trimesh

from dexonomy.sim import HandCfg, MuJoCo_VisEnv, MuJoCo_OptEnv, MuJoCo_OptCfg, MuJoCo_EvalEnv
from dexonomy.util.file_util import load_scene_cfg


SOURCE = Path("assets/object/Dexonomy_GRASP_shadow/succ_collect/14_Tripod/0004e882b42844eda8b4ab7379cb04c8/floating/scale005.npy")
SHADOW = Path("assets/hand/shadow/right.xml")
WUJI = Path("assets/wuji-description/hand2/hand2_beta2/body/mjcf/right.xml")
PHASES = ("pregrasp", "grasp", "squeeze")
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
SHADOW_DISTAL = ("rh_thdistal", "rh_ffdistal", "rh_mfdistal", "rh_rfdistal", "rh_lfdistal")
WUJI_SITES = tuple(f"hand-r_{finger if finger == 'thumb' else finger + '_finger'}_tip" if finger != "pinky" else "hand-r_pinky_tip" for finger in FINGERS)
WUJI_PADS = tuple(f"r_{finger if finger == 'thumb' else finger + '_finger'}_tip_sensor_frame" if finger != "pinky" else "r_pinky_tip_sensor_frame" for finger in FINGERS)


def jsonable(value):
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, (np.floating, np.integer)):
        return jsonable(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def pose_from_variables(x):
    return np.r_[x[:3], Rotation.from_rotvec(x[3:6]).as_quat(scalar_first=True), x[6:]]


def variables_from_pose(q):
    return np.r_[q[:3], Rotation.from_quat(q[3:7], scalar_first=True).as_rotvec(), q[7:]]


def contact_stats(env, q):
    env.reset_qpos(q)
    ho, hh = env.get_contacts(0.0)
    return {
        "hand_object_count": len(ho["dist"]),
        "self_count": len(hh["dist"]),
        "min_hand_object_distance_m": float(min(ho["dist"], default=np.inf)),
        "min_self_distance_m": float(min(hh["dist"], default=np.inf)),
        "hand_object_bodies": sorted(set(ho["bn1"])),
    }, ho


def joint_limits(model):
    joints = [j for j in range(model.njnt) if model.jnt_qposadr[j] >= 7 and model.jnt_qposadr[j] < 27]
    assert len(joints) == 20
    return np.array([model.jnt_range[j] for j in joints]), [model.joint(j).name for j in joints]


def fingertip_positions(env, q, ids, local=None):
    env.reset_qpos(q)
    if local is None:
        return np.array([env._data.site_xpos[i].copy() for i in ids])
    return np.array([env._data.xpos[i] + env._data.xmat[i].reshape(3, 3) @ p for i, p in zip(ids, local)])


def fit_pose(env, target, palm_target, anchor, prior, limits, site_ids, max_nfev=140):
    mid = np.clip(prior[7:], limits[:, 0] + 0.002, limits[:, 1] - 0.002)
    x0 = variables_from_pose(np.r_[anchor[:7], mid])
    lower = np.r_[anchor[:3] - 0.18, [-6.3] * 3, limits[:, 0] + 0.001]
    upper = np.r_[anchor[:3] + 0.18, [6.3] * 3, limits[:, 1] - 0.001]
    x0 = np.clip(x0, lower + 1e-5, upper - 1e-5)
    palm_id = env._model.body("hand-r_wrist").id

    def residual(x):
        q = pose_from_variables(x)
        env.reset_qpos(q)
        tips = np.array([env._data.site_xpos[i] for i in site_ids])
        return np.r_[
            ((tips - target) * 100).ravel(),
            (env._data.xpos[palm_id] - palm_target) * 25,
            (x[:3] - anchor[:3]) * 8,
            (x[3:6] - variables_from_pose(anchor)[3:6]) * 0.8,
            (x[6:] - prior[7:]) * 0.75,
        ]

    result = least_squares(residual, x0, bounds=(lower, upper), max_nfev=max_nfev, ftol=1e-7)
    return pose_from_variables(result.x), {"success": bool(result.success), "nfev": result.nfev, "cost": result.cost}


def render_comparison(shadow, wuji, source_q, result_q, output):
    width, height = 640, 480
    bounds = []
    for env, poses in ((shadow, source_q), (wuji, result_q)):
        for q in poses:
            xmat, xpos = env.forward_kinematics(q)
            for kind in ("hand", "obj"):
                bounds.append(env.get_posed_mesh(xmat, xpos, kind).bounds)
    box = np.array(bounds)
    scene_bounds = np.stack((box[:, 0].min(axis=0), box[:, 1].max(axis=0)))
    images = []
    for env, poses in ((shadow, source_q), (wuji, result_q)):
        env._model.vis.global_.offwidth = width
        env._model.vis.global_.offheight = height
        with mujoco.Renderer(env._model, height=height, width=width) as renderer:
            for q in poses:
                env.reset_qpos(q)
                camera = mujoco.MjvCamera()
                camera.type = mujoco.mjtCamera.mjCAMERA_FREE
                camera.lookat[:] = scene_bounds.mean(axis=0)
                camera.distance = max(float(np.max(scene_bounds[1] - scene_bounds[0])) * 1.9, 0.25)
                camera.azimuth, camera.elevation = 135, -25
                renderer.update_scene(env._data, camera=camera)
                for geom in list(renderer.scene.geoms)[:renderer.scene.ngeom]:
                    if geom.objid < 0:
                        continue
                    name = env._model.body(env._model.geom_bodyid[geom.objid]).name
                    if name.startswith("hand-"):
                        geom.rgba[:] = (0.14, 0.39, 0.92, 1)
                    elif name.startswith("obj-"):
                        geom.rgba[:] = (0.65, 0.68, 0.73, 1)
                images.append(Image.fromarray(renderer.render().copy()))
    from PIL import ImageDraw
    canvas = Image.new("RGB", (width * 3, height * 2 + 32), "white")
    draw = ImageDraw.Draw(canvas)
    for row, hand in enumerate(("Shadow source", "Wuji2 kinematic")):
        draw.text((8, row * height + 8), hand, fill="black")
        for col, phase in enumerate(PHASES):
            canvas.paste(images[row * 3 + col], (col * width, row * height + 32))
            draw.text((col * width + 8, row * height + 18), phase, fill="black")
    canvas.save(output / "comparison.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--index", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("output/wuji2_single_sample"))
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    data = np.load(args.source, allow_pickle=True).item()  # trusted local dataset only
    if any(key not in data for key in ("scene_path", "scene_scale", *(f"{p}_qpos" for p in PHASES))):
        raise ValueError("Source record lacks required pose or scene fields")
    scale = float(np.asarray(data["scene_scale"])[args.index])
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("Invalid scene_scale")
    scene = load_scene_cfg(str(data["scene_path"]))
    obj_name = scene["task"]["obj_name"]
    obj = scene["scene"][obj_name]
    if obj["type"] != "rigid_object":
        raise ValueError("This prototype requires a rigid object")
    obj["scale"] = np.asarray(obj["scale"], dtype=float) * scale
    shadow = MuJoCo_VisEnv(HandCfg(str(SHADOW), freejoint=True), scene, vis_mode="visual")
    wuji = MuJoCo_VisEnv(HandCfg(str(WUJI), freejoint=True), scene, vis_mode="visual")
    sh_opt = MuJoCo_OptEnv(HandCfg(str(SHADOW), freejoint=True), scene, MuJoCo_OptCfg(obj_margin=0, hand_margin=0))
    w_opt = MuJoCo_OptEnv(HandCfg(str(WUJI), freejoint=True), scene, MuJoCo_OptCfg(obj_margin=0, hand_margin=0))
    source_q = [np.asarray(data[f"{p}_qpos"][args.index], dtype=float) for p in PHASES]
    # Calibrate source landmarks from the distal visual mesh: center of its
    # most distal 10% along local +Z. This is deterministic and mesh based.
    local = []
    for name in SHADOW_DISTAL:
        vertices = shadow.get_body_mesh(name).vertices
        cap = vertices[vertices[:, 2] >= np.quantile(vertices[:, 2], 0.9)]
        local.append(cap.mean(axis=0))
    sh_ids = [shadow._model.body("hand-" + name).id for name in SHADOW_DISTAL]
    site_ids = [wuji._model.site(name).id for name in WUJI_SITES]
    targets = [fingertip_positions(shadow, q, sh_ids, local) for q in source_q]
    palm_id = shadow._model.body("hand-rh_palm").id
    palms = []
    for q in source_q:
        shadow.reset_qpos(q)
        palms.append(shadow._data.xpos[palm_id].copy())
    limits, joint_names = joint_limits(wuji._model)
    # Shadow fingers run along +Z while Wuji2 fingers run along -Z.
    # Compose a 180-degree X rotation to align the two wrist frames.
    anchor = source_q[1].copy()[:7]
    anchor[3:7] = (Rotation.from_quat(anchor[3:7], scalar_first=True) * Rotation.from_euler("x", 180, degrees=True)).as_quat(scalar_first=True)
    base = np.r_[anchor, np.clip(np.zeros(20), limits[:, 0] + .01, limits[:, 1] - .01)]
    initial_error = np.linalg.norm(fingertip_positions(wuji, base, site_ids) - targets[1], axis=1) * 1000
    fitted = [None] * 3
    solver = {}
    fitted[1], solver["grasp"] = fit_pose(wuji, targets[1], palms[1], anchor, base, limits, site_ids)
    for i in (0, 2):
        phase_anchor = fitted[1].copy()
        phase_anchor[:3] += source_q[i][:3] - source_q[1][:3]
        fitted[i], solver[PHASES[i]] = fit_pose(wuji, targets[i], palms[i], phase_anchor, fitted[1], limits, site_ids)

    phase_stats = {}
    for i, phase in enumerate(PHASES):
        source_stats, _ = contact_stats(sh_opt, source_q[i])
        sh_opt.reset_qpos(source_q[i])
        near_contacts, _ = sh_opt.get_contacts(0.001)
        source_stats["within_1mm_count"] = len(near_contacts["dist"])
        wuji_stats, _ = contact_stats(w_opt, fitted[i])
        actual = fingertip_positions(wuji, fitted[i], site_ids)
        margin = np.minimum(fitted[i][7:] - limits[:, 0], limits[:, 1] - fitted[i][7:])
        phase_stats[phase] = {"source_contact": source_stats, "wuji_contact": wuji_stats,
            "finger_error_mm": dict(zip(FINGERS, np.linalg.norm(actual - targets[i], axis=1) * 1000)),
            "min_joint_limit_margin_rad": float(margin.min()), "joint_limit_violations": int(np.sum(margin < 0)),
            "solver": solver[phase],
            "previous_stage_wrist_shift_mm": None if i == 0 else float(np.linalg.norm(fitted[i][:3] - fitted[i-1][:3]) * 1000),
            "previous_stage_wrist_rotation_deg": None if i == 0 else float(np.rad2deg((Rotation.from_quat(fitted[i][3:7], scalar_first=True) * Rotation.from_quat(fitted[i-1][3:7], scalar_first=True).inv()).magnitude())),
            "previous_stage_joint_l2_rad": None if i == 0 else float(np.linalg.norm(fitted[i][7:] - fitted[i-1][7:]))}

    # Source contacts seed object targets. Wuji contacts are projected onto
    # its actual collision sensor-pad meshes, then expressed in body frames.
    sh_opt.reset_qpos(source_q[1])
    source_contacts, _ = sh_opt.get_contacts(0.001)
    w_opt.reset_qpos(fitted[1])
    collision_vis = MuJoCo_VisEnv(HandCfg(str(WUJI), freejoint=True), scene, vis_mode="collision")
    hand_cbody, hand_cpn_w, obj_cpn_w = [], [], []
    source_contact_report = []
    for finger, sh_body, pad, tip in zip(FINGERS, SHADOW_DISTAL, WUJI_PADS, targets[1]):
        candidates = [j for j, name in enumerate(source_contacts["bn1"]) if name == sh_body]
        if not candidates:
            source_contact_report.append({"finger": finger, "source_contact": False})
            continue
        j = min(candidates, key=lambda k: np.linalg.norm(source_contacts["pos"][k] - tip))
        obj_point = source_contacts["pos"][j]
        normal = source_contacts["normal"][j]
        body_id = w_opt._model.body("hand-" + pad).id
        body_rot = w_opt._data.xmat[body_id].reshape(3, 3)
        body_pos = w_opt._data.xpos[body_id]
        mesh = collision_vis.get_body_mesh(pad)
        query = ((obj_point - body_pos) @ body_rot).reshape(1, 3)
        closest, distance, _ = trimesh.proximity.closest_point_naive(mesh, query)
        hand_point = body_rot @ closest[0] + body_pos
        hand_cbody.append(pad)
        hand_cpn_w.append(np.r_[hand_point, normal])
        obj_cpn_w.append(np.r_[obj_point, normal])
        source_contact_report.append({"finger": finger, "source_contact": True, "pad": pad,
            "projection_gap_mm": float(distance[0] * 1000)})
    optimization = {"attempted": False, "reason": "No distal source contacts"}
    if hand_cbody:
        hand_cpn_w = np.asarray(hand_cpn_w)
        obj_cpn_w = np.asarray(obj_cpn_w)
        hand_cpn_b = w_opt.transform_cpn_w2b(hand_cbody, hand_cpn_w)
        # Fixed, short local refinement using the same force step as gen_grasp.
        before = np.linalg.norm(hand_cpn_w[:, :3] - obj_cpn_w[:, :3], axis=1)
        for _ in range(15):
            w_opt.apply_contact_forces(hand_cbody, hand_cpn_b, obj_cpn_w)
            w_opt.step_sim(5)
        candidate = w_opt.get_hand_qpos().copy()
        after_world = w_opt.transform_cpn_b2w(hand_cbody, hand_cpn_b)
        after = np.linalg.norm(after_world[:, :3] - obj_cpn_w[:, :3], axis=1)
        stats, _ = contact_stats(w_opt, candidate)
        margin = np.minimum(candidate[7:] - limits[:, 0], limits[:, 1] - candidate[7:])
        optimization = {"attempted": True, "steps": 15, "contact_bodies": hand_cbody,
            "required_cbody": [[b] for b in hand_cbody],
            "hand_cpn_w": hand_cpn_w, "hand_cpn_b": hand_cpn_b, "obj_cpn_w": obj_cpn_w,
            "initial_gap_mm": before * 1000, "final_gap_mm": after * 1000,
            "candidate_qpos": candidate, "candidate_contact": stats,
            "min_joint_limit_margin_rad": float(margin.min()),
            "accepted": bool(np.all(margin >= 0) and np.max(after) < np.max(before) and stats["min_hand_object_distance_m"] > -0.002)}

    # Evaluate the accepted pose only; a failed local refinement must not be
    # advertised as a grasp. MuJoCo's six-direction force-closure check is used.
    eval_pose = optimization["candidate_qpos"] if optimization.get("accepted") else fitted[1]
    eval_env = MuJoCo_EvalEnv(HandCfg(str(WUJI), freejoint=True), scene, debug_view=False)
    target_obj_pose = eval_env.get_active_obj_pose().copy()
    trajectory = [fitted[0], eval_pose, fitted[2]]
    try:
        passed, _, _ = eval_env.eval_fc(trajectory, ["ee_pose", "ee_pose"], [None, None], target_obj_pose, 0.02, 0.2)
        evaluation = {"criterion": "eval_fc six gravity-scale directions, 20 mm / 0.2 rad", "passed": bool(passed),
                      "object_translation_m": float(np.linalg.norm(eval_env.get_active_obj_pose()[:3] - target_obj_pose[:3]))}
    except Exception as exc:
        evaluation = {"passed": False, "error": str(exc)}

    render_comparison(shadow, wuji, source_q, fitted, output)
    result = {"status": "kinematic_retargeting", "source": str(args.source), "sample_index": args.index,
        "scene_path": str(data["scene_path"]), "scene_scale": scale, "object_scale": obj["scale"],
        "shadow_model": str(SHADOW), "wuji_model": str(WUJI),
        "wuji_model_sha256": hashlib.sha256(WUJI.read_bytes()).hexdigest(),
        "source_contact_fields_present": sorted(set(data) & {"hand_cbody", "hand_cpn_w", "obj_cpn_w", "required_cbody"}),
        "shadow_tip_definition": dict(zip(FINGERS, (dict(body=b, local_point_m=p) for b, p in zip(SHADOW_DISTAL, local)))),
        "wuji_tip_sites": dict(zip(FINGERS, WUJI_SITES)), "joint_names": joint_names,
        "shadow_qpos": dict(zip(PHASES, source_q)), "wuji_qpos": dict(zip(PHASES, fitted)),
        "initial_grasp_finger_error_mm": dict(zip(FINGERS, initial_error)),
        "phase_stats": phase_stats, "contact_target_reconstruction": source_contact_report,
        "local_contact_optimization": optimization, "evaluation": evaluation,
        "comparison_png": "comparison.png"}
    (output / "result.json").write_text(json.dumps(jsonable(result), indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(output), "finger_error_mm": phase_stats["grasp"]["finger_error_mm"],
                      "optimization_accepted": optimization.get("accepted"), "evaluation_passed": evaluation["passed"]}, indent=2))


if __name__ == "__main__":
    main()
