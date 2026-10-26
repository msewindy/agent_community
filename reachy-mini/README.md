# Reachy Mini Wireless（Wi-Fi 版）开发笔记

整理日期：2026-10-01。材料来自 Pollen Robotics / Hugging Face 官方文档与 `pollen-robotics/reachy_mini` 仓库 `main` 分支，是阅读摘要，不是原文拷贝。细节、截图和逐步刷机图以官网为准。

官方把这台机器叫做 **Reachy Mini (Wireless)**：机内 Raspberry Pi Compute Module 4、电池、Wi-Fi，上电后自主运行。日常说的「Wi-Fi 版」就是这一版。另有 USB 连电脑的 **Lite**，以及不需要硬件的 **MuJoCo 仿真**。

## 先看这几条

- 控制程序是机器人上的 **daemon**（systemd 服务 `reachy-mini-daemon`），默认监听 `http://reachy-mini.local:8000`。电脑上的 Python / 浏览器 / REST 都是它的客户端。
- 出厂 SSH：`ssh pollen@reachy-mini.local`，用户 `pollen`，密码 `root`。这是官方公开的出厂账号，联网后应自行改掉。
- 新应用官方更推荐 **浏览器里的 JavaScript / WebRTC 应用**（零安装、可分享）。Python SDK 适合脚本、控制环，以及直接跑在机器人上的代码。
- Wireless 独有 **IMU**。相机和麦克风由 daemon 独占；本机客户端走 LOCAL（GStreamer IPC），远程客户端走 WebRTC。
- 远程 Python 的 WebRTC 媒体后端，官方写明目前只有 **Linux 客户端完整支持**，Windows / macOS 还在后续计划里（[issue #572](https://github.com/pollen-robotics/reachy_mini/issues/572)）。在 Windows 上开发时，优先用 VS Code Remote-SSH 把代码跑在机器人上，或做 JS Web 应用 / 直接调 REST。

## 笔记目录

| 文件 | 内容 |
|------|------|
| [01-平台与硬件.md](01-平台与硬件.md) | 三款形态对比、机构、电子、CM4 |
| [02-上手与日常使用.md](02-上手与日常使用.md) | 装配、首次 Wi-Fi、系统更新、控制台、SSH |
| [03-开发工作流.md](03-开发工作流.md) | 在机器人上改代码的三种做法、daemon 分支、Windows 注意点 |
| [04-架构与编程接口.md](04-架构与编程接口.md) | Daemon / SDK、运动与限位、REST、JS SDK、唤醒休眠 |
| [05-应用开发.md](05-应用开发.md) | App 契约、安装发布、离线部署、日志 |
| [06-相机麦克风与IMU.md](06-相机麦克风与IMU.md) | 媒体架构、相机、麦克风阵列、DoA、IMU、均衡 |
| [07-维护重置与刷机.md](07-维护重置与刷机.md) | 蓝牙重置、刷 ReachyMiniOS、恢复出厂 daemon |
| [08-排障速查.md](08-排障速查.md) | 连不上、热点、国内网络、电机与音频 |
| [官方文档索引.md](官方文档索引.md) | 官方页面与仓库链接 |

## 官方入口

- 文档首页：<https://huggingface.co/docs/reachy_mini>
- Wireless 入门：<https://huggingface.co/docs/reachy_mini/platforms/reachy_mini/get_started>
- SDK 仓库：<https://github.com/pollen-robotics/reachy_mini>
- 系统镜像：<https://github.com/pollen-robotics/reachy-mini-os/releases>
- 桌面控制台下载：<https://hf.co/reachy-mini/#/download>
- 给 AI 编程助手的说明：<https://github.com/pollen-robotics/reachy_mini/blob/main/AGENTS.md>
