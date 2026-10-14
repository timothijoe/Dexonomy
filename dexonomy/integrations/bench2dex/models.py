"""Original URDF inspection, independent FK and MuJoCo conversion diagnostics."""
from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

from .common import atomic_json, file_receipt, sha256


def _numbers(text, default):
    return [float(x) for x in text.split()] if text else list(default)


def origin(element):
    out = np.eye(4)
    if element is not None:
        out[:3, 3] = _numbers(element.get('xyz'), [0, 0, 0])
        out[:3, :3] = Rotation.from_euler('xyz', _numbers(element.get('rpy'), [0, 0, 0])).as_matrix()
    return out


class URDFModel:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.tree = ET.parse(self.path)
        root = self.tree.getroot()
        self.links = {el.get('name'): el for el in root.findall('link')}
        self.joints = {el.get('name'): el for el in root.findall('joint')}
        if len(self.links) != len(root.findall('link')) or len(self.joints) != len(root.findall('joint')):
            raise ValueError('Duplicate URDF link or joint names')
        child_links = {el.find('child').get('link') for el in self.joints.values()}
        roots = set(self.links) - child_links
        if len(roots) != 1:
            raise ValueError(f'URDF needs one root link; found {sorted(roots)}')
        self.root_link = roots.pop()
        self.moving_names = [name for name, el in self.joints.items() if el.get('type') != 'fixed']
        for name in self.moving_names:
            if self.joints[name].get('type') not in ('revolute', 'continuous', 'prismatic') or self.joints[name].find('mimic') is not None:
                raise ValueError(f'Unsupported joint/mimic: {name}')

    def limits(self, names):
        limits = []
        for name in names:
            el = self.joints[name].find('limit')
            if el is None or el.get('lower') is None or el.get('upper') is None:
                raise ValueError(f'Missing bounded joint limits: {name}')
            limits.append([float(el.get('lower')), float(el.get('upper'))])
        result = np.asarray(limits)
        if not np.isfinite(result).all() or np.any(result[:, 0] >= result[:, 1]):
            raise ValueError('Invalid joint limits')
        return result

    def forward(self, values: dict):
        if set(values) != set(self.moving_names):
            raise ValueError('FK must receive every moving joint explicitly')
        transforms = {self.root_link: np.eye(4)}
        pending = dict(self.joints)
        while pending:
            count = len(pending)
            for name, joint in list(pending.items()):
                parent = joint.find('parent').get('link')
                if parent not in transforms:
                    continue
                motion = np.eye(4)
                kind = joint.get('type')
                if kind != 'fixed':
                    axis = np.asarray(_numbers(joint.find('axis').get('xyz') if joint.find('axis') is not None else None, [1, 0, 0]))
                    axis /= np.linalg.norm(axis)
                    if kind == 'prismatic':
                        motion[:3, 3] = axis * values[name]
                    else:
                        motion[:3, :3] = Rotation.from_rotvec(axis * values[name]).as_matrix()
                transforms[joint.find('child').get('link')] = transforms[parent] @ origin(joint.find('origin')) @ motion
                del pending[name]
            if len(pending) == count:
                raise ValueError('Disconnected or cyclic URDF')
        return transforms

    def inventory(self):
        meshes = {}
        for mesh in self.tree.getroot().iter('mesh'):
            filename = mesh.get('filename')
            if filename.startswith('package://'):
                raise ValueError(f'Package URI requires explicit resolution: {filename}')
            path = (self.path.parent / filename).resolve()
            meshes[str(path)] = file_receipt(path)
        joints = {}
        for name, el in self.joints.items():
            joints[name] = {
                'type': el.get('type'), 'parent': el.find('parent').get('link'),
                'child': el.find('child').get('link'), 'T_parent_from_joint': origin(el.find('origin')).tolist(),
                'axis': _numbers(el.find('axis').get('xyz') if el.find('axis') is not None else None, [1, 0, 0]),
                'limit': dict(el.find('limit').attrib) if el.find('limit') is not None else None,
            }
        links = {name: {'inertial_xml': ET.tostring(el.find('inertial'), encoding='unicode') if el.find('inertial') is not None else None,
                        'collision_xml': [ET.tostring(x, encoding='unicode') for x in el.findall('collision')]} for name, el in self.links.items()}
        return {'source': file_receipt(self.path), 'root_link': self.root_link, 'moving_joint_names': self.moving_names,
                'joints': joints, 'links': links, 'meshes': list(meshes.values())}

    def fixed_transform(self, parent_link, child_link):
        """Return T_parent_from_child only along an explicitly fixed mount chain."""
        if parent_link not in self.links or child_link not in self.links:
            raise ValueError('Unknown link in fixed transform request')
        child_to_joint = {j.find('child').get('link'): j for j in self.joints.values()}
        T = np.eye(4)
        current = child_link
        seen = set()
        while current != parent_link:
            if current in seen or current not in child_to_joint:
                raise ValueError('Links are not connected by the requested fixed mount chain')
            seen.add(current)
            joint = child_to_joint[current]
            if joint.get('type') != 'fixed':
                raise ValueError('Mount transform crosses a moving joint')
            T = origin(joint.find('origin')) @ T
            current = joint.find('parent').get('link')
        return T


