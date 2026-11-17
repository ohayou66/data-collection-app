# 文档目录

[项目首页](../README.md)

本目录集中维护当前使用说明。除特别注明外，命令和行内源码路径均以仓库根目录为工作目录；不要先进入 `docs/` 再执行启动或构建命令。

## 按任务查找

| 当前任务 | 从这里开始 |
|---|---|
| 第一次安装或换电脑 | [安装与启动](deployment/installation.md) |
| 开始一轮采集 | [操作概览](usage/overview.md)，再进入对应设备指南 |
| 查找已采数据或处理上传 | [数据保存与平台上传](data/recording.md) |
| 天机相机无画面、改参数或升级服务 | [相机配置与维护](maintenance/tianji-camera.md) |
| 核对天机 TCP、坐标或复位条件 | [模型与控制](reference/tianji-model.md) |
| 构建安装包交给其他电脑 | [打包与分发](deployment/packaging.md) |
| 查询某次测试或旧版本行为 | [历史记录](history/README.md) |

## 使用

- [操作概览与子任务标注](usage/overview.md)
- [天机：设备检查、遥操作、参数与复位](usage/tianji.md)
- [乐聚 KUAVO：设备检查、遥操与手动控制](usage/kuavo.md)
- [UMI：硬件选择、标定与录制](usage/umi.md)

## 安装、部署与开发

- [安装、启动与平台配置](deployment/installation.md)
- [打包、独立运行版和离线分发](deployment/packaging.md)
- [源码同步与上传目标核对](deployment/source-sync.md)
- [开发依赖与验证](development.md)

## 数据

- [数据保存、格式与平台上传](data/recording.md)
- [天机录制、后台保存与单臂上传](data/tianji-recording.md)
- [HDF5 数据检查](data/hdf5-quality.md)
- [发布与现场验证证据](../reports/)

## 维护与技术参考

- [天机相机：预览、参数、重连、控制器升级与故障诊断](maintenance/tianji-camera.md)
- [天机模型：坐标、TCP、逆运动学、复位与实测标定](reference/tianji-model.md)

## 历史与模块资料

- [历史记录与相机验收归档](history/README.md)
- [独立相机客户端说明](../fusion_camera_stream/README.md)
- [v2.1 相机接入说明](../fusion_camera_stream/APP_INTEGRATION.md)
- [采集器独立 CLI 与历史部署说明](../fusion_data_collection/FusionDataCollector/README.md)
- [旧相机诊断工具说明](../fusion_camera_diagnostics/README.md)
- [内置运行时代码来源](../teleop_control/vendor/README.md)
- [Galaxis 上游模块说明](../umi_collection/vendor/galaxis/README.md)

模块文档的适用版本以文首说明为准；`vendor/` 内文档随上游组件保留，不代表本 App 已启用所有上游功能。

## 文档维护规则

1. 根目录 README 只保留项目入口、目录导航和当前重要限制。
2. 当前操作步骤写入对应主题文档；旧参数、过程记录与现场结果放入历史目录或 `reports/`，注明日期与验证范围。
3. 文档移动时同步修正相对链接。命令示例使用仓库相对路径，真实凭据和个人采集目录不写入示例。
4. 改变功能时先更新当前指南，再补变更记录；历史报告保留原始结论，不将短时实测改写为长期保证。

原文档位置及新入口见[迁移对照](history/documentation-20261117.md)。程序与 Shell 脚本位置未改变。
