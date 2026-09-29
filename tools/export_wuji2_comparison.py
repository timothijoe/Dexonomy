#!/usr/bin/env python3
"""Export a static-first, wrist-aligned comparison for the Wuji2 benchmark."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
import trimesh

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from tools.retarget_wuji2_sample import PHASES, SOURCE_SPECS, WUJI, source_scene, fingertip_positions


CAMERAS = ((135, -25), (45, 15))
ORBIT_AZIMUTHS = tuple(135 + 30 * step for step in range(12))
ORBIT_ELEVATIONS = (-65, -45, -25, -5, 15)
SOURCE_BASES = {
    "shadow": ("rh_palm", "rh_ffknuckle", "rh_mfknuckle", "rh_rfknuckle"),
    "allegro": ("palm", "ff_base", "mf_base", "rf_base"),
    "wuji": ("r_wrist", "r_index_finger_proximal", "r_middle_finger_proximal", "r_ring_finger_proximal"),
}
COLORS = {"source": (36, 99, 235, 255), "wuji": (17, 156, 126, 255), "object": (165, 174, 189, 255)}


def color_mesh(mesh, rgba):
    """Apply a double-sided GLB material without costly mesh repair."""
    mesh = mesh.copy()
    material = trimesh.visual.material.PBRMaterial(
        name=f"material_{rgba[0]}_{rgba[1]}_{rgba[2]}",
        baseColorFactor=np.asarray(rgba, dtype=np.uint8),
        metallicFactor=0.0,
        roughnessFactor=0.65,
        doubleSided=True,
        alphaMode="OPAQUE",
    )
    mesh.visual = trimesh.visual.TextureVisuals(material=material)
    return mesh


def canonical_root(env: MuJoCo_VisEnv, grasp_q: np.ndarray, hand: str) -> np.ndarray:
    """Align palm origin and anatomical index-ring/middle-base axes in world."""
    q = grasp_q.copy()
    q[:3] = 0
    q[3:7] = [1, 0, 0, 0]
    env.forward_kinematics(q)
    names = SOURCE_BASES[hand]
    positions = [env._data.xpos[env._model.body("hand-" + name).id].copy() for name in names]
    palm, index, middle, ring = positions
    right = index - ring
    right /= np.linalg.norm(right)
    forward = middle - palm
    forward -= right * np.dot(forward, right)
    forward /= np.linalg.norm(forward)
    normal = np.cross(right, forward)
    frame = np.stack((right, forward, normal), axis=1)
    rotation = frame.T
    return np.r_[-rotation @ palm, Rotation.from_matrix(rotation).as_quat(scalar_first=True)]


def hand_only_q(q: np.ndarray, root: np.ndarray) -> np.ndarray:
    return np.r_[root, q[7:]]


def posed_bounds(env: MuJoCo_VisEnv, q: np.ndarray, include_object: bool) -> np.ndarray:
    xmat, xpos = env.forward_kinematics(q)
    hand = env.get_posed_mesh(xmat, xpos, "hand")
    if not include_object:
        return hand.bounds
    obj = env.get_posed_mesh(xmat, xpos, "obj")
    return np.stack((np.minimum(hand.bounds[0], obj.bounds[0]), np.maximum(hand.bounds[1], obj.bounds[1])))


def shared_bounds(envs, poses, include_object):
    boxes = [posed_bounds(env, q, include_object) for env, sequence in zip(envs, poses) for q in sequence]
    return np.stack((np.min([b[0] for b in boxes], axis=0), np.max([b[1] for b in boxes], axis=0)))


def export_glb(env, q, include_object, role, destination):
    xmat, xpos = env.forward_kinematics(q)
    scene = trimesh.Scene()
    hand = color_mesh(env.get_posed_mesh(xmat, xpos, "hand"), COLORS[role])
    scene.add_geometry(hand, node_name=f"{role}_hand", geom_name=f"{role}_hand")
    if include_object:
        obj = color_mesh(env.get_posed_mesh(xmat, xpos, "obj"), COLORS["object"])
        scene.add_geometry(obj, node_name="object", geom_name="object")
    destination.parent.mkdir(parents=True, exist_ok=True)
    scene.export(destination)


def render_image(env, renderer, q, bounds, camera_angles, role, include_object, destination, quality=84):
    env.reset_qpos(q)
    if not include_object:
        # Visual-only hand frame. Move the free object away from the camera;
        # the exported hand pose itself is not modified by this operation.
        env._data.qpos[-7:-4] = [100, 100, 100]
        mujoco.mj_forward(env._model, env._data)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = bounds.mean(axis=0)
    camera.distance = max(float(np.max(bounds[1] - bounds[0])) * 1.9, 0.24)
    camera.azimuth, camera.elevation = camera_angles
    renderer.update_scene(env._data, camera=camera)
    for geom in list(renderer.scene.geoms)[:renderer.scene.ngeom]:
        if geom.objid < 0:
            continue
        name = env._model.body(env._model.geom_bodyid[geom.objid]).name
        if name.startswith("hand-"):
            geom.rgba[:] = np.asarray(COLORS[role]) / 255
        elif name.startswith("obj-"):
            geom.rgba[:] = np.asarray(COLORS["object"]) / 255
    rgb = renderer.render().copy()
    renderer.enable_segmentation_rendering()
    mask = renderer.render()[:, :, 0] >= 0
    renderer.disable_segmentation_rendering()
    rgb = np.where(mask[:, :, None], rgb, np.asarray((245, 247, 251), dtype=np.uint8))
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(destination, quality=quality)


def export_case(case, result, output, width, height):
    source_path = Path(case["source"])
    data = np.load(source_path, allow_pickle=True).item()  # fixed trusted manifest only
    scene, scale, _ = source_scene(data, case["hand"], case["index"])
    if not np.allclose(scene["scene"][scene["task"]["obj_name"]]["scale"], result["object_scale"]):
        raise ValueError(f"Scene scale differs from retarget result: {case['id']}")
    source = MuJoCo_VisEnv(HandCfg(str(SOURCE_SPECS[case["hand"]]["xml"]), freejoint=True), scene, vis_mode="visual")
    wuji = MuJoCo_VisEnv(HandCfg(str(WUJI), freejoint=True), scene, vis_mode="visual")
    source_q = [np.asarray(result["source_qpos"][phase], dtype=float) for phase in PHASES]
    wuji_q = [np.asarray(result["wuji_qpos"][phase], dtype=float) for phase in PHASES]
    source_root = canonical_root(source, source_q[1], case["hand"])
    wuji_root = canonical_root(wuji, wuji_q[1], "wuji")
    source_only = [hand_only_q(q, source_root) for q in source_q]
    wuji_only = [hand_only_q(q, wuji_root) for q in wuji_q]
    finger_names = list(result["source_tip_definition"])
    source_tip_ids = [source._model.body("hand-" + result["source_tip_definition"][finger]["body"]).id for finger in finger_names]
    source_tip_local = [np.asarray(result["source_tip_definition"][finger]["local_point_m"]) for finger in finger_names]
    wuji_tip_ids = [wuji._model.site(result["wuji_tip_sites"][finger]).id for finger in finger_names]
    hand_shape_error = {}
    for phase_index, phase in enumerate(PHASES):
        source_tips = fingertip_positions(source, source_only[phase_index], source_tip_ids, source_tip_local)
        wuji_tips = fingertip_positions(wuji, wuji_only[phase_index], wuji_tip_ids)
        hand_shape_error[phase] = dict(zip(finger_names, (np.linalg.norm(source_tips - wuji_tips, axis=1) * 1000).tolist()))
    with_bounds = shared_bounds((source, wuji), (source_q, wuji_q), True)
    only_bounds = shared_bounds((source, wuji), (source_only, wuji_only), False)
    assets = {}
    for role, env, with_poses, only_poses in (("source", source, source_q, source_only),
                                              ("wuji", wuji, wuji_q, wuji_only)):
        env._model.vis.global_.offwidth = width
        env._model.vis.global_.offheight = height
        with mujoco.Renderer(env._model, height=height, width=width) as renderer:
            for phase_index, phase in enumerate(PHASES):
                for mode, pose, bounds, include_object in (("scene", with_poses[phase_index], with_bounds, True),
                                                           ("hand", only_poses[phase_index], only_bounds, False)):
                    stem = Path("assets") / case["id"] / f"{phase}_{mode}_{role}"
                    glb = stem.with_suffix(".glb")
                    export_glb(env, pose, include_object, role, output / glb)
                    images = []
                    for view_index, angles in enumerate(CAMERAS):
                        image = stem.with_name(stem.name + f"_view{view_index}").with_suffix(".webp")
                        render_image(env, renderer, pose, bounds, angles, role, include_object, output / image)
                        images.append(image.as_posix())
                    orbit_grid = []
                    for pitch_index, elevation in enumerate(ORBIT_ELEVATIONS):
                        row = []
                        for yaw_index, azimuth in enumerate(ORBIT_AZIMUTHS):
                            angles = (azimuth % 360, elevation)
                            if angles in CAMERAS:
                                row.append(images[CAMERAS.index(angles)])
                                continue
                            orbit = Path("orbit") / case["id"] / f"{phase}_{mode}_{role}_p{pitch_index:02d}_y{yaw_index:02d}.webp"
                            render_image(env, renderer, pose, bounds, angles, role, include_object, output / orbit, quality=76)
                            row.append(orbit.as_posix())
                        orbit_grid.append(row)
                    assets.setdefault(phase, {}).setdefault(mode, {})[role] = {
                        "images": images, "glb": glb.as_posix(), "orbit_grid": orbit_grid,
                    }
    return {"id": case["id"], "split": case["split"], "hand": case["hand"], "family": case["family"],
            "category": case["category"], "source": case["source"], "sample_index": case["index"],
            "scene_scale": scale, "phase_stats": result["phase_stats"],
            "hand_shape_finger_error_mm": hand_shape_error,
            "evaluation": result["evaluation"], "assets": assets}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/wuji2_retarget_v1.json"))
    parser.add_argument("--results", type=Path, default=Path("output/wuji2_benchmark/baseline"))
    parser.add_argument("--output", type=Path, default=Path("output/wuji2_comparison"))
    parser.add_argument("--ids", nargs="*", help="Optional case IDs for a short smoke export")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    cases = [case for case in manifest["cases"] if not args.ids or case["id"] in args.ids]
    if args.ids and len(cases) != len(set(args.ids)):
        raise ValueError("Unknown or duplicate case ID")
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for case in cases:
        path = Path(case["source"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != case["sha256"]:
            raise ValueError(f"Source file changed: {case['id']}")
        result = json.loads((args.results / case["id"] / "result.json").read_text())
        if result["source"] != case["source"] or result["sample_index"] != case["index"] or result["source_hand"] != case["hand"]:
            raise ValueError(f"Retarget result does not match manifest: {case['id']}")
        records.append(export_case(case, result, args.output, args.width, args.height))
        print(f"exported {case['id']}", flush=True)
    index = {"title": "Wuji2 grasp migration comparison", "manifest": str(args.manifest),
             "camera_angles": [{"azimuth": azimuth, "elevation": elevation} for azimuth, elevation in CAMERAS],
             "orbit_azimuths": ORBIT_AZIMUTHS, "orbit_elevations": ORBIT_ELEVATIONS,
             "hand_alignment": "palm origin; index-to-ring and palm-to-middle-base axes at grasp phase",
             "phases": PHASES, "records": records}
    (args.output / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    template = Path(__file__).with_name("wuji2_comparison.html").read_text(encoding="utf-8")
    embedded_index = json.dumps(index, ensure_ascii=False).replace("<", "\\u003c")
    (args.output / "index.html").write_text(
        template.replace("__WUJI2_INDEX_JSON__", embedded_index), encoding="utf-8"
    )
    shutil.copyfile(Path(__file__).with_name("wuji2_comparison.js"), args.output / "app.js")
    vendor = args.output / "vendor"
    vendor.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("vendor") / "model-viewer.min.js", vendor / "model-viewer.min.js")
    print(f"wrote {args.output / 'index.html'}")


if __name__ == "__main__":
    main()
