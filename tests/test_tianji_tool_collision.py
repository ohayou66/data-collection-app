"""URDF end-effector geometry and recovery checks; no hardware connections."""
import xml.etree.ElementTree as ET
import json
from pathlib import Path

import numpy as np
import pytest

from marvin_teleop.geometry import rotation
from marvin_teleop.model import Models, StaticMesh, mesh_vertices, origin
from marvin_teleop.recovery import ZeroRecovery
from marvin_teleop.recovery_clearance import RecoveryClearance
from marvin_teleop.urdf_collision import load_tool_volumes
from test_tianji_zero_recovery import models, rig  # Fake SDK, real kinematics.


def write_tool(path, joint_type='revolute', limits='lower="0" upper="3.141592653589793"',
               geometry='<box size="0.002 0.002 0.002"/>'):
    path.write_text(f'''<robot name="test"><link name="wrist"/>
      <link name="finger"><collision name="tip"><origin xyz="0.1 0 0"/>
      <geometry>{geometry}</geometry></collision></link>
      <joint name="jaw" type="{joint_type}"><parent link="wrist"/><child link="finger"/>
      <axis xyz="0 0 1"/><limit {limits}/></joint></robot>''')


def test_swept_volume_covers_interior_extrema_not_only_open_closed(tmp_path):
    path = tmp_path/'tool.urdf'
    write_tool(path)
    volume, = load_tool_volumes(path, 'wrist')
    assert volume.moving
    assert (volume.center + volume.half)[1] > .1
    assert (volume.center - volume.half)[0] <= -.101
    for angle in np.linspace(0, np.pi, 101):
        point = rotation([0, 0, 1], angle) @ [.101, .001, .001]
        assert np.all(np.abs(point - volume.center) <= volume.half + 1e-12)


@pytest.mark.parametrize('geometry,limits,joint_type', [
    ('<mesh filename="missing.stl"/>', 'lower="0" upper="1"', 'revolute'),
    ('<box size="0.1 0.1 0.1"/>', 'lower="nan" upper="1"', 'revolute'),
    ('<box size="0.1 0.1 0.1"/>', 'lower="0" upper="1"', 'floating'),
    ('<unsupported/>', 'lower="0" upper="1"', 'fixed'),
])
def test_bad_tool_geometry_fails_loading_instead_of_silently_disabling(tmp_path, geometry, limits, joint_type):
    path = tmp_path/'tool.urdf'
    write_tool(path, geometry=geometry, limits=limits, joint_type=joint_type)
    with pytest.raises((ValueError, OSError)):
        load_tool_volumes(path, 'wrist')


def test_visible_tool_without_collision_geometry_is_rejected(tmp_path):
    path = tmp_path/'tool.urdf'
    write_tool(path)
    path.write_text(path.read_text().replace('<collision', '<visual').replace('</collision>', '</visual>'))
    with pytest.raises(ValueError, match='no tool collision'):
        load_tool_volumes(path, 'wrist')


def test_mount_and_collision_origins_are_both_applied(tmp_path):
    path = tmp_path/'tool.urdf'
    write_tool(path, joint_type='fixed')
    tree = ET.parse(path)
    ET.SubElement(tree.find('joint'), 'origin', xyz='0.02 0.03 0.04', rpy='0 0 1.5707963267948966')
    tree.write(path)
    volume, = load_tool_volumes(path, 'wrist')
    np.testing.assert_allclose(volume.center, [.02, .13, .04], atol=1e-12)
    assert not volume.moving


def test_relative_mesh_path_and_units_are_preserved(tmp_path):
    mesh_dir = tmp_path/'meshes'
    mesh_dir.mkdir()
    (mesh_dir/'tip.stl').write_text('solid tip\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 20 0\nendsolid tip\n')
    urdf_dir = tmp_path/'urdf'
    urdf_dir.mkdir()
    path = urdf_dir/'tool.urdf'
    write_tool(path, joint_type='fixed', geometry='<mesh filename="../meshes/tip.stl" scale="0.001 0.001 0.001"/>')
    volume, = load_tool_volumes(path, 'wrist')
    np.testing.assert_allclose(volume.center, [.105, .01, 0], atol=1e-12)
    np.testing.assert_allclose(volume.half, [.005, .01, 0], atol=1e-12)


