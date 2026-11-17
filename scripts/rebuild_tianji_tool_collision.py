"""Rebuild conservative tool collision meshes from every installed CAD visual.

Offline only. The original CAD export remains untouched. Run with --check in CI.
Each rigid group is bounded in its URDF link frame; the runtime analytically
sweeps the three moving groups over their full joint limits (including mimic).
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from itertools import product

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'teleop_control/vendor/tianji/teleop'))
from marvin_teleop.model import mesh_vertices, origin

GROUPS = {
    'housing': {0, 2, 3, 4, 5, 6, 20, 51},
    'camera_support': set(range(7, 17)),
    'motor': set(range(22, 49)),
    'adapter': {53},
    'jaw_1': {1, 18, 49},
    'jaw_17': {17, 19, 50},
    'shaft': {21, 52},
}


def box_stl(low, high):
    points = np.array(list(product(*zip(low, high))))
    # Outward-facing, closed triangulated box, in metres.
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
             (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    rows = ['solid cad_conservative_bound']
    for a, b, c, d in faces:
        for tri in ((a, b, c), (a, c, d)):
            v = points[list(tri)]
            normal = np.cross(v[1]-v[0], v[2]-v[0])
            normal /= np.linalg.norm(normal)
            rows += ['facet normal ' + ' '.join(f'{x:.12g}' for x in normal), 'outer loop']
            rows += ['vertex ' + ' '.join(f'{x:.12f}' for x in row) for row in v]
            rows += ['endloop', 'endfacet']
    return ('\n'.join(rows) + '\nendsolid cad_conservative_bound\n').encode()


def build(path):
    tree = ET.parse(path)
    root = tree.getroot()
    letter = 'L' if 'left' in path.name else 'R'
    source_manifest = path.parent.parent/'meshes/gripper/manifest.json'
    source = json.loads(source_manifest.read_text())
    parts = {p['mesh']: p for p in source['parts']}
    groups = {name: [] for name in GROUPS}
    hashes = {}
    seen = set()
    links = {}
    for link in root.findall('link'):
        name = link.get('name')
        if not name.startswith('gripper_'):
            continue
        links[name] = link
        for visual in link.findall('visual'):
            mesh = visual.find('geometry/mesh')
            if mesh is None:
                raise ValueError('Unexpected non-mesh CAD visual: ' + name)
            filename = mesh.get('filename')
            part = parts[Path(filename).name]
            index = part['index']
            if index in seen:
                raise ValueError('Duplicate CAD part: ' + filename)
            seen.add(index)
            matches = [g for g, ids in GROUPS.items() if index in ids]
            if len(matches) != 1:
                raise ValueError('CAD part has no unique collision group: ' + filename)
            file = (path.parent/filename).resolve()
            hashes[filename] = hashlib.sha256(file.read_bytes()).hexdigest()
            v = mesh_vertices(file) * np.fromstring(mesh.get('scale', '1 1 1'), sep=' ')
            t = origin(visual.find('origin'))
            v = v @ t[:3, :3].T + t[:3, 3]
            if not len(v) or not np.isfinite(v).all():
                raise ValueError('Invalid CAD vertices: ' + filename)
            groups[matches[0]].append((name, part, v))
        for collision in list(link.findall('collision')):
            link.remove(collision)
    if seen != {p['index'] for p in parts.values()} or seen != set(range(54)):
        raise ValueError('URDF and CAD manifest must contain all 54 parts exactly once')
    files, report = {}, []
    for group, items in groups.items():
        names = {x[0] for x in items}
        if len(names) != 1:
            raise ValueError('Cannot merge different moving links: ' + group)
        name = names.pop()
        v = np.concatenate([x[2] for x in items])
        # One micrometre numerical padding; physical reserve remains 15 mm.
        low, high = v.min(axis=0)-1e-6, v.max(axis=0)+1e-6
        meshfile = f'../meshes/gripper/collision/{group}.stl'
        content = box_stl(low, high)
        files[(path.parent/meshfile).resolve()] = content
        hashes[meshfile] = hashlib.sha256(content).hexdigest()
        collision = ET.SubElement(links[name], 'collision', name=f'cad_{group}_{letter}')
        ET.SubElement(collision, 'origin', xyz='0 0 0', rpy='0 0 0')
        geometry = ET.SubElement(collision, 'geometry')
        ET.SubElement(geometry, 'mesh', filename=meshfile)
        report.append(dict(group=group, link=name, collision=collision.get('name'),
                           parts=[dict(index=p['index'], mesh=p['mesh'], instance=p['instance']) for _, p, _ in items],
                           low_m=low.tolist(), high_m=high.tolist(), triangles=12))
    manifest_name = path.stem + '.collision.json'
    root.set('tool_collision_manifest', manifest_name)
    ET.indent(tree, space='  ')
    urdf_bytes = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    files[path.resolve()] = urdf_bytes
    manifest = dict(schema=1, policy='all_cad_visuals_grouped_v1', part_count=len(seen),
                    cad_source=source['source'], cad_source_sha256=source['source_sha256'],
                    source_manifest_sha256=hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
                    urdf_sha256=hashlib.sha256(urdf_bytes).hexdigest(), mesh_sha256=hashes,
                    numerical_padding_m=1e-6, groups=report)
    files[path.with_name(manifest_name).resolve()] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for side, letter in (('left', 'L'), ('right', 'R')):
        path = ROOT/f'teleop_control/vendor/tianji/Marvin M6-S-{letter}-CCS-696-V4.0 urdf (FUSION)/urdf/marvin_{side}_with_gripper.urdf'
        for file, data in build(path).items():
            if args.check:
                if not file.is_file() or file.read_bytes() != data:
                    raise SystemExit('Stale generated collision asset: ' + str(file))
            else:
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
        print(side + ': 54 CAD parts covered by 7 meshes (4 fixed, 3 moving)')


if __name__ == '__main__':
    main()
