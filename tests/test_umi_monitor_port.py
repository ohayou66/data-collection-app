"""Port conflicts must leave previews and hardware ownership untouched."""
import errno
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'teleop_control/src'))
from teleop_control import umi, umi_monitor
from teleop_control.models import UmiStartRequest


@pytest.mark.parametrize('hostname', ['127.0.0.1', 'localhost'])
def test_conflict_is_rejected_and_released_port_is_usable(hostname):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        url = f'http://{hostname}:{listener.getsockname()[1]}'
        with pytest.raises(RuntimeError, match='已被其他程序占用'):
            umi_monitor.require_free_monitor_port(url)
    umi_monitor.require_free_monitor_port(url)
    # The preflight itself must also release its probe socket.
    umi_monitor.require_free_monitor_port(url)


def test_remote_monitor_does_not_probe_local_socket(monkeypatch):
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('local probe'))
    umi_monitor.require_free_monitor_port('http://192.0.2.1:8770')


def test_permission_error_is_reported_not_mistaken_for_free_port(monkeypatch):
    def denied(*args, **kwargs):
        raise OSError(errno.EACCES, 'denied')
    monkeypatch.setattr(socket, 'socket', denied)
    with pytest.raises(RuntimeError, match='无法使用采集监控端口 8770'):
        umi_monitor.require_free_monitor_port('http://127.0.0.1:8770')


def test_conflict_prevents_device_checks_preview_stop_and_process_launch(tmp_path, monkeypatch):
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'tools/galaxis_collection.py').touch()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        manager = umi.UmiManager(tmp_path, tmp_path / 'data', python=sys.executable,
            runtime_dir=tmp_path / 'runtime',
            monitor_url=f'http://127.0.0.1:{listener.getsockname()[1]}')
        def forbidden(*args, **kwargs):
            pytest.fail('Port conflict must be rejected before taking over devices')
        for name in ('check', '_stop_encoder_preview', '_stop_camera_previews',
                     '_start_with_encoder_handoff'):
            monkeypatch.setattr(manager, name, forbidden)
        with pytest.raises(RuntimeError, match='已被其他程序占用'):
            manager.start(UmiStartRequest())
        assert manager._process is None
        assert 'collection' not in manager._encoder_preview_blockers
