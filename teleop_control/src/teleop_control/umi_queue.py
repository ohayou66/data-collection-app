"""Read-only view of durable episodes, scoped to their original destination."""
import json
import yaml
from pathlib import Path


def read_json(path):
    try:
        value = path.read_text(encoding='utf-8')
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def queue_summary(data_root, destination=None, *, raw_only=False):
    root = Path(data_root)
    default = read_json(root / '.background-upload/config.json').get('default_destination')
    result = dict(pending=0, uploaded=0, processing=0, failed_processing=0,
                  other_pending=0, waiting_auth=0, uploading=0, failed=0, message='',
                  interrupted=0, needs_review=0, quality_message='', last_interruption=None)
    if raw_only:
        result.update(saved=0, upload_enabled=False)
    reasons = []
    bags = (root / 'rosbags').resolve()
    recovery = {}
    for path in (bags / '.capture-journals').glob('*.json'):
        intent = read_json(path)
        if intent.get('state') != 'interrupted':
            continue
        folder = (bags / intent.get('folder', '')).resolve()
        if folder != bags and folder.is_relative_to(bags) and folder.is_dir():
            recovery[folder] = intent.get('metadata') or {}
    folders = {p.parent for name in ('meta.json', '.mp4-pending.json') for p in bags.glob('*/*/' + name)} | recovery.keys()
    for folder in sorted(folders):
        try:
            if (folder / '.discarded').exists():
                continue
            meta = read_json(folder / 'meta.json') or read_json(folder / '.mp4-pending.json') or recovery.get(folder, {})
            target = meta.get('upload_destination') or default
            receipt = (folder / '.data-platform-uploaded.json').is_file()
            processing = ((folder / '.mp4-pending.json').is_file() or (folder / '.recovery-pending').exists() or folder in recovery)
            failure = (folder / 'recording-failure.json').is_file()
            complete = ((folder / 'media/video-manifest.json').is_file() or
                        ((folder / 'metadata.yaml').is_file() and any(folder.glob('*.mcap'))))
        except OSError as exc:
            # A historical episode must not break status or recording controls.
            reasons.append(f"无法读取采集数据 {folder.name}：{exc.strerror or str(exc)}；请检查目录权限或磁盘状态")
            continue
        if not raw_only and destination is not None and target != destination:
            if not receipt and (processing or complete) and destination.get('storage_mode') != 'local_raw':
                result['other_pending'] += 1
            continue
        if processing:
            result['failed_processing' if failure else 'processing'] += 1
        elif complete and not failure:
            interruption = meta.get('interruption') or {}
            quality = meta.get('data_quality') or read_json(folder / 'data-quality.json')
            warnings = quality.get('warnings') or []
            if interruption:
                result['interrupted'] += 1
                candidate = dict(folder=folder.name, reason=str(interruption.get('reason', 'unknown')),
                                 detected_ns=int(interruption.get('detected_ns') or 0))
                previous = result['last_interruption']
                if previous is None or candidate['detected_ns'] > previous['detected_ns']:
                    result['last_interruption'] = candidate
            if interruption or warnings:
                result['needs_review'] += 1
            if warnings and not result['quality_message']:
                result['quality_message'] = '历史数据质量提示（不影响当前采集）：' + '；'.join(dict.fromkeys(str(x) for x in warnings))[:700]
            if raw_only:
                result['saved'] += 1
                continue
            if receipt:
                result['uploaded'] += 1
                continue
            result['pending'] += 1
            state = read_json(folder / '.upload-status.json')
            stage = state.get('state')
            if stage in ('waiting_auth', 'uploading', 'failed'):
                result[stage] += 1
            if state.get('message') and stage != 'uploaded':
                reasons.append(state['message'])
    if result['other_pending']:
        reasons.append(f"其他平台尚有 {result['other_pending']} 段待上传，保留原目标；可切换到原平台查看")
    last = result['last_interruption']
    if last:
        labels = {'platform_connection_lost':'平台连接检查中断',
                  'desktop_heartbeat_lost':'采集界面心跳丢失',
                  'record_manager_exited':'录制管理进程退出',
                  'recorder_stopped_unexpectedly':'录制进程异常停止'}
        reason = labels.get(last['reason'], last['reason'])
        last['message'] = '上次异常中断：' + last['folder'] + ' · ' + reason + '；已保留可用数据，请复核该段'
    result['message'] = '；'.join(dict.fromkeys(reasons))
    return result


