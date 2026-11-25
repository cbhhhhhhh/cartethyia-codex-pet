# 卡提希娅codex桌宠 · Mac 安装说明

适用于 M 系列芯片、macOS 27.2 或更新系统。请先在这台 Mac 安装支持本地插件的 Codex。官方桌面版内置的命令行工具即可使用。

1. 解压完整个文件夹，双击「安装.command」。不要单独移动 payload 里的应用。
2. 直接回车安装本地文字聊天；输入 2 安装离线桌宠与工作提醒；输入 3 同时安装图片理解。程序会放到当前用户的「应用程序」文件夹。安装不需要管理员权限。
3. 在 Codex 的「设置 → Hooks」审阅 pet-plus 的 hooks，然后新建一个本地任务。悬停卡提能看到工作的工具和耗时；单击打开聊天；右键可以点播动作、查看待办。从「应用程序」打开 Codex Pet Plus 可以调整人设、模型和外观。

模型从 llama.cpp 的 GitHub Release 与 Qwen 的 Hugging Face 仓库下载。默认文字模式约下载 1.1 GB；加上图片模型约 2.7 GB。模型下载完即可在本地运行。安装包已包含角色、109 段动作和 Python 运行环境。个人聊天、偏好和记忆保存在本机。

系统提示无法验证开发者时，也可从项目仓库的 Code → Download ZIP 取得源码。安装 Apple Command Line Tools（终端运行 xcode-select --install）后，在解压后的源码目录运行 ./install.sh --full 进行本机编译。

## 更新和卸载

打开新版的安装器即可更新，现有设置和聊天会保留。需要备份档案时，复制 ~/Library/Application Support/CodexPetPlus/profiles/ 即可。

在终端执行下方命令卸载桌宠、模型、聊天记录和本地插件。安装器会在首次改动 Codex 配置前备份原文件，卸载时保留后续添加的其他配置。

```sh
/bin/bash "$HOME/Library/Application Support/CodexPetPlus/installer/uninstall.sh"
```

如果只想收起卡提，按 Control + Option + P。菜单栏的 ♧ 可以找回她。
