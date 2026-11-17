# 开发依赖与验证

[文档目录](README.md) · [项目首页](../README.md)

命令均在仓库根目录执行，使用已装好测试依赖的解释器。视频测试还需要 FFmpeg/ffprobe；Qt 测试需要 PySide6，部分 CAD 测试需要 xacro。

历史文件的独立 HDF5 质量检查：运行 `python3 scripts/check_hdf5_quality.py "/路径/文件.h5"`，
会生成离线图表报告、0～3 阶差分/Z-score 和异常明细；不会修改原文件。
参数与计算约定见 [HDF5 数据检查](data/hdf5-quality.md)。

- PySide6 6.8.3 / Qt Quick（完整 deb 已内置）；Qt 系统图形库由 apt 安装
- Python 3.12+
- 智元 GDK / bot Python 环境
- `adb`、Galaxis VR 服务以及 UMI Docker/ROS 环境

厂商运行时代码、遥操作采集器、UMI 工程、前端和启动脚本都包含在本文件夹内。
完整 `.deb` 会安装 Docker、Compose、ADB 并携带 UMI 镜像；源码安装脚本不负责这些系统组件。
GDK 系统库、机器人驱动和硬件固件仍按具体机器人部署。

## 源码入口

桌面入口为 `scripts/desktop_app.py`，原生界面位于 `scripts/qt_ui/qml/`，与后端通信的桥接位于 `scripts/qt_ui/bridge.py`；`app/` 与 `components/` 保留源码开发使用的网页界面。

天机控制维护见[模型与坐标](reference/tianji-model.md)，控制器相机维护见[相机配置与诊断](maintenance/tianji-camera.md)。

## 开发验证

```bash
PYTHONPATH=scripts:teleop_control/src:teleop_control/vendor/tianji/teleop:fusion_camera_stream:fusion_data_collection/FusionDataCollector/controller_v22 python3 -m pytest tests
# 使用装有 PySide6 的解释器，隔离模拟接口，不连接硬件：
.venv/bin/python scripts/smoke_qt_ui.py --screenshots /tmp/qt-ui-check
```

本工程是采集电脑本地应用，不发布到公共网站；公开托管页面无法直接、安全地拥有本机 USB/VR 设备。

最近一次功能合并的验证范围见[2026-11-17 验证记录](../reports/remote-hotfix-merge-20261117.json)。历史测试通过不表示后续改动或真实设备已验收。
