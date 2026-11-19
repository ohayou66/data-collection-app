"""Local recording must work with zero platform connectivity or upload workers."""
import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'teleop_control/src'))
from teleop_control.raw_storage import RawOnlySession, raw_only_enabled, retry_raw_finalization
from teleop_control.collection_gate import CollectionGate, collection_context, collection_available
from teleop_control.umi_queue import queue_summary


def test_explicit_mode_does_not_change_pc_default(monkeypatch):
    monkeypatch.delenv('DATA_COLLECTION_STORAGE_MODE', raising=False)
    assert not raw_only_enabled()
    monkeypatch.setenv('DATA_COLLECTION_STORAGE_MODE', 'raw-only')
    assert raw_only_enabled()


def test_local_gate_needs_no_platform_and_preserves_owner(tmp_path, monkeypatch):
    session=RawOnlySession()
    gate=CollectionGate(tmp_path/'gate.json',session)
    monkeypatch.setenv('DATA_COLLECTION_GATE_FILE',str(gate.path))
    state=gate.refresh()
    assert state['session_type']=='local' and state['upload_enabled'] is False
    assert collection_available()
    assert collection_context()=={'author':session.username,'upload_destination':{'kind':'raw-only'}}
    with pytest.raises(ValueError): session.select('cloud')


def test_saved_queue_ignores_old_upload_failures_but_tracks_raw_failures(tmp_path):
    ready=tmp_path/'rosbags/task/001';ready.mkdir(parents=True)
    for name,value in [('meta.json',{}),('.upload-status.json',{'state':'failed','message':'old offline'})]:
        (ready/name).write_text(json.dumps(value))
    (ready/'metadata.yaml').write_text('rosbag2_bagfile_information: {}')
    (ready/'raw.mcap').write_bytes(b'dummy')
    pending=ready.with_name('002');pending.mkdir()
    (pending/'.mp4-pending.json').write_text('{}')
    (pending/'recording-failure.json').write_text('{"stage":"mp4"}')
    value=queue_summary(tmp_path,raw_only=True)
    assert value['saved']==1 and value['failed_processing']==1
    assert value['pending']==value['failed']==value['waiting_auth']==0
    assert not value['message'] and not value['upload_enabled']
    assert queue_summary(tmp_path)['pending']==1
    retry_raw_finalization(tmp_path)
    assert not (pending/'recording-failure.json').exists()
    assert (pending/'.mp4-pending.json').exists()
    assert (ready/'raw.mcap').read_bytes()==b'dummy'
    assert queue_summary(tmp_path,raw_only=True)['processing']==1


def test_disabled_worker_never_opens_config_or_upload_client(tmp_path,monkeypatch):
    from teleop_control import background_upload as b
    (tmp_path/'.uploads-disabled').touch()
    b.run(tmp_path/'.background-upload/config.json')
    with pytest.raises(RuntimeError,match='禁用'): b.ensure_service(tmp_path,[])


def test_raw_api_health_auth_and_retry_do_not_use_network(tmp_path,monkeypatch):
    import httpx
    from teleop_control.app import create_app
    from teleop_control.main import MockController
    monkeypatch.setattr(httpx,'AsyncClient',lambda *a,**kw:pytest.fail('platform HTTP forbidden'))
    local=RawOnlySession();umi=Mock(data_root=tmp_path)
    umi.status.return_value={'state':'idle'}
    app=create_app(MockController(),cors_origins=[],umi=umi,platform_login=local,upload_targets=local)
    endpoints={r.path:r.endpoint for r in app.routes if hasattr(r,'path')}
    assert asyncio.run(endpoints['/platform/status']())['upload_mode']=='disabled'
    assert endpoints['/platform/auth']()['session_type']=='local'
    assert asyncio.run(endpoints['/umi/import/scan']())=={'state':'idle'}


def test_main_raw_mode_does_not_construct_uploaders(tmp_path,monkeypatch):
    from teleop_control import main as m
    # main() exports its gate for child workers; restore it after this in-process test.
    monkeypatch.setenv('DATA_COLLECTION_GATE_FILE', str(tmp_path/'unused-gate.json'))
    monkeypatch.setenv('DATA_COLLECTION_STORAGE_MODE','raw-only')
    monkeypatch.setattr(sys,'argv',['collector','--mock','--umi-data-root',str(tmp_path)])
    def forbidden(*a,**kw): pytest.fail('raw mode must not create platform client/uploader')
    for name in ('PlatformLogin','UploadTargets','CollectionUploader'):
        monkeypatch.setattr(m,name,forbidden)
    monkeypatch.setattr(m,'build_controller',lambda *a,**kw:Mock())
    monkeypatch.setattr(m,'build_preview',lambda *a,**kw:None)
    state=SimpleNamespace(tianji_manager=Mock(),kuavo_manager=Mock())
    monkeypatch.setattr(m,'create_app',lambda *a,**kw:SimpleNamespace(state=state))
    monkeypatch.setattr(m.uvicorn,'run',lambda *a,**kw:None)
    m.main()
    assert not (tmp_path/'.background-upload').exists()


