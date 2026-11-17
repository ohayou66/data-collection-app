# 2026-11-17 文档整理与迁移对照

[文档目录](../README.md) · [历史目录](README.md) · [项目首页](../../README.md)

本轮接续工作区已有的文档整理。根目录 README 保留项目介绍、安装入口、导航和当前限制；操作步骤、部署、数据、维护、技术参考与历史资料分别维护。

## 旧入口与新位置

| 原入口或内容 | 当前入口 |
|---|---|
| 根 README：安装、桌面兼容和云平台配置 | [安装与启动](../deployment/installation.md) |
| 根 README：设备操作与标注 | [操作概览](../usage/overview.md)、[天机](../usage/tianji.md)、[乐聚](../usage/kuavo.md)、[UMI](../usage/umi.md) |
| 根 README：数据流、UMI 就绪和保存格式 | [数据保存与上传](../data/recording.md) |
| 根 README：依赖与开发验证 | [开发说明](../development.md) |
| 根 README：GitHub 同步 | [源码同步](../deployment/source-sync.md) |
| 根 README：历次功能合并 | [10–11 月变更记录](changes-202610-11.md) |
| 根 README：乐聚接入与 ZED 现场补充 | [集成与相机现场记录](kuavo-and-camera-notes.md) |
| `打包与分发.md` | [打包、安装与分发](../deployment/packaging.md) |
| `HDF5数据检查.md` | [HDF5 数据检查](../data/hdf5-quality.md) |
| `优化合并说明.txt` | [2026-10-12 合并说明](2026-10-12-merge.md) |
| `fusion_camera_stream/REPORT_60S.md` | [60 秒报告](camera/fusion-60s.md) |
| `fusion_camera_stream/REPORT_100HZ_GRIPPERS.md` | [100 Hz 与夹爪报告](camera/fusion-100hz-grippers.md) |
| `fusion_camera_stream/REPORT_GRIPPER_30HZ.md` | [夹爪 30 Hz 报告](camera/fusion-gripper-30hz.md) |
| `fusion_camera_stream/packet_diagnostics/REPORT.md` | [数据包诊断](camera/packet-diagnostics.md) |
| `fusion_data_collection/FusionDataCollector/VERIFICATION.md` | [采集器验证](camera/collector-verification-20260921.md) |

## 天机专题拆分

原 `docs/usage/tianji.md` 中的正文按主题分配，维护工具的版本限制、数据完整性条件和验证范围一并保留：

| 内容 | 当前入口 |
|---|---|
| 连接、账号凭据、接管、按键、参数、手动复位 | [天机操作](../usage/tianji.md) |
| 相机档位、预览、重连、更新及版本限定的修复工具 | [相机配置与维护](../maintenance/tianji-camera.md) |
| 连续录制、后台队列、单臂上传和失败处理 | [天机数据说明](../data/tianji-recording.md) |
| 坐标、TCP、逆运动学、碰撞边界和实测安装标定 | [模型与控制](../reference/tianji-model.md) |

当前 App 的相机清单来自 `tianji_collection.py`，上传筛选来自 `tianji_export.py`。据此修正了旧“三路完整”描述：当前 App 按实际相机清单录制，旧独立 CLI 的三路校验仍属于该工具的限制。设备配置帧率与实测帧率继续分别表述。

## 核查范围

文档核查覆盖项目首页、`docs/` 和相机/采集模块说明的本地链接、章节锚点、迁移内容及 Markdown 差异。相机诊断模块补充了历史日期和当前指南入口。外部站点、历史现场路径与设备状态不在此次验证范围内。

旧诊断模块引用的 `results/20260920-125518/REPORT.md`、`results/20260920-134736/REPORT.md` 与 `results/20260920-144427/REPORT.md` 不在当前目录中。对应说明保留原路径和结果摘要，并注明报告缺失；未用其他测试报告替代这些证据。

源码、脚本、模型、配置、运行数据、报告证据和厂商目录保持原位。本轮没有构建安装包、部署设备、启动采集或推送 Git；原有未提交改动继续保留在工作区。