@pytest.mark.parametrize('source', ['missing', 'jaw'])
def test_invalid_mimic_source_is_rejected(tmp_path, source):
    path = tmp_path/'tool.urdf'
    write_tool(path)
    tree = ET.parse(path)
    ET.SubElement(tree.find('joint'), 'mimic', joint=source)
    tree.write(path)
    with pytest.raises(ValueError, match='mimic'):
        load_tool_volumes(path, 'wrist')


@pytest.mark.parametrize('side', ['left', 'right'])
def test_all_installed_collisions_and_mimic_motion_are_inside_envelopes(models, side):
    arm = models.arms[side]
    tree = ET.parse(arm.path)
    volumes = {v.name: v for v in arm.tool_volumes}
    assert len(volumes) == 7 and sum(v.moving for v in volumes.values()) == 3
    assert models.mapping_report['tool_collision'][side]['volumes'] == [v.name for v in arm.tool_volumes]
    letter = 'L' if side == 'left' else 'R'
    joints = {j.get('name'): j for j in tree.findall('joint')}
    parents = {j.find('child').get('link'): j for j in joints.values()}
    drive = joints['gripper_drive_' + letter]
    maximum = float(drive.find('limit').get('upper'))
    for amount in np.linspace(0, maximum, 11):
        def joint_angle(joint):
            mimic = joint.find('mimic')
            if mimic is not None:
                return joint_angle(joints[mimic.get('joint')]) * float(mimic.get('multiplier', '1')) + float(mimic.get('offset', '0'))
            return amount
        for name, volume in volumes.items():
            link_name, collision_name = name.split('/')
            collision = tree.find(f"link[@name='{link_name}']/collision[@name='{collision_name}']")
            mesh = collision.find('geometry/mesh')
            vertices = mesh_vertices(arm.path.parent/mesh.get('filename'))
            vertices *= np.fromstring(mesh.get('scale', '1 1 1'), sep=' ')
            frame = origin(collision.find('origin'))
            link = link_name
            while link != 'Link7_' + letter:
                joint = parents[link]
                motion = np.eye(4)
                if joint.get('type') != 'fixed':
                    motion[:3, :3] = rotation(np.fromstring(joint.find('axis').get('xyz'), sep=' '), joint_angle(joint))
                frame = origin(joint.find('origin')) @ motion @ frame
                link = joint.find('parent').get('link')
            actual = vertices @ frame[:3, :3].T + frame[:3, 3]
            assert np.all(np.abs(actual - volume.center) <= volume.half + 1e-10), name
    zero = {s: np.zeros(7) for s in models.arms}
    assert models.collision_reason(zero) is None


def finger_obstacle(models, side, joints):
    arm = models.arms[side]
    volume = next(v for v in arm.tool_volumes if '/cad_jaw_1_' in v.name)
    frame = arm.chain(joints[side])[-1]
    point = frame[:3, :3] @ volume.center + frame[:3, 3]
    return StaticMesh(np.array([[point + [-.002, -.002, 0],
                                 point + [.002, -.002, 0], point + [0, .002, 0]]]))


def test_recovery_preflight_blocks_tool_only_midpath_collision_before_enable(rig, monkeypatch):
    model = rig.models
    monkeypatch.setattr(model, 'collision_reason', Models.collision_reason.__get__(model))
    for q in rig.q:
        q[:] = 0
    rig.q[0][1] = -40
    start = dict(zip(('left', 'right'), rig.q))
    middle = {s: q.copy() for s, q in start.items()}
    middle['left'][1] = -20
    zero = {s: np.zeros(7) for s in start}
    monkeypatch.setattr(model, 'obstacles', model.obstacles + [finger_obstacle(model, 'left', middle)])
    assert model.collision_reason(start) is None
    assert model.collision_reason(zero) is None
    assert 'tool gripper_' in model.collision_reason(middle)
    with monkeypatch.context() as bare:
        for arm in model.arms.values():
            bare.setattr(arm, 'tool_volumes', ())
        assert model.collision_reason(middle) is None
    recovery = ZeroRecovery(rig.robot, model, rig.config, ('left',), rig.clock[0])
    with pytest.raises(ValueError, match='tool gripper_'):
        rig.run(recovery)
    assert recovery.phase == 'validate'
    assert not any(event[0] == 'state' and event[2] == 1 for event in rig.events)
    assert not recovery.done


