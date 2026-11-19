"""UMI finalization and platform handoff share the App capture directory."""
import json
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'teleop_control/src'))
from teleop_control.collection_uploader import CollectionUploader, READY_MARKER, UPLOADED_MARKER
from teleop_control.platform_auth import PlatformBearerAuth, PlatformLogin, PlatformTokenStore
from teleop_control.upload_targets import UploadTargets
from test_umi_background_finalizer import finalize_episode, job


def test_umi_finalized_round_registration_reuses_id_and_keeps_capture(tmp_path):
    capture = tmp_path / 'data'
    bags = capture / 'umi/rosbags'
    bags.mkdir(parents=True)
    api = 'http://127.0.0.1:8000'
    store = PlatformTokenStore(tmp_path / 'session')
    store.write(token='fixture', expires_in=3600, user={'username': 'operator-001'})
    targets = UploadTargets(tmp_path, PlatformLogin(api, store), api, local_directory_import=True)
    requests = []
    def handle(request):
        assert (request.method, request.url.path) == ('POST', '/uploads/local-episodes')
        assert request.headers['Authorization'] == 'Bearer fixture'
        payload = json.loads(request.content)
        assert payload == {'id': payload['id'], 'source': 'umi', 'directory': 'umi/rosbags/task/001'}
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(400, json={'detail': '尚未支持 UMI'})
        return httpx.Response(201, json={'id': payload['id'], 'status':'registered', 'storage_mode':'local_raw'})

    folder, _ = job(bags)
    pending = folder / '.mp4-pending.json'
    metadata = {**json.loads(pending.read_text()), 'upload_destination': targets.snapshot()}
    pending.write_text(json.dumps(metadata))
    (folder/'meta.json').write_text(json.dumps(metadata))
    with httpx.Client(transport=httpx.MockTransport(handle), auth=PlatformBearerAuth(store)) as client:
        registration = CollectionUploader(bags, api, client=client, targets=targets)
        registration.local_destination = targets.snapshot()
        registration.capture_root = capture
        registration.scan_once()
        assert not requests and not (folder/READY_MARKER).exists()
        finalize_episode(folder)
        manifest = folder/'media/video-manifest.json'
        original = manifest.read_bytes()
        registration.scan_once()
        assert registration.status()['failed'] == 1 and not (folder/UPLOADED_MARKER).exists()
        marker = json.loads((folder/READY_MARKER).read_text())
        assert marker['author'] == 'operator-001' and marker['upload_destination'] == targets.snapshot()
        registration.scan_once()
        registration.scan_once()
        assert len(requests) == 2 and requests[0] == requests[1]
        assert registration.status()['registered'] == 1 and original == manifest.read_bytes()
        assert (folder/'media/signals.mcap').is_file()


@pytest.mark.parametrize('barrier', ['.discarded', '.recovery-pending', '.mp4-converting', 'recording-failure.json', 'raw-only', 'legacy'])
def test_umi_never_enrolls_unfinished_or_unselected_rounds(tmp_path, barrier):
    from teleop_control.umi_queue import local_registration_info
    destination = dict(kind='local', storage_mode='local_raw')
    meta = {'author':'operator','upload_destination':destination}
    if barrier == 'raw-only':
        meta['upload_destination'] = {'kind':'raw-only'}
    elif barrier == 'legacy':
        meta.pop('upload_destination')
    else:
        (tmp_path/barrier).touch()
    (tmp_path/'meta.json').write_text(json.dumps(meta))
    (tmp_path/'metadata.yaml').touch()
    (tmp_path/'bag.mcap').touch()
    assert local_registration_info(tmp_path, destination) is None
    assert not (tmp_path/READY_MARKER).exists()


@pytest.mark.parametrize('mode', ['raw-only', 'local-platform'])
def test_umi_desktop_backend_uses_capture_mount_and_same_account_gate(tmp_path, monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from teleop_control import background_upload, main

    capture = tmp_path / 'app/data'
    monkeypatch.setenv('TELEOP_DATA_ROOT', str(capture))
    monkeypatch.setenv('UMI_DATA_ROOT', str(tmp_path/'previous-state'))
    monkeypatch.setenv('PLATFORM_TOKEN_FILE', str(tmp_path/'token'))
    monkeypatch.setenv('DATA_COLLECTION_GATE_FILE', str(tmp_path/'unused'))
    monkeypatch.setenv('DATA_COLLECTION_STORAGE_MODE', mode)
    monkeypatch.setattr(sys, 'argv', ['collector', '--mock'])
    config = {}
    def create(_, **kwargs):
        config.update(kwargs)
        tianji, kuavo = Mock(), Mock()
        tianji.collection.saved_output = capture/'tianji'
        kuavo.collection.output = capture/'kuavo'
        return SimpleNamespace(state=SimpleNamespace(tianji_manager=tianji, kuavo_manager=kuavo))
    monkeypatch.setattr(main, 'create_app', create)
    monkeypatch.setattr(main, 'build_controller', lambda *a, **kw: Mock())
    monkeypatch.setattr(main, 'build_preview', lambda *a, **kw: None)
    monkeypatch.setattr(background_upload, 'ensure_service', lambda *a, **kw: Mock())
    monkeypatch.setattr(PlatformLogin, 'status', lambda _: {'authenticated':True, 'user':{'username':'collector'}})
    def run(app, **kwargs):
        umi = config['umi']
        assert umi.data_root == capture/'umi' and (umi.data_root/'rosbags').is_dir()
        assert umi.collection_gate_path == umi.data_root/'.collection-platform.json'
        assert umi.upload_targets is config['upload_targets']
        # Stop the asynchronous initial refresh before testing a deterministic lease.
        gate = config['umi_gate']
        gate.stopped.set()
        gate.thread.join()
        gate.refresh()
        lease = json.loads(umi.collection_gate_path.read_text())
        if mode == 'local-platform':
            assert lease['username'] == 'collector' and lease['upload_destination']['storage_mode'] == 'local_raw'
            worker = app.state.local_registrations['umi']
            assert worker.capture_root == capture and worker.output_root == umi.data_root/'rosbags'
        else:
            assert lease['upload_destination'] == {'kind':'raw-only'}
            assert not hasattr(app.state, 'local_registrations')
    monkeypatch.setattr(main.uvicorn, 'run', run)
    main.main()
