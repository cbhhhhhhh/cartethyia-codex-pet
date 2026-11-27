# 版本记录

| 版本 | 平台 | 发行内容 |
| --- | --- | --- |
| [0.2.0](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/tag/v0.2.0) | macOS · Apple Silicon | 109 段重新绘制的角色动作、可点选的配图、人设约束、本地/API/Codex 三条模型线路、主子回合归属与任务用量。[本版说明](docs/RELEASE-0.2.0.md) |
| [0.1.0](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/tag/v0.1.0) | macOS、Windows | 可移植的 Mac 安装包、内置角色与运行时，以及随后补入的 Windows x64 发行资产。[双平台发行说明](docs/RELEASE-0.1.0.md) |

本项目在 2026 年 11 月 27 日统一调整公开版本号。原 2.3.0 对应 0.2.0，原 2.2.0 对应 0.1.0。原始验收文件保留采样时的编号。[重编号前的 Mac 源码](https://github.com/cbhhhhhhh/cartethyia-codex-pet/tree/5a267e5250a1df8d85d59893d68eb017c490f9bc) · [重编号前的 Windows 源码](https://github.com/cbhhhhhhh/cartethyia-codex-pet/tree/bcb113b86af7005d92b0a19026b4e1db4654c557)

每个版本的发布页保留当时的更新说明、安装方法和对应平台资产。[全部 GitHub Releases](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases)

## 后续版本如何发布

1. 在 `scripts/build.sh` 更新 macOS 的版本号与构建号，按本次改动补充测试，并写一份对应版本的发行说明。
2. 运行 `./scripts/package-macos.sh`，从生成的 ZIP 测试安装、升级、回退及卸载。将经过验收的提交打上 `v主版本.次版本.修订号` 标签。
3. 在该标签的 GitHub Release 上传安装包和本次生成的校验文件，写明支持的平台和安装步骤。README 的安装入口统一指向 Releases，本表使用每个版本的固定链接。某个平台验收通过后再提供该平台的下载地址。
