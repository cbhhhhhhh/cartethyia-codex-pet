# 卡提希娅codex桌宠

这是读取本机 Codex 事件的 macOS 桌面伙伴。将鼠标放在卡提身上看工作详情，右键点播动作或打开待办，单击在她头顶聊天。菜单栏 **♧** 可以找回卡提。[2.1 手势、气泡和应用入口](docs/DESKTOP-V2.1.md) · [桌宠功能清单](docs/DESKTOP-V2.md)

![卡提希娅的工作气泡](docs/v21-preview.png)

## 在另一台 Mac 上安装

需要 **M 系列芯片、macOS 27.2 或更新版本**，并已安装支持本地插件的 Codex。安装器优先使用 PATH 中的 `codex`，也能找到位于「应用程序」中的 Codex 桌面版内置 CLI。推理和工作提醒在本机运行，无需 API Key。发行包内含独立的 Python 运行环境，无需 Homebrew、Xcode 或单独安装 Python。

1. 在这个 GitHub 仓库的 **Releases → Latest** 下载 **Cartethyia-Codex-Pet-macOS-arm64.zip**（Assets 下的安装包）。解压，打开文件夹，双击 **安装.command**。
2. 回车选择文字聊天，首次下载约 1.1 GB。选 **2** 可立即安装桌宠和任务提醒，无需下载模型。选 **3** 可再安装图片聊天，总下载量约 2.7 GB。卡提基础造型和 109 个扩展动作已随包提供。
3. 打开 Codex 的 **设置 → Hooks**，审阅 `pet-plus@cartethyia-local` 的 hooks。在 Codex 新开一个本地任务，将鼠标放到卡提身上看当前工具和经过时间。单击卡提可以聊天，从「应用程序」打开 **Codex Pet Plus** 可以改人设。
4. 系统提示无法验证开发者时，此版本采用本地临时签名。也可从本仓库 **Code → Download ZIP** 下载源码，解压，在该文件夹打开终端，运行下面的源码安装命令，使用本机 Apple 开发工具编译。

从解压后的安装包或源码目录运行同一个命令。安装包直接使用预编译的 arm64 应用；源码目录使用 Apple Command Line Tools 的 Swift、Clang 和 Python 3，请先运行 `xcode-select --install` 安装开发工具。

```sh
./install.sh --events       # 角色、交互和 Codex 状态提醒
./install.sh --full         # 额外启用本地文字聊天与碎碎念
./install.sh --full --vision  # 同时安装图片理解模型
```

下载新版安装包后再次运行安装器，即可保留人设、设置和聊天记录。完整卸载可在终端运行下方命令；如需保留聊天记录，请先备份设置表中的 `profiles` 目录。

```sh
/bin/bash "$HOME/Library/Application Support/CodexPetPlus/installer/uninstall.sh"
```

## 启动和演示

```sh
open "$HOME/Applications/Codex Pet Plus.app"
```