def test_qt_local_session_skips_login_and_destination_requests(tmp_path):
    sys.path.insert(0,str(ROOT/'scripts'))
    from PySide6.QtCore import QCoreApplication
    from qt_ui.bridge import Bridge
    app=QCoreApplication.instance() or QCoreApplication([])
    b=Bridge({'DATA_COLLECTION_STORAGE_MODE':'raw-only'},demo=False,settings_path=tmp_path)
    calls=[]
    def request(path,**kw):
        calls.append(path)
        if path=='/storage/status':kw['done'](dict(storage_mode='raw-only',local_session=True,rosbag_path='/data/rosbags'))
    b.request=request
    b.serviceReady()
    assert b.rawOnly and b.state['ready'] and not b.state['authenticated']
    b.enterLocal()
    assert b.state['authenticated'] and b.state['username']=='本地采集'
    assert '/storage/status' in calls
    assert b.state['storagePath']=='/data/rosbags'
    assert not any(p.startswith('/platform/') for p in calls)
    assert not any(p in calls for p in ('/platform/auth/preferences','/platform/auth/login','/platform/destinations'))
    b.shutdown()


def test_raw_launch_does_not_validate_platform_url_or_touch_tokens(tmp_path,monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts'))
    from generate_runtime_config import platform_urls
    import run_app
    config=dict(DATA_COLLECTION_STORAGE_MODE='raw-only',PLATFORM_API_URL='obsolete',PLATFORM_WEB_URL='invalid')
    assert platform_urls(config)==platform_urls({})
    monkeypatch.setattr(run_app,'PlatformTokenStore',lambda *a,**kw:pytest.fail('raw launch must not read tokens'))
    run_app.clear_previous_app_login(config)


def test_raw_ui_platform_actions_are_inert_and_retry_is_local(tmp_path):
    sys.path.insert(0,str(ROOT/'scripts'))
    from PySide6.QtCore import QCoreApplication
    from qt_ui.bridge import Bridge
    app=QCoreApplication.instance() or QCoreApplication([])
    b=Bridge({'DATA_COLLECTION_STORAGE_MODE':'raw-only'},demo=True,settings_path=tmp_path)
    calls=[];b.action=lambda *a,**kw:calls.append(a)
    b.selectUploadTarget('cloud');b.login('user','',False,False,False);b.logout();b.openPlatform()
    assert not calls
    b.retryUploads()
    assert calls[0][:2]==('save','/umi/storage/retry')
    b.shutdown()


def test_local_platform_choice_uses_loopback_and_leaves_saved_settings_intact(monkeypatch):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from recording_mode import launch_values
    saved = {'PLATFORM_API_URL': 'https://cloud.example', 'PLATFORM_WEB_URL': 'https://web.example'}
    assert launch_values(saved, 'raw-only')['DATA_COLLECTION_STORAGE_MODE'] == 'raw-only'
    assert launch_values(saved, 'local-platform')['PLATFORM_API_URL'] == 'http://127.0.0.1:8000'
    assert saved['PLATFORM_API_URL'] == 'https://cloud.example'
    with pytest.raises(ValueError, match='回环地址'):
        launch_values({**saved, 'UMI_LOCAL_API_URL': 'https://cloud.example'}, 'local-platform')


def test_local_platform_scan_skips_default_and_legacy_episodes(tmp_path):
    from teleop_control.collection_uploader import CollectionUploader, READY_MARKER
    from teleop_control.background_upload import uploader_spec
    target = dict(kind='local', api_url='http://127.0.0.1:8000', web_url='http://127.0.0.1:5173', storage_mode='local_raw')
    client = Mock()
    root = tmp_path / 'tianji'
    root.mkdir()
    uploader = CollectionUploader(root, target['api_url'], client=client)
    uploader.local_destination = target
    uploader.capture_root = tmp_path
    for i, marker in enumerate(({}, {'upload_destination': {'kind': 'raw-only'}},
                                {'upload_destination': {**target, 'format': 'other'}})):
        folder = root / str(i)
        folder.mkdir()
        (folder / READY_MARKER).write_text(json.dumps(marker))
    uploader.scan_once()
    assert uploader_spec(uploader)['local_destination'] == target
    assert not client.mock_calls


def test_all_teleop_directories_created_on_default_launch(tmp_path, monkeypatch):
    from teleop_control import main as m
    from teleop_control.kuavo import KuavoManager
    from teleop_control.tianji_collection import TianjiCollection
    data = tmp_path / 'app' / 'data'
    monkeypatch.setenv('TELEOP_DATA_ROOT', str(data))
    monkeypatch.setenv('TELEOP_OUTPUT', str(tmp_path / 'old-output'))
    monkeypatch.delenv('DATA_COLLECTION_STORAGE_MODE', raising=False)
    monkeypatch.setenv('DATA_COLLECTION_GATE_FILE', str(tmp_path / 'gate.json'))
    monkeypatch.setattr(sys, 'argv', ['collector', '--mock', '--umi-data-root', str(tmp_path)])
    assert Path(m.parse_args().output) == data / 'g2'
    assert TianjiCollection(Mock()).saved_output == data / 'tianji'
    assert KuavoManager(Mock(), root=tmp_path).collection.output == data / 'kuavo'
    monkeypatch.setattr(m, 'build_controller', lambda *a, **kw: Mock())
    monkeypatch.setattr(m, 'build_preview', lambda *a, **kw: None)
    monkeypatch.setattr(m, 'create_app', lambda *a, **kw: SimpleNamespace(
        state=SimpleNamespace(tianji_manager=Mock(), kuavo_manager=Mock())))
    monkeypatch.setattr(m.uvicorn, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(m, 'PlatformLogin', lambda *a, **kw: pytest.fail('unexpected platform login'))
    m.main()
    assert {p.name for p in data.iterdir() if p.is_dir()} == {'tianji', 'kuavo', 'g2'}


def test_local_directory_registration_retries_only_the_same_id(tmp_path):
    import httpx
    from teleop_control.collection_uploader import CollectionUploader, READY_MARKER, UPLOADED_MARKER
    from teleop_control.platform_auth import PlatformTokenStore, PlatformLogin, PlatformBearerAuth
    from teleop_control.upload_targets import UploadTargets
    api = 'http://127.0.0.1:8000'
    token = PlatformTokenStore(tmp_path / 'token')
    token.write(token='fixture', expires_in=3600, user={'username': 'collector'})
    targets = UploadTargets(tmp_path, PlatformLogin(api, token), api, local_directory_import=True)
    device = tmp_path / 'data/tianji'
    directory = device / '模拟回合'
    directory.mkdir(parents=True)
    meta = directory / 'meta_info.json'
    meta.write_text('{"complete":false}')
    marker = directory / READY_MARKER
    marker.write_text(json.dumps({'author':'collector', 'upload_destination':targets.snapshot()}))
    calls = []
    def respond(request):
        assert request.method == 'POST' and request.url.path == '/uploads/local-episodes'
        assert request.headers['Authorization'] == 'Bearer fixture'
        payload = json.loads(request.content)
        assert set(payload) == {'id', 'directory'} and payload['directory'] == 'tianji/模拟回合'
        calls.append(payload)
        if len(calls) == 1:
            raise httpx.ConnectError('平台离线', request=request)
        if len(calls) == 2:
            return httpx.Response(409, json={'detail':'目录冲突'})
        return httpx.Response(201, json={'id':payload['id'],'status':'registered','storage_mode':'local_raw'})
    with httpx.Client(transport=httpx.MockTransport(respond), auth=PlatformBearerAuth(token)) as client:
        uploader = CollectionUploader(device, api, client=client, targets=targets)
        uploader.capture_root = device.parent
        uploader.local_destination = targets.snapshot()
        uploader.scan_once()
        assert uploader.status()['failed'] == 1 and not (directory/UPLOADED_MARKER).exists()
        uploader.scan_once()
        assert '目录冲突' in uploader.status()['error'] and not (directory/UPLOADED_MARKER).exists()
        uploader.scan_once()
        uploader.scan_once()
        assert len(calls) == 3 and calls[0] == calls[1] == calls[2]
        assert uploader.status()['registered'] == 1 and uploader.status()['uploaded'] == 0
        assert json.loads((directory/UPLOADED_MARKER).read_text())['status'] == 'registered'
        assert meta.read_text() == '{"complete":false}'


@pytest.mark.parametrize('finalized', [True, False])
def test_local_tianji_ready_marker_records_finalization_independently_of_quality(tmp_path, finalized):
    import threading
    from teleop_control.collection_uploader import READY_MARKER
    from teleop_control.tianji_collection import TianjiCollection

    directory = tmp_path / 'take'
    directory.mkdir()
    (directory / 'meta_info.json').write_text('{"complete":false}')
    episode = SimpleNamespace(
        stopping=threading.Event(), finished=threading.Event(), run=lambda: None,
        directory=directory, records_finalized=finalized, error='相机缺帧',
    )
    info = {'author': 'operator', 'teleop_session_id': 'test', 'upload_sides': ['left'],
            'upload_destination': {'kind': 'local', 'storage_mode': 'local_raw'}}
    collection = TianjiCollection(Mock(), output=tmp_path)
    collection._record(episode, info)
    assert collection.phase == 'incomplete'
    if finalized:
        assert json.loads((directory / READY_MARKER).read_text()) == info
        assert not json.loads((directory / 'meta_info.json').read_text())['complete']
    else:
        assert not (directory / READY_MARKER).exists()
