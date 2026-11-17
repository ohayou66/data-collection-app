"""Conservative collision volumes for every URDF descendant of the wrist.

Recovery does not read or move the gripper. Moving links therefore cover their
entire URDF joint range, including mimic joints. Rotation extrema are analytic;
checking only open/closed poses would miss the volume between them.
"""

from dataclasses import dataclass
from itertools import product
from pathlib import Path
import math
import hashlib
import json
import xml.etree.ElementTree as ET

import numpy as np

from .geometry import transform


def _vector(value, size=3):
    result = np.array([float(v) for v in value.split()])
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError('Invalid URDF collision vector')
    return result


def _origin(node):
    return np.eye(4) if node is None else transform(
        _vector(node.get('xyz', '0 0 0')), _vector(node.get('rpy', '0 0 0')))


def _corners(low, high):
    return np.array(list(product(*zip(low, high))))


def _rotate_envelope(vertices, axis, lower, upper):
    """Exact coordinate extrema of these points rotated over a closed interval."""
    parallel = np.outer(vertices @ axis, axis)
    cosine = vertices - parallel
    sine = np.cross(axis, vertices)
    at_lower = parallel + cosine * math.cos(lower) + sine * math.sin(lower)
    at_upper = parallel + cosine * math.cos(upper) + sine * math.sin(upper)
    low, high = np.minimum(at_lower, at_upper), np.maximum(at_lower, at_upper)
    phase = np.arctan2(sine, cosine)
    radius = np.hypot(cosine, sine)
    for offset, sign in ((0., 1.), (math.pi, -1.)):
        extrema = phase + offset
        extrema += 2 * math.pi * np.ceil((lower - extrema) / (2 * math.pi))
        inside = extrema <= upper + 1e-12
        value = parallel + sign * radius
        if sign > 0:
            high = np.where(inside, np.maximum(high, value), high)
        else:
            low = np.where(inside, np.minimum(low, value), low)
    return _corners(low.min(axis=0), high.max(axis=0))


def _geometry(geometry, urdf):
    if geometry is None or len(geometry) != 1:
        raise ValueError('Missing or ambiguous URDF tool collision geometry')
    shape = geometry[0]
    if shape.tag == 'mesh':
        from .model import mesh_vertices

        filename = shape.get('filename', '')
        if not filename:
            raise ValueError('Missing URDF tool collision mesh filename')
        if filename.startswith('package://'):
            # Standard URDF package layout: <package>/urdf and <package>/meshes.
            relative = filename[len('package://'):].partition('/')[2]
            if not relative:
                raise ValueError('Invalid URDF package mesh path')
            path = urdf.parent.parent / relative
        else:
            path = urdf.parent / filename
        scale = _vector(shape.get('scale', '1 1 1'))
        if np.any(scale <= 0):
            raise ValueError('Invalid URDF tool collision mesh scale')
        vertices = mesh_vertices(path.resolve()) * scale
    elif shape.tag == 'box':
        size = _vector(shape.get('size', ''))
        if np.any(size <= 0):
            raise ValueError('Invalid URDF collision box size')
        vertices = _corners(-size / 2, size / 2)
    elif shape.tag in ('sphere', 'cylinder'):
        radius = float(shape.get('radius', 'nan'))
        half_z = radius if shape.tag == 'sphere' else float(shape.get('length', 'nan')) / 2
        if not np.isfinite([radius, half_z]).all() or min(radius, half_z) <= 0:
            raise ValueError('Invalid URDF collision radius/length')
        half = np.array([radius, radius, half_z])
        vertices = _corners(-half, half)
    else:
        raise ValueError('Unsupported URDF tool collision geometry: ' + shape.tag)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices) or not np.isfinite(vertices).all():
        raise ValueError('Invalid URDF tool collision mesh vertices')
    return vertices


@dataclass(frozen=True)
class ToolVolume:
    name: str
    center: np.ndarray
    half: np.ndarray
    moving: bool


def _verify_generated_assets(path, root):
    """Fail closed when CAD, URDF placement, or generated bounds go stale."""
    filename = root.get('tool_collision_manifest')
    if filename is None:
        if path.name in ('marvin_left_with_gripper.urdf', 'marvin_right_with_gripper.urdf'):
            raise ValueError('末端碰撞模型校验失败：缺少 CAD 覆盖清单，请重新生成碰撞网格')
        return  # Generic/user-authored URDFs need not use our CAD generator.
    if Path(filename).name != filename:
        raise ValueError('Invalid tool collision manifest path')
    try:
        manifest = json.loads(path.with_name(filename).read_text())
        if (manifest['schema'] != 1
                or manifest['policy'] != 'all_cad_visuals_grouped_v1'
                or manifest['urdf_sha256'] != hashlib.sha256(path.read_bytes()).hexdigest()):
            raise ValueError('URDF changed after collision mesh generation')
        for relative, expected in manifest['mesh_sha256'].items():
            mesh = (path.parent / relative).resolve()
            if not mesh.is_relative_to(path.parent.parent):
                raise ValueError('Collision source outside robot package')
            if hashlib.sha256(mesh.read_bytes()).hexdigest() != expected:
                raise ValueError('CAD/collision mesh changed: ' + relative)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('末端碰撞模型校验失败，请运行 scripts/rebuild_tianji_tool_collision.py 重新生成：' + str(exc)) from exc


