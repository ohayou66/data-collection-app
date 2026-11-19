# 小凯实验室数采平台

运行在采集电脑上的 PySide6 + Qt Quick/QML 桌面应用，提供机器人遥操作、相机预览和数据采集。支持天机 Marvin M6、乐聚 KUAVO 5-W、智元 G2 与 UMI；具体入口取决于安装包架构和设备运行环境。Ego 为占位页，不提供 HIL-SERL。

登录页的「启动模式」下拉框预选「默认（仅保存原始数据）」，点击「进入采集」即可使用。天机、乐聚、智元 G2 的新回合分别写入代码目录下的 `data/tianji/`、`data/kuavo/`、`data/g2/`。UMI 的新回合写入 `data/umi/rosbags/<任务>/<回合>/`。选择「上传本机平台」并登录运行中的本机 Docker 平台后，App 提交回合 UUID 和相对目录。平台从本机只读挂载读取原始数据，并对支持的格式执行转换和质量检查。

## 安装与启动

源码版在仓库根目录执行：

```bash
./install-app.sh
./start-app.sh
```

使用实际桌面用户安装，不要对整个安装脚本使用 sudo。依赖、源码换机和平台地址设置见[安装说明](docs/deployment/installation.md)。完整 `.deb` 的构建、安装及升级见[打包与分发](docs/deployment/packaging.md)。

## 操作指南

| 需要做什么 | 文档 |
|---|---|
| 了解操作入口与子任务标注 | [操作概览](docs/usage/overview.md) |
| 天机设备检查、遥操作与复位 | [天机指南](docs/usage/tianji.md) |
| 天机相机参数、重连与诊断 | [相机维护](docs/maintenance/tianji-camera.md) |
| 乐聚设备检查、遥操与手动控制 | [KUAVO 指南](docs/usage/kuavo.md) |
| UMI 设备选择、标定与录制 | [UMI 指南](docs/usage/umi.md) |
| 查看数据保存格式和上传规则 | [数据说明](docs/data/recording.md) |
| 检查历史 HDF5 文件 | [HDF5 数据检查](docs/data/hdf5-quality.md) |
| 运行开发验证 | [开发说明](docs/development.md) |
| 将本机源码上传到 GitHub | [源码同步](docs/deployment/source-sync.md) |

完整索引见 [docs/README.md](docs/README.md)，旧版本参数、现场测试和变更经过见[历史记录](docs/history/README.md)。

## 当前版本边界

- 已合入使用端 UMI 端口预检与旧 XR 服务识别修复；历史质量提示在界面隐藏，后台记录保留。
- 天机保留 1280×720/60 fps 档位和相机线程调度，能力以真实设备及配套控制器版本为准。
- 天机 TCP 与模型沿用已合并的上游定义；新增末端全 CAD 碰撞网格检查仍未启用，不能据此认为外接相机支架已完整覆盖。
- UMI/PICO 安装点使用仓库内 CAD 基准的完整精度，方向和左右镜像关系不变。
- 最近功能合并的[验证记录](reports/remote-hotfix-merge-20261117.json)涵盖离线回归，不等于已部署或完成实机验收。

## 目录说明

| 目录 | 用途 |
|---|---|
| `docs/` | 使用、部署、数据、维护、技术参考与历史文档 |
| `scripts/` | 启动、构建、维护工具；`qt_ui/` 为桌面界面代码 |
| `teleop_control/` | 本机控制服务、机器人适配与模型 |
| `umi_collection/` | UMI 采集、监控、固件与镜像源码 |
| `fusion_camera_stream/`、`fusion_data_collection/` | 天机相机接口及采集链路 |
| `app/`、`components/`、`lib/`、`public/` | Web 开发界面、共享前端逻辑与静态资产 |
| `tests/` | 回归测试 |
| `reports/` | 发布与现场验证证据 |

`teleop_control/runtime/` 包含运行状态和真实采集数据；`.build-cache/`、`.venv/`、`outputs/` 等是本机工作文件，不能混入源码分发。它们不是本次文档整理的清理对象。配置和凭据使用本机 `.env` 与用户配置目录，不上传到 Git。

协作与部署约定见 [AGENTS.md](AGENTS.md)。