def convert_hand(urdf: Path, output: Path, semantics: dict, validation: dict) -> dict:
    """Native URDF conversion plus URDF/MuJoCo FK check; no Isaac success claim."""
    import mujoco
    parsed = URDFModel(urdf)
    names = [el['urdf_name'] for el in semantics['joints']]
    if set(names) != set(parsed.moving_names):
        raise ValueError('Explicit hand mapping does not cover original URDF joints')
    tips = semantics['tip_links']
    if parsed.root_link != semantics['palm_link'] or any(t not in parsed.links for t in tips):
        raise ValueError('Palm/tip semantics disagree with original URDF')
    root = parsed.tree.getroot()
    extension = root.find('mujoco')
    if extension is None:
        extension = ET.SubElement(root, 'mujoco')
    compiler = extension.find('compiler')
    if compiler is None:
        compiler = ET.SubElement(extension, 'compiler')
    compiler.set('fusestatic', 'false')
    compiler.set('discardvisual', 'false')
    compiler.set('meshdir', str((urdf.parent / compiler.get('meshdir', '.')).resolve()))
    # Name visual/collision geoms explicitly to avoid MuJoCo duplicate-name warnings.
    for link in root.findall('link'):
        for kind in ('visual', 'collision'):
            for i, item in enumerate(link.findall(kind)):
                item.set('name', f'{link.get("name")}_{kind}_{i}')
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
    output.mkdir(parents=True, exist_ok=True)
    mjcf = output / 'hand.xml'
    mujoco.mj_saveLastXML(str(mjcf), model)
    # Check the persisted/reloaded artifact, including compiler numeric rounding.
    model = mujoco.MjModel.from_xml_path(str(mjcf))
    data = mujoco.MjData(model)
    limits = parsed.limits(names)
    neutral = np.clip(np.zeros(len(names)), limits[:, 0] + 0.001, limits[:, 1] - 0.001)
    postures = {'neutral': neutral, 'quarter': limits[:, 0] + .25 * np.ptp(limits, axis=1),
                'middle': np.mean(limits, axis=1), 'three_quarters': limits[:, 0] + .75 * np.ptp(limits, axis=1)}
    for i, name in enumerate(names):
        if not np.allclose(model.jnt_range[model.joint(name).id], limits[i], atol=1e-6):
            raise ValueError(f'Converted limits disagree: {name}')
    rows = []
    for label, angles in postures.items():
        values = dict(zip(names, angles))
        reference = parsed.forward(values)
        for name, value in values.items():
            data.qpos[model.joint(name).qposadr[0]] = value
        mujoco.mj_forward(model, data)
        for tip in tips:
            idx = model.body(tip).id
            T = reference[tip]
            rows.append({'posture': label, 'tip': tip,
                         'position_error_m': float(np.linalg.norm(data.xpos[idx] - T[:3, 3])),
                         'angle_error_deg': float(np.rad2deg(Rotation.from_matrix(T[:3, :3].T @ data.xmat[idx].reshape(3, 3)).magnitude()))})
    report = {'schema_version': 1, 'source': parsed.inventory(), 'mjcf': file_receipt(mjcf),
              'converter': {'name': 'mujoco_native_urdf', 'version': mujoco.__version__, 'preserve_fixed_bodies': True},
              'joint_names': names, 'neutral_qpos_rad': neutral.tolist(),
              'postures_rad': {key: val.tolist() for key, val in postures.items()}, 'fk': rows,
              'urdf_mujoco_fk_passed': all(row['position_error_m'] <= validation['fk_position_tolerance_m'] and row['angle_error_deg'] <= validation['fk_angle_tolerance_deg'] for row in rows),
              'isaaclab_fk_passed': None,
              'limitations': ['Isaac Lab runtime comparison pending', 'MuJoCo mesh collisions use convex hulls',
                              'No dynamics or contact validation performed', 'URDF effort/inertia may differ from USD/Bench2Dex actuator overrides'],
              'tolerances': validation}
    atomic_json(output / 'model_report.json', report)
    return report
