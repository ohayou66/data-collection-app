#!/usr/bin/env python3
"""Rebuild the supplied Tianji flange display assets; no robot or backend IO.

The part frame remains robot face z=0, gripper face z=52.7 mm. The changed
robot-side hole pattern requires the confirmed left -45 / right +45-degree correction
in the active URDFs. Keep m54/m116 identities, which Kuavo explicitly excludes.
"""
import hashlib
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np

from build_kuavo_flange import display_mesh, streams

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'teleop_control/assets/tianji/flange'


def write_json(path, value, *, compact=False):
    path.write_text(json.dumps(value, ensure_ascii=False,
                              **({'separators': (',', ':')} if compact else {'indent': 2})) + '\n')


def build():
    source = ASSETS / 'motor_adapter.SLDPRT'
    raw = source.read_bytes()
    content = streams(raw, display_version=14000)
    mesh, bounds = display_mesh(content['Contents/DisplayLists'], expected_faces=56)
    # A different envelope needs a fresh assembly review, not automatic fitting.
    np.testing.assert_allclose(bounds, [[-.0375, -.0375, 0], [.0375, .0375, .0527]], atol=1e-9, rtol=0)
    triangles = np.asarray(mesh['vertices'])[np.asarray(mesh['faces'])]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    assert np.all(lengths > 1e-16), 'Degenerate flange triangles'
    normals /= lengths[:, None]
    stl = bytearray(b'Tianji flange saved CAD display tessellation; units=m'.ljust(80, b'\0'))
    stl.extend(struct.pack('<I', len(triangles)))
    for normal, triangle in zip(normals, triangles):
        stl.extend(struct.pack('<12fH', *normal, *triangle.reshape(-1), 0))

    source_info = dict(source=str(source.relative_to(ROOT)), original_filename='电机_天机电机连接法兰.SLDPRT',
                       source_sha256=hashlib.sha256(raw).hexdigest())
    model_path = ROOT / 'public/tianji-model.json'
    model = json.loads(model_path.read_text())
    manifests = sorted((ROOT / 'teleop_control/vendor/tianji').glob('*/meshes/gripper/manifest.json'))
    assert len(manifests) == 2
    mounts = {}
    for side, letter in [('left', 'L'), ('right', 'R')]:
        path, = (ROOT / 'teleop_control/vendor/tianji').glob(f'*/urdf/marvin_{side}_with_gripper.urdf')
        origin = ET.parse(path).find(f"joint[@name='gripper_mount_{letter}']/origin")
        mounts[side] = dict(urdf=str(path.relative_to(ROOT)),
                           xyz_m=[float(v) for v in origin.get('xyz').split()],
                           rpy_deg=np.degrees([float(v) for v in origin.get('rpy').split()]).tolist())
    for letter, key in [('L', 'm54'), ('R', 'm116')]:
        link = next(link for link in model['links'] if link['name'] == f'gripper_{letter}')
        visual = next(v for v in link['visuals'] if v['mesh'] == key)
        assert visual['xyz'] == visual['rpy'] == [0, 0, 0] and visual['scale'] == [1, 1, 1]
        model['meshes'][key] = mesh
    for path in manifests:
        manifest = json.loads(path.read_text())
        side = 'left' if 'M6-S-L-' in str(path) else 'right'
        manifest['urdf_registration']['mount_rpy_deg'] = mounts[side]['rpy_deg']
        part = next(p for p in manifest['parts'] if p['mesh'] == 'part_53.stl')
        np.testing.assert_allclose(part['flange_from_part'], np.eye(4), atol=1e-12)
        part.update(source_info, bounds_m=bounds.tolist())
        for field in ('original_triangles', 'visual_triangles'):
            manifest[field] += len(triangles) - part[field]
            part[field] = len(triangles)
        edits = manifest.setdefault('geometry_edits', [])
        edits[:] = [edit for edit in edits if edit.get('mesh') != 'part_53.stl']
        edits.append(dict(source_info, mesh='part_53.stl', action='replace flange with updated standalone CAD display mesh',
                          assembly_pose=f'Original part frame; gripper_mount rotated {"-45" if side == "left" else "+45"} degrees about flange Z from the previous adapter mounting'))
        (path.parent / part['mesh']).write_bytes(stl)
        write_json(path, manifest)

    target = ASSETS / 'display-mesh.json'
    write_json(target, mesh, compact=True)
    (ASSETS / 'preview.png').write_bytes(content['PreviewPNG'])
    write_json(ASSETS / 'manifest.json', dict(source_info,
        display_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        stl_sha256=hashlib.sha256(stl).hexdigest(), units='m', bounds_m=bounds.tolist(),
        dimensions_mm=((bounds[1] - bounds[0]) * 1000).round(6).tolist(),
        vertices=len(mesh['vertices']), triangles=len(triangles), saved_faces=56, display_version=14000,
        preview_meshes=dict(left='m54', right='m116'),
        assembly=dict(robot_face_z_mm=0, gripper_face_z_mm=52.7,
                      robot_hole_centers_xy_mm=[[x, y] for x in (-17.67766953, 17.67766953) for y in (-17.67766953, 17.67766953)],
                      gripper_hole_centers_xy_mm=[[19, 0], [0, 19], [-19, 0], [0, -19]],
                      confirmed_rotation='Left counterclockwise 45 degrees; right clockwise 45 degrees; viewed from robot towards gripper along flange +Z',
                      delta_rpy_deg=dict(left=[0, 0, -45], right=[0, 0, 45]), mounts=mounts,
                      tcp='Position unchanged; flange-to-TCP orientation follows the corrected gripper mount.')))
    write_json(model_path, model, compact=True)
    print(f'Updated both Tianji flanges: {len(triangles)} triangles each; 75 x 75 x 52.7 mm')


if __name__ == '__main__':
    build()
