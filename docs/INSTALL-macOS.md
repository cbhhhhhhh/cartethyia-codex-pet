# 安装卡提希娅桌宠 0.2.0

适用于 M 系列芯片、macOS 27.2 或更新版本，以及装有 Codex 桌面版的 Mac。查看「苹果菜单 → 关于本机」可核对系统与芯片。

1. 从 [0.2.0 发布页](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/tag/v0.2.0) 下载 `Cartethyia-Codex-Pet-macOS-arm64.zip` 并解压。
2. 双击解压目录里的 **安装.command**，选择完整安装。本地文字聊天首次约下载 1.1 GB 的 llama.cpp 与 Qwen 模型，以后可离线运行。只想看工作状态可选「仅事件」。这条安装路径也支持之后直接在设置中选用 API 或 Codex 聊天。安装到当前账户的「应用程序」，无需管理员权限。
3. 在 Codex 的「设置 → Hooks」审阅 pet-plus 的 hooks，再发一条新消息。单击卡提聊天，右键点播动作、预览配图、查询账户额度或当前任务用量。工作详情移到了右键菜单。
4. 从应用列表打开 **Codex Pet Plus** 进入设置。「聊天」可以编辑人设与禁用话题。「模型」可以分别选择聊天和碎碎念的来源。本地默认使用 Qwen2.5-1.5B-Instruct。选择 API 或 Codex 后，该通道才会向所选服务发送生成所需的数据。

可用发布页的 `SHA256SUMS` 校验压缩包。在存有两个下载文件的目录运行 `shasum -a 256 -c SHA256SUMS`。应用采用本地签名。若系统提示无法验证开发者，核对来源与校验值后，可在「系统设置 → 隐私与安全性」查看本次打开选项。也可以下载同版本源码，安装 Apple Command Line Tools 后运行 `./install.sh --full`。

## 更新、回退与卸载

直接运行新版安装器会保留角色设置和聊天。回退时从[版本列表](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases)下载所需的 Mac 安装包，退出桌宠后运行该版安装器。建议先复制 `~/Library/Application Support/CodexPetPlus/profiles/` 留存新版配置和记忆。

只想收起卡提时按 Control + Option + P。菜单栏的 ♧ 可再次显示她。完整卸载会删除桌宠、下载的模型、本地聊天与本地插件。安装器在首次改写 Codex 配置前备份原文件，卸载时保留用户后来添加的其他配置。

```sh
/bin/bash "$HOME/Library/Application Support/CodexPetPlus/installer/uninstall.sh"
```

自己保存到钥匙串的兼容 API 密钥可在「钥匙串访问」中按服务名 `local.cartethyia.petplus.api` 查找并删除。