@pytest.mark.parametrize('side', ['left', 'right'])
def test_recovery_live_check_stops_before_sending_into_tool_obstacle(rig, monkeypatch, side):
    model = rig.models
    monkeypatch.setattr(model, 'collision_reason', Models.collision_reason.__get__(model))
    index = ('left', 'right').index(side)
    for q in rig.q:
        q[:] = 0
    rig.q[index][1] = -2
    recovery = ZeroRecovery(rig.robot, model, rig.config, (side,), rig.clock[0])
    for _ in range(100):
        rig.clock[0] += .01
        recovery.tick(rig.clock[0])
        if recovery.phase == 'moving':
            break
    assert recovery.phase == 'moving'
    joints = dict(zip(('left', 'right'), rig.q))
    monkeypatch.setattr(model, 'obstacles', model.obstacles + [finger_obstacle(model, side, joints)])
    before = list(rig.events)
    with pytest.raises(ValueError, match='tool gripper_'):
        recovery.tick(rig.clock[0] + .01)
    assert rig.events == before  # The worker handles the exception by stopping.
    assert not recovery.done


def test_recovery_clearance_exception_never_exempts_tools(models, monkeypatch):
    joints = {s: np.zeros(7) for s in models.arms}
    monkeypatch.setattr(models, 'obstacles', models.obstacles + [finger_obstacle(models, 'left', joints)])
    guard = RecoveryClearance(models, joints, .015)
    assert not guard.floors
    assert 'tool gripper_' in guard.reason(joints)


@pytest.mark.parametrize('side', ['left', 'right'])
def test_every_cad_visual_vertex_is_inside_its_generated_collision_mesh(models, side):
    """Check original CAD vertices, not just the already-reduced collision mesh."""
    arm = models.arms[side]
    tree = ET.parse(arm.path)
    manifest = json.loads(arm.path.with_name(tree.getroot().get('tool_collision_manifest')).read_text())
    seen = set()
    for group in manifest['groups']:
        link = tree.find(f"link[@name='{group['link']}']")
        collision = link.find(f"collision[@name='{group['collision']}']")
        bound = mesh_vertices(arm.path.parent / collision.find('geometry/mesh').get('filename'))
        low, high = bound.min(axis=0), bound.max(axis=0)
        for part in group['parts']:
            matching = [v for v in link.findall('visual') if Path(v.find('geometry/mesh').get('filename')).name == part['mesh']]
            assert len(matching) == 1
            visual = matching[0]
            mesh = visual.find('geometry/mesh')
            vertices = mesh_vertices(arm.path.parent / mesh.get('filename'))
            vertices *= np.fromstring(mesh.get('scale', '1 1 1'), sep=' ')
            frame = origin(visual.find('origin'))
            vertices = vertices @ frame[:3, :3].T + frame[:3, 3]
            assert np.all(vertices >= low-1e-10) and np.all(vertices <= high+1e-10), part['instance']
            assert part['index'] not in seen
            seen.add(part['index'])
    visual_count = sum(len(link.findall('visual')) for link in tree.findall('link') if link.get('name').startswith('gripper_'))
    assert seen == set(range(54)) and visual_count == manifest['part_count'] == 54
    camera = next(g for g in manifest['groups'] if g['group'] == 'camera_support')
    assert {7, 8} <= {p['index'] for p in camera['parts']}


@pytest.mark.parametrize('modified', ['urdf', 'source', 'collision'])
def test_changed_generated_assets_fail_closed(models, monkeypatch, modified):
    arm = models.arms['left']
    target = {'urdf': arm.path, 'source': arm.path.parent/'../meshes/gripper/part_08.stl',
              'collision': arm.path.parent/'../meshes/gripper/collision/camera_support.stl'}[modified].resolve()
    original = Path.read_bytes
    def changed(path):
        data = original(path)
        return data+b'changed' if path.resolve() == target else data
    monkeypatch.setattr(Path, 'read_bytes', changed)
    with pytest.raises(ValueError, match='末端碰撞模型校验失败'):
        load_tool_volumes(arm.path, 'Link7_L')


