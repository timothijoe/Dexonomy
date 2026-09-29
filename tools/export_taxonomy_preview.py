#!/usr/bin/env python3
"""Export a small, deterministic Dexonomy taxonomy preview as GLB files."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import mujoco
import trimesh
from PIL import Image

from dexonomy.sim import HandCfg, MuJoCo_VisEnv
from dexonomy.util.file_util import load_scene_cfg


DEFAULT_CLASSES = [
    "1_Large_Diameter",
    "14_Tripod",
    "24_Tip_Pinch",
]
PHASES = ["pregrasp", "grasp", "squeeze"]
PREVIEW_WIDTH = 960
PREVIEW_HEIGHT = 720
ORBIT_AZIMUTHS = [135 + 30 * step for step in range(12)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("assets/object/Dexonomy_GRASP_shadow/succ_collect"),
    )
    parser.add_argument("--hand-xml", type=Path, default=Path("assets/hand/shadow/right.xml"))
    parser.add_argument("--output", type=Path, default=Path("output/taxonomy_preview"))
    parser.add_argument("--samples-per-class", type=int, default=3)
    parser.add_argument("--classes", nargs="+", default=DEFAULT_CLASSES)
    return parser.parse_args()


def choose_paths(class_dir: Path, count: int) -> list[Path]:
    by_object: dict[str, Path] = {}
    for path in sorted(class_dir.glob("**/*.npy")):
        relative = path.relative_to(class_dir)
        object_name = relative.parts[0]
        by_object.setdefault(object_name, path)
    paths = list(by_object.values())
    if len(paths) <= count:
        return paths
    indices = np.linspace(0, len(paths) - 1, count, dtype=int)
    return [paths[index] for index in indices]


def color_mesh(mesh: trimesh.Trimesh, rgba: tuple[int, int, int, int]) -> trimesh.Trimesh:
    mesh = mesh.copy()
    # MuJoCo meshes are not guaranteed to use browser-facing winding. An
    # explicit double-sided PBR material keeps thin finger meshes visible in
    # glTF viewers while preserving opaque, stable colors.
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals(multibody=True)
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


def export_phase(
    env: MuJoCo_VisEnv, qpos: np.ndarray, destination: Path
) -> dict[str, list[list[float]]]:
    xmat, xpos = env.forward_kinematics(qpos)
    hand = color_mesh(env.get_posed_mesh(xmat, xpos, "hand"), (36, 99, 235, 255))
    obj = color_mesh(env.get_posed_mesh(xmat, xpos, "obj"), (165, 174, 189, 255))
    scene = trimesh.Scene()
    scene.add_geometry(obj, node_name="object", geom_name="object")
    scene.add_geometry(hand, node_name="shadow_hand", geom_name="shadow_hand")
    destination.parent.mkdir(parents=True, exist_ok=True)
    scene.export(destination)
    bounds = np.stack([np.minimum(hand.bounds[0], obj.bounds[0]), np.maximum(hand.bounds[1], obj.bounds[1])])
    return {"bounds": bounds.tolist()}


def render_preview(
    env: MuJoCo_VisEnv,
    renderer: mujoco.Renderer,
    qpos: np.ndarray,
    bounds: np.ndarray,
    destination: Path,
    azimuth: float = 135,
) -> None:
    """Render the same pose as the GLB with a shared camera for all phases."""
    env.forward_kinematics(qpos)
    mujoco.mj_forward(env._model, env._data)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = bounds.mean(axis=0)
    camera.distance = max(float(np.max(bounds[1] - bounds[0])) * 1.9, 0.25)
    camera.azimuth = azimuth
    camera.elevation = -25
    renderer.update_scene(env._data, camera=camera)
    for geom in list(renderer.scene.geoms)[: renderer.scene.ngeom]:
        if geom.objid < 0:
            continue
        body_name = env._model.body(env._model.geom_bodyid[geom.objid]).name
        if body_name.startswith("hand-"):
            geom.rgba[:] = (0.14, 0.39, 0.92, 1.0)
        elif body_name.startswith("obj-"):
            geom.rgba[:] = (0.65, 0.68, 0.73, 1.0)
    rgb = renderer.render()
    renderer.enable_segmentation_rendering()
    mask = renderer.render()[:, :, 0] >= 0
    renderer.disable_segmentation_rendering()
    background = np.array((245, 247, 251), dtype=np.uint8)
    rgb = np.where(mask[:, :, None], rgb, background)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(rgb)
    if destination.suffix == ".webp":
        image = image.resize((640, 480), Image.Resampling.LANCZOS)
        image.save(destination, quality=78)
    else:
        image.save(destination)


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = []

    for class_name in args.classes:
        class_dir = args.data_root / class_name
        if not class_dir.is_dir():
            raise FileNotFoundError(class_dir)
        selected = choose_paths(class_dir, args.samples_per_class)
        for sample_number, data_path in enumerate(selected, start=1):
            data = np.load(data_path, allow_pickle=True).item()
            sample_count = int(data["grasp_qpos"].shape[0])
            sample_index = sample_count // 2
            scene_path = Path(str(data["scene_path"]))
            scene_cfg = load_scene_cfg(str(scene_path))
            scene_scale = float(np.asarray(data["scene_scale"])[sample_index])
            if not np.isfinite(scene_scale) or scene_scale <= 0:
                raise ValueError(f"Invalid scene_scale {scene_scale} in {data_path} [{sample_index}]")
            target_name = scene_cfg["task"]["obj_name"]
            target = scene_cfg["scene"][target_name]
            if target["type"] != "rigid_object":
                raise NotImplementedError(f"Preview currently requires a rigid target: {data_path}")
            target["scale"] = np.asarray(target["scale"], dtype=float) * scene_scale
            env = MuJoCo_VisEnv(
                hand_cfg=HandCfg(str(args.hand_xml), freejoint=True),
                scene_cfg=scene_cfg,
                vis_mode="visual",
            )
            relative_source = data_path.relative_to(args.data_root)
            record = {
                "class_name": class_name,
                "sample_number": sample_number,
                "sample_index": sample_index,
                "sample_count_in_file": sample_count,
                "source": relative_source.as_posix(),
                "scene_path": str(scene_path),
                "scene_scale_multiplier": scene_scale,
                "object_scale": np.asarray(target["scale"]).tolist(),
                "phases": {},
            }
            stem = f"sample_{sample_number:02d}"
            phase_bounds = []
            for phase in PHASES:
                glb_relative = Path("assets") / class_name / f"{stem}_{phase}.glb"
                extra = export_phase(env, data[f"{phase}_qpos"][sample_index], output / glb_relative)
                png_relative = Path("previews") / class_name / f"{stem}_{phase}.png"
                record["phases"][phase] = {
                    "glb": glb_relative.as_posix(),
                    "png": png_relative.as_posix(),
                    **extra,
                }
                phase_bounds.append(np.asarray(extra["bounds"]))
            shared_bounds = np.stack(phase_bounds)
            shared_bounds = np.stack((shared_bounds[:, 0].min(axis=0), shared_bounds[:, 1].max(axis=0)))
            env._model.vis.global_.offwidth = PREVIEW_WIDTH
            env._model.vis.global_.offheight = PREVIEW_HEIGHT
            with mujoco.Renderer(env._model, height=PREVIEW_HEIGHT, width=PREVIEW_WIDTH) as renderer:
                for phase in PHASES:
                    phase_record = record["phases"][phase]
                    qpos = data[f"{phase}_qpos"][sample_index]
                    png = phase_record["png"]
                    render_preview(env, renderer, qpos, shared_bounds, output / png)
                    orbit = [png]
                    for frame, azimuth in enumerate(ORBIT_AZIMUTHS[1:], start=1):
                        relative = Path("orbit") / class_name / f"{stem}_{phase}_{frame:02d}.webp"
                        render_preview(env, renderer, qpos, shared_bounds, output / relative, azimuth)
                        orbit.append(relative.as_posix())
                    phase_record["orbit"] = orbit
            records.append(record)
            print(f"exported {class_name} {stem}: {relative_source} [{sample_index}]")

    index = {
        "title": "Dexonomy Shadow Hand Taxonomy Preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classes": args.classes,
        "phases": PHASES,
        "records": records,
    }
    (output / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    template = Path(__file__).with_name("taxonomy_preview.html")
    (output / "index.html").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    script = Path(__file__).with_name("taxonomy_preview.js")
    shutil.copyfile(script, output / "app.js")
    renderer = Path(__file__).with_name("vendor") / "model-viewer.min.js"
    renderer_output = output / "vendor" / renderer.name
    renderer_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(renderer, renderer_output)
    print(f"wrote {output / 'index.html'}")


if __name__ == "__main__":
    main()
