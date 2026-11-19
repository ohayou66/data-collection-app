"""Resolve the storage choice for this launch without changing saved credentials."""

from urllib.parse import urlsplit

from generate_runtime_config import platform_urls


def launch_values(settings, mode):
    values = dict(settings)
    values["DATA_COLLECTION_STORAGE_MODE"] = mode
    if mode == "local-platform":
        for key, local_key, fallback in (
            ("PLATFORM_API_URL", "UMI_LOCAL_API_URL", "http://127.0.0.1:8000"),
            ("PLATFORM_WEB_URL", "UMI_LOCAL_WEB_URL", "http://127.0.0.1:5173"),
        ):
            configured = values.get(key, fallback)
            if urlsplit(configured).hostname not in ("localhost", "127.0.0.1", "::1"):
                configured = fallback
            url = values.get(local_key) or configured
            if urlsplit(url).hostname not in ("localhost", "127.0.0.1", "::1"):
                raise ValueError("上传本机平台需要使用本机回环地址")
            values[key] = url
    values.update(platform_urls(values))
    return values