def test_reexported_installed_urdf_cannot_drop_coverage_manifest(tmp_path):
    path = tmp_path/'marvin_left_with_gripper.urdf'
    write_tool(path, joint_type='fixed')
    with pytest.raises(ValueError, match='缺少 CAD 覆盖清单'):
        load_tool_volumes(path, 'wrist')


def camera_obstacle(models, side, joints):
    """Place a thin obstacle on a real camera vertex outside all other tool boxes."""
    arm = models.arms[side]
    letter = side[0].upper()
    tree = ET.parse(arm.path)
    visual = tree.find(f".//visual[@name='g{letter}_08']")
    pts = np.unique(mesh_vertices(arm.path.parent/visual.find('geometry/mesh').get('filename')), axis=0)
    frame = origin(visual.find('origin'))
    link = 'gripper_' + letter
    parents = {j.find('child').get('link'): j for j in tree.findall('joint')}
    while link != 'Link7_' + letter:
        joint = parents[link]
        frame = origin(joint.find('origin')) @ frame
        link = joint.find('parent').get('link')
    pts = pts @ frame[:3, :3].T + frame[:3, 3]
    other = [v for v in arm.tool_volumes if 'camera_support' not in v.name]
    gap = np.min([np.max(abs(pts-v.center)-v.half, axis=1) for v in other], axis=0)
    assert gap.max() > .02
    frame = arm.chain(joints[side])[-1]
    point = frame[:3, :3] @ pts[np.argmax(gap)] + frame[:3, 3]
    return StaticMesh(np.array([[point+[-.001, -.001, 0], point+[.001, -.001, 0], point+[0, .001, 0]]]))


@pytest.mark.parametrize('side', ['left', 'right'])
def test_camera_only_midpath_collision_blocks_recovery_before_enable(rig, monkeypatch, side):
    model = rig.models
    monkeypatch.setattr(model, 'collision_reason', Models.collision_reason.__get__(model))
    for q in rig.q:
        q[:] = 0
    rig.q[('left', 'right').index(side)][1] = -40
    start = dict(zip(('left', 'right'), rig.q))
    middle = {s: q.copy() for s, q in start.items()}
    middle[side][1] = -20
    zero = {s: np.zeros(7) for s in start}
    monkeypatch.setattr(model, 'obstacles', model.obstacles + [camera_obstacle(model, side, middle)])
    assert model.collision_reason(start) is None
    assert model.collision_reason(zero) is None
    assert 'cad_camera_support_' in model.collision_reason(middle)
    with monkeypatch.context() as missing:
        arm = model.arms[side]
        missing.setattr(arm, 'tool_volumes', tuple(v for v in arm.tool_volumes if 'camera_support' not in v.name))
        assert model.collision_reason(middle) is None
    guard = RecoveryClearance(model, middle, .015)
    assert 'cad_camera_support_' in guard.reason(middle)
    recovery = ZeroRecovery(rig.robot, model, rig.config, (side,), rig.clock[0])
    with pytest.raises(ValueError, match='cad_camera_support_'):
        rig.run(recovery)
    assert recovery.phase == 'validate'
    assert not any(e[0] == 'state' and e[2] == 1 for e in rig.events)


@pytest.mark.parametrize('side', ['left', 'right'])
def test_camera_live_check_stops_before_command(rig, monkeypatch, side):
    model = rig.models
    monkeypatch.setattr(model, 'collision_reason', Models.collision_reason.__get__(model))
    for q in rig.q:
        q[:] = 0
    rig.q[('left', 'right').index(side)][1] = -2
    recovery = ZeroRecovery(rig.robot, model, rig.config, (side,), rig.clock[0])
    for _ in range(100):
        rig.clock[0] += .01
        recovery.tick(rig.clock[0])
        if recovery.phase == 'moving':
            break
    assert recovery.phase == 'moving'
    q = dict(zip(('left', 'right'), rig.q))
    monkeypatch.setattr(model, 'obstacles', model.obstacles + [camera_obstacle(model, side, q)])
    before = list(rig.events)
    with pytest.raises(ValueError, match='cad_camera_support_'):
        recovery.tick(rig.clock[0]+.01)
    assert rig.events == before
