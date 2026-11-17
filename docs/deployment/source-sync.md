# 源码同步与 GitHub 上传

[文档目录](../README.md) · [项目首页](../../README.md)

所有命令在当前源码仓库根目录执行，不依赖某位开发者的桌面路径。推送源码不会部署使用端，也不会更新机器人控制器。

## 先核对目标

```bash
git status --short --branch
git remote -v
git log -5 --oneline
```

2026-11-17 整理时，本机配置为：

| 远程名 | 地址 | 用途 |
|---|---|---|
| `origin` | `https://github.com/ohayou66/data-collection-app.git` | 本机仓库的上传目标 |
| `teammate` | `https://github.com/ljy-2-2/data-collection-app.git` | 合并参考来源 |

其他电脑或后续配置可能不同，以 `git remote -v` 的实际输出和操作者选择为准。

## 上传已提交的本地版本

确认当前在 `main`、提交内容正确，并确认 `origin` 是希望更新的仓库后执行：

```bash
git push origin main
```

有未提交文件时先查看 `git diff`，只暂存本次明确要提交的路径，检查暂存内容后再提交。不把 `.env`、授权文件、运行数据、缓存或备份加入 Git。远端已有新提交导致推送被拒绝时，先获取并核对差异，处理冲突后再推送，不强制覆盖历史。

## 现有快捷脚本的适用范围

[`scripts/push_github.sh`](../../scripts/push_github.sh) 仍固定使用远程名 `ljy` 和 `git@github.com:ljy-2-2/data-collection-app.git`，并执行 `git add -A`。它不是上述 `origin` 上传流程的通用入口；需要推送到 `origin` 时使用上面的明确命令。

本次只修正文档，未修改或执行该脚本。构建与部署另见[打包与分发](packaging.md)。
