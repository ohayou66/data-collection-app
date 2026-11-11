"""Match actual CAD hole loops at both mounting interfaces, without robot IO."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'teleop_control/vendor/tianji/teleop'))
from marvin_teleop.geometry import transform


def stl_triangles(path):
    raw = path.read_bytes()
    count = int.from_bytes(raw[80:84], 'little')
    dtype = np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attribute', '<u2')])
    assert len(raw) == 84 + count * dtype.itemsize
    return np.frombuffer(raw, dtype=dtype, offset=84)['vertices'].astype(float)


def hole_centers(triangles, z, pitch_radius_mm, bore_radius_mm):
    """Fit closed boundary loops on an interface plane; dimensions are mm."""
    planar = triangles[np.all(abs(triangles[:, :, 2] - z) < 1e-7, axis=1)]
    points, faces = np.unique(planar.reshape(-1, 3).round(7), axis=0, return_inverse=True)
    faces = faces.reshape(-1, 3)
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    edges, counts = np.unique(edges, axis=0, return_counts=True)
    adjacent = {}
    for a, b in edges[counts == 1]:
        adjacent.setdefault(a, set()).add(b)
        adjacent.setdefault(b, set()).add(a)
    seen, centers = set(), []
    for start in adjacent:
        if start in seen:
            continue
        component, pending = set(), [start]
        while pending:
            vertex = pending.pop()
            if vertex in component:
                continue
            component.add(vertex)
            pending.extend(adjacent[vertex] - component)
        seen.update(component)
        if len(component) < 12 or any(len(adjacent[v]) != 2 for v in component):
            continue
        xy = points[list(component), :2] * 1000
        fit = np.linalg.lstsq(np.column_stack([2 * xy, np.ones(len(xy))]), (xy**2).sum(axis=1), rcond=None)[0]
        center = fit[:2]
        radius = np.sqrt(max(0, fit[2] + center @ center))
        error = np.max(abs(np.linalg.norm(xy - center, axis=1) - radius))
        if (abs(np.linalg.norm(center) - pitch_radius_mm) < .03
                and abs(radius - bore_radius_mm) < .03 and error < .03):
            centers.append([*center / 1000, z])
    assert len(centers) == 4, centers
    return np.asarray(centers)


def matching_error(a, b):
    return np.linalg.norm(a[:, None] - b[None, :], axis=2).min(axis=1).max()


@pytest.mark.parametrize('side,letter', [('left', 'L'), ('right', 'R')])
def test_updated_flange_holes_match_robot_and_gripper(side, letter):
    mesh_dir, = (ROOT / 'teleop_control/vendor/tianji').glob(f'*M6-S-{letter}-*/meshes')
    model = json.loads((ROOT / 'public/tianji-model.json').read_text())
    joints = {j['name']: j for j in model['joints']}
    flange = joints[f'flange_fixed_{letter}']
    frame = transform(flange['xyz'], flange['rpy'])
    wrist = stl_triangles(mesh_dir / f'Link7_{letter}.STL')
    wrist_in_flange = (wrist - frame[:3, 3]) @ frame[:3, :3]
    robot_holes = hole_centers(wrist_in_flange, 0, 25, 2.6)
    adapter = stl_triangles(mesh_dir / 'gripper/part_53.stl')
    bottom_holes = hole_centers(adapter, 0, 25, 3.3)
    top_holes = hole_centers(adapter, .0527, 19, 1.65)
    motor = stl_triangles(mesh_dir / 'gripper/part_27.stl')
    motor_holes = hole_centers(motor, .0527, 19, 1.35)
    assert matching_error(top_holes, motor_holes) < 3e-5

    mount = joints[f'gripper_mount_{letter}']
    frame = transform(mount['xyz'], mount['rpy'])
    actual = bottom_holes @ frame[:3, :3].T + frame[:3, 3]
    assert matching_error(actual, robot_holes) < 3e-5
    # The former mounting angle must fail this geometric check, even though
    # both versions have the same envelope and TCP position.
    old = transform([0, 0, 0], [0, 0, -np.pi / 4 if side == 'left' else 3 * np.pi / 4])
    assert matching_error(bottom_holes @ old[:3, :3].T, robot_holes) > .01

    key = 'm54' if side == 'left' else 'm116'
    mesh = model['meshes'][key]
    np.testing.assert_allclose(np.asarray(mesh['vertices'])[mesh['faces']], adapter, atol=1e-10)
