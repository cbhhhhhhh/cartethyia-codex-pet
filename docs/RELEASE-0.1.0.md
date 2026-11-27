# 卡提希娅 Codex 桌宠 0.1.0

本版首次发布于 2026 年 11 月 25 日，原版本号 2.2.0，现统一为 **0.1.0**。下面的实机记录来自首次发行，重编号安装包的 SHA-256 见本页 Assets。

| 系统 | 下载安装包 | 安装方法 |
| --- | --- | --- |
| Windows x64（已在 Windows 11 验证） | **[Windows 安装包（EXE）](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/download/v0.1.0/Cartethyia-0.1.0-Windows-x64-Setup.exe)** | 双击安装，从开始菜单打开「卡提希娅」。 |
| macOS 27.2 或更新版本，Apple Silicon | **[Mac 安装包（ZIP）](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/download/v0.1.0/Cartethyia-Codex-Pet-macOS-arm64.zip)** | 解压后双击 `安装.command`。 |

校验下载文件可使用对应的 SHA-256 清单。[Windows 校验文件](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/download/v0.1.0/SHA256SUMS-Windows.txt) · [macOS 校验文件](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/download/v0.1.0/SHA256SUMS)

## Windows 版本说明

- 安装包包含角色图集、109 段扩展动作和 10 张对话插画。任务提醒开箱可用，按需下载模型后可进行本机文字或图片聊天。此版本未作 Authenticode 签名。
- Windows 11 x64 实测覆盖真实 Codex 任务、审批、中断、安装、覆盖升级和卸载。常驻进程连续运行一小时，121 次采样中无异常退出。[Windows 安装与卸载说明](https://github.com/cbhhhhhhh/cartethyia-codex-pet/blob/v0.1.0/docs/WINDOWS.md) · [完整实机验收](https://github.com/cbhhhhhhh/cartethyia-codex-pet/blob/v0.1.0/docs/WINDOWS-ACCEPTANCE.md)
- 本页的源码归档包含 macOS 和 Windows 两个平台的源码。

重编号复核使用了隔离 Wine 环境，打开新 EXE 并核对安装后的版本号和全部 262 个随包文件。上面的一小时桌面测试来自原版在 Windows 11 真机上的记录。

## macOS 版本说明

本版面向 M 系列芯片、macOS 27.2 或更新版本。下载 Release Assets 里的 **Cartethyia-Codex-Pet-macOS-arm64.zip**，解压后双击 **安装.command**。启动前请安装支持本地插件的 Codex 桌面版。

- 安装包附上卡提图集、应用图标、109 个动作和独立 Python 运行环境。可选离线工作提醒、本机文字聊天或本机图片聊天。
- 安装器按每位用户的实际路径注册 Codex hooks 和 MCP。重新安装保留档案，可从已安装的位置运行卸载脚本。
- 提供 SHA256SUMS 供校验。应用采用 ad-hoc 签名。偏好本机编译的用户可下载源码，从源码目录运行 `./install.sh --full`。

### macOS 实测

环境为 Apple M4、macOS 27.2.1 和 Codex CLI 0.171.0-alpha.13.2。使用临时用户目录和真实 Codex CLI，单独验证已打包的 arm64 应用。应用的 Mach-O 最低系统版本为 27.2。

| 项目 | 结果 |
| --- | --- |
| 空白用户安装 | 通过，首次安装前没有角色目录。预编译应用成功打开，读取内置基础图集和 109 段动作，共 1,744 帧。 |
| 工作事件 | 安装的原生 hook 接收测试事件，实际运行的桌宠依次报告思考、工作、等待审批和中断后待机。 |
| 本机推理 | 验证了首次从公开源下载引擎和文字权重，以及复用校验后的缓存安装视觉权重。文字与图片均获得本机流式回复。 |
| 升级与卸载 | 重装保留单份插件注册。用已安装的卸载器恢复原配置，独立的源码安装测试也保留了安装后另行添加的设置。 |
| 从源码安装 | 从干净的源码归档编译并安装，成功生成角色动作。 |
| 单元测试 | 28 项通过。 |

硬件实测限于 M4 和上述系统版本。此前 2.1 版的一小时运行记录见仓库内 `docs/v21-stability-summary.json`。