def load_tool_volumes(path, wrist_link):
    """Return separate collision envelopes in the URDF wrist-link frame.

    Fixed mounting parts may touch their parent wrist. Moving fingers are not
    covered by that adjacency exemption. No tool/arm collision margin is relaxed.
    """
    path = Path(path).resolve()
    root = ET.parse(path).getroot()
    _verify_generated_assets(path, root)
    links = {link.get('name'): link for link in root.findall('link')}
    joints = {joint.get('name'): joint for joint in root.findall('joint')}
    if (len(links) != len(root.findall('link')) or len(joints) != len(root.findall('joint'))
            or wrist_link not in links):
        raise ValueError('Invalid URDF tool link/joint names')
    children, parents = {}, set()
    for joint in joints.values():
        parent, child = joint.find('parent'), joint.find('child')
        if parent is None or child is None:
            raise ValueError('Missing URDF joint parent/child')
        parent, child = parent.get('link'), child.get('link')
        if parent not in links or child not in links or child in parents:
            raise ValueError('Invalid URDF joint tree')
        parents.add(child)
        children.setdefault(parent, []).append(joint)

    def limits(joint, seen=()):
        name = joint.get('name')
        if name in seen:
            raise ValueError('Cyclic URDF mimic joint')
        kind = joint.get('type')
        if kind == 'continuous':
            lower, upper = -math.pi, math.pi
        elif kind in ('revolute', 'prismatic'):
            limit = joint.find('limit')
            if limit is None:
                raise ValueError('Missing URDF tool joint limits: ' + name)
            lower, upper = float(limit.get('lower', 'nan')), float(limit.get('upper', 'nan'))
        else:
            raise ValueError('Unsupported moving URDF tool joint: ' + str(kind))
        if not np.isfinite([lower, upper]).all() or lower > upper:
            raise ValueError('Invalid URDF tool joint limits: ' + name)
        mimic = joint.find('mimic')
        if mimic is not None:
            source = joints.get(mimic.get('joint'))
            if source is None:
                raise ValueError('Missing URDF mimic source: ' + name)
            multiplier, offset = float(mimic.get('multiplier', '1')), float(mimic.get('offset', '0'))
            mapped = np.array(limits(source, (*seen, name))) * multiplier + offset
            lo, hi = float(mapped.min()), float(mapped.max())
            if not np.isfinite(mapped).all() or lo < lower - 1e-9 or hi > upper + 1e-9:
                raise ValueError('URDF mimic range exceeds joint limits: ' + name)
            lower, upper = lo, hi
        return lower, upper

    volumes, seen, visual_count = [], {wrist_link}, 0
    pending = [(joint.find('child').get('link'), [joint]) for joint in children.get(wrist_link, [])]
    while pending:
        name, chain = pending.pop()
        if name in seen:
            raise ValueError('Cyclic URDF tool tree')
        seen.add(name)
        link = links[name]
        visual_count += len(link.findall('visual'))
        for index, collision in enumerate(link.findall('collision')):
            vertices = _geometry(collision.find('geometry'), path)
            frame = _origin(collision.find('origin'))
            vertices = vertices @ frame[:3, :3].T + frame[:3, 3]
            moving = False
            for joint in reversed(chain):
                kind = joint.get('type')
                if kind != 'fixed':
                    moving = True
                    lower, upper = limits(joint)
                    axis_node = joint.find('axis')
                    axis = _vector('1 0 0' if axis_node is None else axis_node.get('xyz', '1 0 0'))
                    norm = np.linalg.norm(axis)
                    if norm < 1e-12:
                        raise ValueError('Invalid URDF tool joint axis')
                    axis /= norm
                    if kind == 'prismatic':
                        vertices = np.concatenate((vertices + lower * axis, vertices + upper * axis))
                    else:
                        vertices = _rotate_envelope(vertices, axis, lower, upper)
                frame = _origin(joint.find('origin'))
                vertices = vertices @ frame[:3, :3].T + frame[:3, 3]
            low, high = vertices.min(axis=0), vertices.max(axis=0)
            if not np.isfinite(vertices).all() or np.max(np.abs(vertices)) > 1:
                raise ValueError('URDF tool collision envelope exceeds one metre')
            volumes.append(ToolVolume(name + '/' + collision.get('name', str(index)),
                                      (low + high) / 2, (high - low) / 2, moving))
        pending.extend((joint.find('child').get('link'), chain + [joint])
                       for joint in children.get(name, []))
    if visual_count and not volumes:
        raise ValueError('URDF has a visible tool but no tool collision geometry')
    return tuple(volumes)