def completed_mcap(payload_dir):
    try:
        metadata = yaml.safe_load((payload_dir / "metadata.yaml").read_text(encoding="utf-8"))
        names = metadata["rosbag2_bagfile_information"]["relative_file_paths"]
    except (yaml.YAMLError, KeyError, TypeError) as exc:
        raise ValueError("UMI 回合的 metadata.yaml 无效") from exc
    # The platform's rosbag ingest consumes one MCAP per Episode. Our
    # recorder does not split bags; reject unexpected layouts explicitly.
    if not isinstance(names, list) or len(names) != 1 or not isinstance(names[0], str) or Path(names[0]).name != names[0]:
        raise ValueError("rosbag Episode must contain one complete MCAP file")
    mcap = payload_dir / names[0]
    if mcap.suffix.lower() != ".mcap" or not mcap.is_file() or mcap.is_symlink():
        raise ValueError("rosbag metadata references a missing MCAP file")
    with mcap.open("rb") as handle:
        magic = b"\x89MCAP0\r\n"
        if handle.read(8) != magic or mcap.stat().st_size < 16:
            raise ValueError("invalid MCAP header")
        handle.seek(-8, 2)
        if handle.read(8) != magic:
            raise ValueError("MCAP has not been finalized")
    return mcap


def local_registration_info(folder, destination):
    """Publish the handoff only for a finalized UMI round opted in at capture start."""
    from .collection_uploader import READY_MARKER
    from .umi_uploader import UmiRosbagUploader

    if UmiRosbagUploader._processing(folder):
        return None
    meta = read_json(folder / 'meta.json')
    if meta.get('upload_destination') != destination or not meta.get('author'):
        return None
    info = {'author': meta['author'], 'upload_destination': destination, 'source': 'umi'}
    marker = folder / READY_MARKER
    if marker.is_symlink():
        raise ValueError('UMI 完成标记不能是符号链接')
    if marker.exists():
        existing = read_json(marker)
        if any(existing.get(key) != value for key, value in info.items()):
            raise ValueError('UMI 完成标记与录制账号或目标不一致')
        return info
    # meta.json also exists during offline MP4 processing. The finalizer
    # publishes ready only after verifying the output and cleaning staging files.
    media = folder / 'media' if (folder / 'media/video-manifest.json').is_file() else folder
    manifest_path = media / 'video-manifest.json'
    if manifest_path.is_file() or meta.get('recording_format') == 'umi-mp4-v1':
        manifest = read_json(manifest_path)
        cameras = manifest.get('cameras') or []
        if (manifest.get('format') != 'umi-mp4-v1' or manifest.get('state') != 'complete'
                or not cameras or manifest.get('signals', {}).get('file') != 'signals.mcap'):
            return None
        for camera in cameras:
            name = camera.get('file', '')
            if Path(name).name != name or not name.endswith('.mp4') or not (media/name).is_file():
                return None
    elif (meta.get('video_output') == 'mp4' and meta.get('recording_format') != 'umi-mcap-h264-v1'
          and read_json(folder / 'raw-data-status.json').get('state') != 'ready'):
        # MJPEG metadata can briefly precede creation of its MP4-pending flag.
        return None
    if not (media/'metadata.yaml').is_file():
        return None
    mcap = completed_mcap(media)
    if manifest_path.is_file() and mcap.name != 'signals.mcap':
        raise ValueError("UMI 视频清单与 MCAP 文件不一致")
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps(info, ensure_ascii=False))
    temporary.replace(marker)
    return info
