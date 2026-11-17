# 历史记录

[文档目录](../README.md) · [项目首页](../../README.md)

本目录保留旧版本实现过程、机器路径、参数、部署状态和测试结果。内容只对当时记录的版本与场景有效；当前步骤请查[使用指南](../README.md#使用)。历史文件中的命令不是自动执行清单。

## 变更与集成

| 记录 | 范围 |
|---|---|
| [2026-11-17 文档整理与迁移对照](documentation-20261117.md) | 当前目录结构、旧入口去向与核查范围 |
| [2026 年 10–11 月变更](changes-202610-11.md) | 使用端修复、连续相机、标注与选择性合并 |
| [2026-10-12 合并说明](2026-10-12-merge.md) | 早期本机目录合并、验证与备份位置 |
| [乐聚集成与相机现场记录](kuavo-and-camera-notes.md) | 原 README 的乐聚接入、后续功能和 11 月相机现场补充 |

## 早期天机相机与采集验证

| 记录 | 原位置 |
|---|---|
| [三路图像与关节 60 秒](camera/fusion-60s.md) | `fusion_camera_stream/REPORT_60S.md` |
| [100 Hz 关节与夹爪](camera/fusion-100hz-grippers.md) | `fusion_camera_stream/REPORT_100HZ_GRIPPERS.md` |
| [夹爪 30 Hz](camera/fusion-gripper-30hz.md) | `fusion_camera_stream/REPORT_GRIPPER_30HZ.md` |
| [数据包诊断](camera/packet-diagnostics.md) | `fusion_camera_stream/packet_diagnostics/REPORT.md` |
| [采集器验证：2026-09-21](camera/collector-verification-20260921.md) | `fusion_data_collection/FusionDataCollector/VERIFICATION.md` |

其余机器可读结果、发布校验、图片和现场证据继续保留在 [`reports/`](../../reports/)，本次未移动。上游组件的 `vendor/` 文档、许可证和计划也保持原位。
