# 版本记录

| 版本 | 平台 | 发行内容 |
| --- | --- | --- |
| [2.3.0](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/tag/v2.3.0) | macOS · Apple Silicon | 109 段重新绘制的角色动作、可点选的配图、人设约束、本地/API/Codex 三条模型线路、主子回合归属与任务用量。[本版说明](docs/RELEASE-2.3.0.md) |
| [2.2.0](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/tag/v2.2.0) | macOS、Windows | 可移植的 Mac 安装包、内置角色与运行时，以及随后补入的 Windows x64 发行资产。[Mac 版说明](docs/RELEASE-2.2.0.md) |

每个版本的发布页保留当时的更新说明、安装方法和对应平台资产。[全部 GitHub Releases](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases)

## 后续版本如何发布

1. 在 `scripts/build.sh` 更新 macOS 的版本号与构建号，按本次改动补充测试，并写一份对应版本的发行说明。
2. 运行 `./scripts/package-macos.sh`，从生成的 ZIP 测试安装、升级、回退及卸载。将经过验收的提交打上 `v主版本.次版本.修订号` 标签。
3. 在该标签的 GitHub Release 上传安装包和本次生成的校验文件，写明支持的平台和安装步骤。README 以及上表指向该版本的固定链接。某个平台验收通过后再提供该平台的下载地址。