1. 在 Codex 开一个本地任务。卡提会在思考、执行工具、检查结果时切换动作。任务成功短跳后回到待机。点击完成气泡可以回到对应的 Codex 会话。
2. 第一次安装后，到 **Codex 设置 → Hooks**，也可在 CLI 输入 `/hooks`。审阅来源为 `pet-plus@cartethyia-local`、命令为此应用内 `pet-hook` 的七项。Codex 跳过未信任的 hook，这时只读会话日志仍可显示普通回合和工具；审批提醒需要 `PermissionRequest`。安装新版本后以 Codex 展示的实际信任状态为准。[官方 hook 指南](https://learn.chatgpt.com/docs/hooks)
3. 鼠标停在角色身体上约四分之一秒，会出现工具、耗时和计划。空闲时显示空值。右键身体打开菜单。慢慢拖动或拖后稍停再松手，卡提停在释放位置。按住后快速画一个小圈，或来回摇两下，边动边松开，卡提会往随机一侧飞出并撞墙。也可以快速朝一个方向拖动后松开。双击，在第二次按下时拉开再松手，卡提向相反方向飞出。
4. 单击角色，在头顶输入框键入「记住我的猫叫雪团」并回车。回复逐字出现在头顶的插画气泡，配合情绪选取神态与随机动作。气泡有中断和回复入口。完整记录在 **右键 → 聊天记录**。首次回复需要从本地磁盘载入模型。
5. 在应用列表点带卡提头像的 **Codex Pet Plus** 即可打开设置。运行中再次点图标会将同一个设置窗口带到前台。菜单栏 **♧ → 设置** 也可以打开。调整大小、人设或动作映射后立即观察。用 **移到鼠标所在屏幕** 找回宠物。点 **启用系统通知** 可向 macOS 请求通知权限；桌宠自己的气泡可以直接工作。
6. **⌃⌥P** 唤醒或收起。在设置中可把 P 改为 K 或 J。主档案的 **⌃⌥⇧M** 切换静音，**⌃⌥⇧Q** 退出。菜单栏也有这三个操作。

完整的角色动作在 **右键 → 点播动作 → 角色包动作**，分为 13 类。发行包内附 109 段预渲染透明精灵序列，也可由浏览器舞台点播。[动作预览](docs/v2-repertoire.gif) · [动作清单](art/repertoire.json)

## 安装和回滚

安装会先备份 Codex 配置，再注册用户级本地插件。默认保留账户的内置宠物选择。如要在此 Mac 使用一键切回，并允许同步账户的宠物偏好，可在安装时显式传入 `--sync-native`。

```sh
./install.sh --full --sync-native
```

启用同步时，安装器先通过官方 Pets 接口保存当前活动宠物的稳定 ID，再选择 `default` 停用内置宠物。**♧ → 切回 Codex 内置宠物** 会恢复原 ID 并收起独立窗口；同一位置可切回独立伙伴。只有收到服务端对目标 ID 的确认，菜单才报告成功。卸载也会恢复原选择。恢复服务离线时可重新运行；若主动选择保留账户当前偏好，可用 `./uninstall.sh --local-only`。

卸载会移除此工程的应用、marketplace、插件缓存、模型运行副本以及伙伴的设置、聊天和提醒。希望保留聊天时，先复制自己的 `profiles` 目录。工程及下载缓存保留，可用于重装。安装器在变更 Codex 配置前保存原文件；若安装期间还有其他配置编辑，卸载器使用 Codex CLI 只移除本插件和本 marketplace。用户原有图集始终从原位置读取。

## 设置和文件位置

| 位置 | 内容 |
| --- | --- |
| `~/Applications/Codex Pet Plus.app` | 原生窗口、hook 发送程序、事件与聊天服务 |
| `~/Library/Application Support/CodexPetPlus/profiles/main/` | `config.json`、完整 `history.json`、最近上下文 `memory.json`、最近一次公开状态 `status.json` |
| `~/Library/Application Support/CodexPetPlus/runtime/` | 本地 llama.cpp 和 GGUF 模型 |
| `~/Library/Application Support/CodexPetPlus/backup/` | 本次安装前后的 Codex 配置快照 |
| `~/.codex/pets/<角色>/pet.json` | 用户自己的宠物描述和图集 |
| `examples/config.json` | 可阅读的默认设置样例 |

默认启用工作气泡，关闭声音、语音、碎碎念、时间和天气。开启碎碎念后默认间隔 45 分钟，22:00–08:00 安静；工作中、窗口收起、手动专注或静音时会跳过。系统朗读分别控制通知、碎碎念和待办，使用 macOS 自带语音。多轮聊天默认保存最后 10 轮，可调至 1–50 轮；模型的单次输入还受本地上下文长度约束。

**多角色。** 在设置中选择 `~/.codex/pets` 下的角色。要让两只宠物各自拥有设置和记忆，使用 **♧ → 新建独立伙伴窗口**，为新档案取独立名称。独立档案也可从终端启动：

```sh
open -na "$HOME/Applications/Codex Pet Plus.app" --args --profile knight
```

**待办和额度。** 已连接的插件提供 `pet_status`、`pet_remind`、`pet_complete`。可以明确要求 Codex「用 pet-plus 给我添加今晚 9 点的提醒」。提醒调用接收含时区的 ISO 时间和可选 thread UUID；提醒存在本地 SQLite，运行着的主伙伴每 2 秒检查，有截止时间的待办越临近提醒越密。右键「待办事项」可添加、完成、重新打开或点两次删除图标确认。Codex 的 `update_plan` 提供完成数和庆祝动作；计划缺少截止时间时不会自行估算。右键「查看额度」读取最近收到的 Codex 窗口用量快照。

**可选环境和图片。** 开启本地时间后，只给本机模型附上时刻。在「环境」填写城市并主动勾选后，生成回复或手动点「查询天气」时会将城市名和地理编码得到的坐标分别交给 Open-Meteo，失败静默，一小时内复用结果。图片理解使用可选的 Qwen3-VL-2B 本地模型。点聊天框旁的「图片」并输入问题，即可发送 PNG/JPEG（至多 8 MB）。另一台 Mac 上用 `./install.sh --full --vision` 或 `./scripts/get-vision.sh` 安装视觉权重。纯文字继续使用 Qwen2.5-1.5B；自备视觉模型也可在设置指定模型和配套投影文件。图片交给本机推理进程。已完成对话的图片按内容去重，保存在当前档案的 images 目录，历史记录里可以查看。删除最后一个引用某张图片的轮次会一并清理该图片。

## 故障排查

| 现象 | 检查 |
| --- | --- |
| 菜单栏有 ♧，找不到卡提 | 唤醒 → 设置 → 移到鼠标所在屏幕。检查所选包和图集尺寸。 |
| 普通任务会动，审批无提醒 | 审阅本插件的 `PermissionRequest` hook。正在执行的工作是否确实产生了审批请求，也取决于 Codex 的权限模式。 |
| 没有工作事件 | 检查本机 `~/.codex/sessions` 是否写入；桌宠启动后只回放新事件。远端主机的会话需要在相应主机提供事件。 |
| 短暂显示超时然后待机 | 真正的工具或模型超过 120 秒没有新信号时会收敛；审批上限 300 秒。后续真实事件可恢复状态。 |
| 聊天无法启动 | 检查当前安装阶段和模型文件。将设置中的模型名恢复为样例值。终端不要传任何云服务密钥。 |
| 系统通知或语音没声音 | 在桌宠设置请求通知授权，核对 macOS 通知设置、静音、对应播报开关和音量。 |
| 一键切回不可用 | 需要已登录的 Codex、已连接的 Pets 以及安装时授权 `--sync-native`。官方接口异常时保留当前模式。 |
| 快捷键冲突 | 更换唤醒键。多个伙伴使用不同唤醒键，静音和退出组合键由主档案注册。 |

## 验证

维护者可重新生成 arm64 安装包；构建脚本校验便携 Python 归档的固定 SHA-256。第二条命令从 ZIP 在空白 HOME 中安装，用真实 Codex CLI 注册插件，检验工作状态转换、随包动作、重复安装和卸载。加 `--full` 会校验完整的本机模型安装与推理。

```sh
./scripts/package-macos.sh
/usr/bin/python3 -B tests/release-install.py --full
(cd dist && shasum -a 256 -c SHA256SUMS)
```

```sh
/usr/bin/python3 -B -m unittest discover -s tests
./scripts/test-native.sh --preview
/usr/bin/python3 -B tests/installed-v2.py
python3 -B tests/browser.py
python3 -B tests/artwork.py
/usr/bin/python3 -B tests/integration.py
/usr/bin/python3 -B tests/conversation.py
/usr/bin/python3 -B tests/conversation.py --whisper
/usr/bin/python3 -u scripts/soak.py 3600 --output .build/my-soak.json
```

原生测试在临时目录创建真实 AppKit 窗口，包含实际 Codex CLI、仅监听回环地址的测试模型服务和本地会话日志。长稳测试按实际墙钟时间采样已安装的桌宠。本版验收记录见 [2.1 验收报告](docs/DESKTOP-V2.1.md)，手测操作见 [手工清单](docs/MANUAL-QA.md)。接口依据和模块见 [架构](ARCHITECTURE.md)，素材与依赖见 [NOTICE](NOTICE)。
