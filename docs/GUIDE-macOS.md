# macOS 使用手册

单击卡提打开头顶输入框，右键查看工作详情或点播动作。需要安装或卸载时请参阅[安装手册](INSTALL-macOS.md)。

## 启动和演示

```sh
open "$HOME/Applications/Codex Pet Plus.app"
```

1. 在 Codex 开一个本地任务。卡提会在思考、执行工具、检查结果时切换动作。主回合结束时播放庆祝，随后回到待机。点击完成气泡可以回到对应的 Codex 会话。
2. 第一次安装后，到 **Codex 设置 → Hooks**，也可在 CLI 输入 `/hooks`。审阅来源为 `pet-plus@cartethyia-local`、命令为此应用内 `pet-hook` 的七项。Codex 跳过未信任的 hook，这时只读会话日志仍可显示普通回合和工具；审批提醒需要 `PermissionRequest`。安装新版本后以 Codex 展示的实际信任状态为准。[官方 hook 指南](https://learn.chatgpt.com/docs/hooks)
3. 鼠标经过角色时桌面保持安静。右键身体打开菜单，点「工作详情」可持续查看工具、耗时和计划。慢慢拖动或拖后稍停再松手，卡提停在释放位置。按住后快速画一个小圈，或来回摇两下，边动边松开，卡提会往随机一侧飞出并撞墙。也可以快速朝一个方向拖动后松开。双击，在第二次按下时拉开再松手，卡提向相反方向飞出。
4. 单击角色，在头顶输入框键入「记住我的猫叫雪团」并回车。回复出现在头顶气泡中。未开启禁谈规则时可看流式文字，严格模式会先检查整句。气泡有中断和回复入口。完整记录在 **右键 → 聊天记录**。首次回复需要从本地磁盘载入模型。
5. 在应用列表点带卡提头像的 **Codex Pet Plus** 即可打开设置。运行中再次点图标会将同一个设置窗口带到前台。菜单栏 **♧ → 设置** 也可以打开。调整大小、人设或动作映射后立即观察。用 **移到鼠标所在屏幕** 找回宠物。点 **启用系统通知** 可向 macOS 请求通知权限；桌宠自己的气泡可以直接工作。
6. **⌃⌥P** 唤醒或收起。在设置中可把 P 改为 K 或 J。主档案的 **⌃⌥⇧M** 切换静音，**⌃⌥⇧Q** 退出。菜单栏也有这三个操作。

完整的角色动作在 **右键 → 点播动作**，分为 13 类。发行包内附 109 段预渲染透明精灵序列，也可由浏览器舞台点播。[0.2.0 动作预览](qa/0.2.0/actions.gif) · [动作清单](../art/repertoire.json)

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
| `~/Library/Application Support/CodexPetPlus/profiles/main/` | `config.json`、完整 `history.json`、最近上下文 `memory.json`、工作状态 `status.json`、回合用量 `usage.json`、最近点播 `interaction.json` |
| `~/Library/Application Support/CodexPetPlus/runtime/` | 本地 llama.cpp 和 GGUF 模型 |
| `~/Library/Application Support/CodexPetPlus/backup/` | 本次安装前后的 Codex 配置快照 |
| `~/.codex/pets/<角色>/pet.json` | 用户自己的宠物描述和图集 |
| `examples/config.json` | 可阅读的默认设置样例 |

默认启用工作气泡，关闭声音、语音、碎碎念、时间和天气。开启碎碎念后默认间隔 45 分钟，22:00–08:00 安静；工作中、窗口收起、手动专注或静音时会跳过。系统朗读分别控制通知、碎碎念和待办，使用 macOS 自带语音。多轮聊天默认保存最后 10 轮，可调至 0–50 轮；模型的单次输入还受本地上下文长度约束。

自动碎碎念和手动点配图都由当前碎碎念模型现场生成。如果连续两次生成都触犯禁谈规则，卡提会选一句符合当前规则的本地短句。点播动作有单独编写的台词，跟着动作节拍出现。

**多角色。** 在设置中选择 `~/.codex/pets` 下的角色。要让两只宠物各自拥有设置和记忆，使用 **♧ → 新建独立伙伴窗口**，为新档案取独立名称。独立档案也可从终端启动：

```sh
open -na "$HOME/Applications/Codex Pet Plus.app" --args --profile knight
```

**待办和额度。** 已连接的插件提供 `pet_status`、`pet_remind`、`pet_complete`。可以明确要求 Codex「用 pet-plus 给我添加今晚 9 点的提醒」。提醒调用接收含时区的 ISO 时间和可选 thread UUID；提醒存在本地 SQLite，运行着的主伙伴每 2 秒检查，有截止时间的待办越临近提醒越密。右键「待办事项」可添加、完成、重新打开或点两次删除图标确认。Codex 的 `update_plan` 提供计划进度，全部打勾后仍以主回合真实结束事件触发庆祝。

**可选环境和图片。** 开启本地时间后，给所选通道附上时刻。在「环境」填写城市并主动勾选后，明确询问天气或手动点「查询天气」时会将城市名和地理编码得到的坐标分别交给 Open-Meteo，失败静默，一小时内复用结果。图片理解使用可选的 Qwen3-VL-2B 本地模型。点聊天框旁的「图片」并输入问题，即可发送 PNG/JPEG（至多 8 MB）。另一台 Mac 上用 `./install.sh --full --vision` 或 `./scripts/get-vision.sh` 安装视觉权重。纯文字继续使用 Qwen2.5-1.5B；自备视觉模型也可在设置指定模型和配套投影文件。选择本地线路时图片交给本机推理进程，主动选用的网络线路将图片提交给相应服务。已完成对话的图片按内容去重，保存在当前档案的 images 目录，历史记录里可以查看。删除最后一个引用某张图片的轮次会一并清理该图片。

## 故障排查

| 现象 | 检查 |
| --- | --- |
| 菜单栏有 ♧，找不到卡提 | 唤醒 → 设置 → 移到鼠标所在屏幕。检查所选包和图集尺寸。 |
| 普通任务会动，审批无提醒 | 审阅本插件的 `PermissionRequest` hook。正在执行的工作是否确实产生了审批请求，也取决于 Codex 的权限模式。 |
| 没有工作事件 | 检查本机 `~/.codex/sessions` 是否写入；桌宠启动后只回放新事件。远端主机的会话需要在相应主机提供事件。 |
| 短暂显示超时然后待机 | 真正的工具或模型超过 120 秒没有新信号时会收敛；审批上限 300 秒。后续真实事件可恢复状态。 |
| 本地聊天无法启动 | 在「设置 → 模型」核对 GGUF 文件名。仅事件安装可再运行 `./install.sh --full` 补上默认本地模型。 |
| API 或 Codex 模型无法连接 | API 可在「设置 → 模型」点「测试 API 连接」并核对基址和凭据。Codex 可点「读取可用模型」，检查登录状态与该账户可用的型号。 |
| 任务已有 token，金额仍显示「暂未提供」 | token 来自本机回合记录。金额需要官方服务针对这条会话返回数据。若只返回会话累计，可在「设置 → 桌面」启用起止读取，再观察下一轮的估算增量。 |
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
./scripts/test-native.sh
/usr/bin/python3 -B tests/installed-v2.py
python3 -B tests/browser.py
python3 -B tests/artwork.py
/usr/bin/python3 -B tests/integration.py
/usr/bin/python3 -B tests/conversation.py
/usr/bin/python3 -B tests/conversation.py --whisper
/usr/bin/python3 -u scripts/soak.py 3600 --output .build/my-soak.json
```

原生测试在临时目录创建真实 AppKit 窗口，包含实际 Codex CLI、仅监听回环地址的测试模型服务和本地会话日志。长稳测试按实际墙钟时间采样已安装的桌宠。维护者显式加 `--account` 可以运行 `tests/macos-live-turns.py` 和 `tests/macos-model-routes.py`，两者均要求 `--output` 指定本地结果文件，发送的是专用测试提示，会使用当前 Codex 账户的额度。[0.2.0 实测](QA-0.2.0.md) · [手工清单](MANUAL-QA.md) · [架构及接口依据](../ARCHITECTURE.md) · [素材与依赖](../NOTICE)
