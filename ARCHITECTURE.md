# 架构与本机勘察

## 2.3.0 的事件归属与计量

本地 hook 经带令牌的 Unix datagram 发送最小事件。Codex 插件没有订阅桌面客户端所有会话的接口。独立启动的 app-server 能看见它自己发起的回合，其他 Codex 客户端由本机只读 JSONL 观察器补全。观察器在文件末尾接续，首先验证 `session_meta` 的身份、父会话和继承边界。真实分叉会用新的时间戳重写继承记录，因此须按 `subagent_history_start_ordinal` 跳过前缀。

`src/state.py` 的 reducer 使用 `(thread, turn)` 作为主键。计划完成、Stop 尝试、单个工具失败分别按进度、检查、工具结果处理。主回合的终止记录才能产生完成或失败通知。子回合独立记账，活跃主任务优先显示。排队的气泡带回合身份与到期时间，新回合会撤销上轮尚未展示的完成气泡。

`src/usage.py` 在每个档案保存最小的 `usage.json`。将相邻的官方累计样本相减，可以去除重复更新和同一会话的历史消耗。父子关系必须有会话和回合的证据。没有可靠起点时只展示已观测用量。读取账户额度使用 `account/rateLimits/read`，按会话读取积分和金额使用 `account/usage/read`。微单位除以一百万。缺少本回合起止估值时只展示官方给出的整条会话累计。账户百分比与单次任务无法直接换算。

## 角色动作、配图与模型

参照的 dsh-pet 为许多动作分别提供 WebM，例如抛球、下棋和吃月饼。播放控制器会等待下一段素材准备好再换源，同时管理循环与一次性播放。它的聊天通过宿主按 provider 和 model 选择服务。Mac 版沿用分动作制作素材和按通道选择模型的设计，使用 Cartethyia 自己的透明帧条以及本地、API、Codex 三种线路。[上游动画控制器](https://github.com/PC2005-cloud/dsh-pet/blob/fb38ce620576f5ed3735a99536d2b1a4a9eb313f/dsh-pet/src/client/pet/animation/animation.ts) · [上游模型选择](https://github.com/PC2005-cloud/dsh-pet/blob/fb38ce620576f5ed3735a99536d2b1a4a9eb313f/dsh-pet/src/host/chat.ts)

- `art/performances/` 包含 109 个独立 WebP 帧条及清单。每段有四个独立绘制的姿势，过渡和停顿在制作时烘焙。AppKit 解码成功后切换片段，Core Animation 在一个图层上切换当前帧的矩形区域，窗口隐藏时移除动画。写字和书法片段保持原方向，带 `travel` 的点播动作同时改变窗口位置。自定义角色包的清单优先于随应用分发的清单，旧版自动生成缓存排在最后。
- `src/web/gallery.json` 为十张配图提供名称、表情和描述，另可从当前档案的 `stickers/` 读取本地 PNG/JPEG。点击配图会锁定资源 ID，将允许的描述交给碎碎念模型。普通聊天、连续配图和显式回看使用不同选择条件。历史保留实际展示的图和动作。
- `src/pet_response.py` 负责统一组装人设、允许的短期上下文和动作请求。`src/dialogue.py` 负责禁谈规则、图库和动作名。明确的天气、地名、禁用词规则存在时，先过滤环境与记忆，再检查整句并在必要时重写一次。仍不合规时从本机选择符合规则的短句。系统 Natural Language 实体识别为地名规则补充检测，一般性文风仍由所选模型实现。
- `src/providers.py` 支持本地 llama.cpp、兼容 Chat Completions 的 SSE，以及登录 Codex 的临时、只读 app-server 回合。后者使用空工作目录、隔离线程、受限工具和独立会话标记。正常工作计量排除桌宠模型线程。外部 API 的凭据通过指定环境变量或按服务原点隔离的 macOS 钥匙串条目读取；服务连接测试仅读取模型列表。

## 桌面交互 2.1

角色窗口和卡片分别由 AppKit 管理。角色按图集像素透明度接受指针事件。鼠标悬停只改变视线。右键打开工作详情、当前任务用量或待办，单击角色打开输入框。这些内容和回复共用贴在角色窗口上的面板。卡片优先放在角色上方，到达屏幕顶边时放在下方。聊天记录和设置各自有可聚焦的常规窗口。

拖动时记录屏幕坐标。最多保存 750 毫秒的轨迹，通过路径长度、轨迹跨度、首尾距离和速度识别快速画圈或来回摇动，赋予随机左右方向和上扬初速。直线甩出使用最近 170 毫秒的速度；静止 180 毫秒后释放会保存当前位置。双击拖动使用拉距决定反方向初速。飞行期间积分重力、墙面法向反弹、地面阻力。多个本机档案通过带 token 的 Unix 数据报广播位置和碰撞冲量。

broker 保存每个档案的完整历史，再从中截取模型上下文。图片在档案中按内容摘要保存。可选网页舞台和本机脚本接口由 broker 按需启动，使用单独的临时 Bearer token、回环地址和同源限制。渲染层只能触发预定义操作。安装器先验证独立应用签名，通过临时目录替换旧应用，去除早期备份的应用注册后将正式版注册到 Launch Services。安装前的 Codex 配置快照继续用于卸载恢复。模块和接口细节见 [2.0 交互与接口](docs/DESKTOP-V2.md)。

气泡使用带定位指尖的 SwiftUI 形状、系统中文娃娃体及圆体。卡提使用十张本地透明插画，其他角色从各自图集取帧。一次回复确定情绪和动作，增量字符只更新文字。普通启动和系统重新打开事件显示设置，后台安装和附加档案使用显式参数。[2.1 画圈与气泡验收](docs/DESKTOP-V2.1.md)

## 本机边界

| 勘察对象 | 结果与工程决定 |
| --- | --- |
| ChatGPT.app、Codex CLI | 初次勘察使用桌面版 26.1117.41037、CLI 0.171.0-alpha.13。2.3.0 的真机测试使用桌面版 26.1120.50957、CLI 0.171.0-alpha.13.2，bundle ID 为 `com.openai.codex`。接口以 CLI 生成的 app-server JSON Schema 与实际请求核对。安装写入用户目录，独立桌宠使用 ad hoc 签名。 |
| `~/.codex/config.toml` | 已有官方 marketplace、多个已启用插件，以及带环境配置的 MCP。工程用 CLI 加入独立 `cartethyia-local` marketplace，保留原设置。 |
| 官方插件 manifest | `browser`、`chrome`、`unified-computer-use` 含 Stop、Interrupt、SubagentStop。`codex-app-tools` 等声明本地 MCP。插件支持 skills、命令 hooks、stdio MCP 以及客户端承载的应用内容。当前公开协议没有注册系统级、可拖动且每像素穿透的原生桌宠窗口的 API。 |
| app-server 和 IPC | 公共协议提供回合、item、审批以及 `account/rateLimits/read`；审批是发给负责会话的客户端的请求。存在权限为用户私有的 `~/.codex/ipc/ipc.sock`，未发现对第三方保证的全桌面只读广播契约。工程对自己负责的公有协议请求使用 stdio，观察已有桌面任务采用 hook 与只读日志。 |
| 用户图集 | 包声明 `spriteVersionNumber: 2`。读取真实 WebP，按每格 192×208 取前九行动画。兼容 1536×1872 和 1536×2288；v2 末两行的方向素材保留在原包，本窗口使用前九行。 |
| dsh-pet | 本机 0.4.9。只读勘察了 work-status、whisper-policy、persona、setup、chat、todo、balance 和客户端 motion/chat/settings，并对照本地配置和记忆文件的结构。工程使用独立实现，未导入 DSH 的记忆、角色设定、图像或音频。 |

可机读现场摘要见 [host-audit.json](docs/host-audit.json)。官方行为参考 [Hooks](https://learn.chatgpt.com/docs/hooks)、[应用深链接](https://learn.chatgpt.com/docs/reference/commands)、[App Server](https://developers.openai.com/codex/app-server/)。

## Hook 与事件契约

本机 `HooksListResponse.HookEventName` 有 14 种事件。模型请求前后为 PreModelRequest、PostModelRequest，工具前后为 PreToolUse、PostToolUse，授权为 PermissionRequest。其余为 PreCompact、PostCompact、SessionStart、SessionEnd、UserPromptSubmit、SubagentStart、SubagentStop、Stop、Interrupt。此版本没有 Notification hook。完整输入由 JSON 经 stdin 传入；公共字段包括 `session_id`、`hook_event_name`、`transcript_path`、`cwd`、`model`，回合及工具事件的专有字段按实际事件选择。大多数 hook 默认超时 600 秒，Interrupt 与 SessionEnd 默认 1 秒、最多 3 秒。本插件声明异步命令和 1 秒上限。发送器只提取最小字段，非阻塞投递后退出 0。它没有权限批准、拒绝或续跑任务。[官方输入、后台运行与超时说明](https://learn.chatgpt.com/docs/hooks)

```text
Codex 七项官方 hook → pet-hook → 带短期 token 的 Unix datagram ┐
本地 rollout JSONL → 只读增量解析、过滤历史及重复事件         ├→ 单一 Reducer → 管道 → AppKit 浮窗
Codex 的 update_plan、使用量快照 → 可用时显示详情             │
本地 stdio MCP → SQLite 到期待办 → 提醒及庆祝                 ┘
窗口聊天或定时闲聊 → 本机 llama-server → 结构化流式文字、情绪和动作
```

事件版本 `v=1`。包内保留 thread、turn、kind、call、tool、source 等字段。每次运行重建认证 token，Unix socket 及本地数据目录仅所属用户可读写。hook 忽略过大的 stdin，不保存 prompt、工具参数或输出。macOS 通过 kqueue 的 vnode 写入和目录变更事件通知尾读器，空闲期间无需反复遍历会话树。单实例最多监视 2,048 个路径，超过上限、目录尚未创建或系统缺少 kqueue 时回退到增量轮询。JSONL 尾读器从 EOF 开始，只投影相关事件；恢复旧会话时可以向前找最近的 turn ID，旧对话不会触发动画。JSONL 是兼容层，Codex 更新后可通过本机真实 CLI 测试发现字段变化。

## 状态、绘制与故障恢复

| 真实信号 | 工作状态 | 默认图集行 |
| --- | --- | --- |
| UserPromptSubmit / task_started | thinking | review |
| PreToolUse / function_call | working | running |
| PermissionRequest | waiting-for-approval | waiting |
| PostToolUse / tool output | 其他工具仍在执行则 working，余下无工具则 thinking | running / review |
| 最终答复阶段 | review | review |
| Stop | 短暂检查，后续工具可以继续推进同一回合 | review |
| SubagentStop | 主回合状态由主线程自己的事件决定 | 保持当前工作动画 |
| task_complete | success 约 0.55 秒，随后 idle | jumping → idle |
| Interrupt / turn_aborted | idle | idle |
| 回合 error | error 约 0.55 秒，随后 idle | failed → idle |

每个 thread/turn 独立归约，同时显示优先级最高的活动状态。审批优先于普通运行，终止回合有有限去重缓存，迟到的工具结果不会复活已结束回合。PermissionRequest 可以不含 call ID；有身份的请求按调用匹配，其余按官方工具名与后续结果关联。工具失败与回合失败分别处理，一个非零工具结果仍可由 Codex 继续修复。并行工具各有 call ID；已经完成的 call 去重。无权威状态时回到 idle。120 秒无新事件触发超时，审批上限 300 秒。broker 每 2 秒发本地心跳，原生窗口监视其退出与心跳超时并重启服务。

AppKit 的 LSUIElement 应用包含透明无边框 NSPanel、菜单栏入口和 Carbon 全局快捷键。绘图复用 ImageIO 剪出的帧和 alpha 掩模，光标处的透明度决定窗口是否忽略鼠标事件。使用仅鼠标移动的 AppKit 监听，未采集键盘输入；监听不可用时回退到命中测试定时器。拖动使用 AppKit 屏幕坐标，按显示器的可用工作区限制位置；重力 1400 点/s²、弹性 0.78、地面摩擦 2.5、甩出速度倍率 1。Retina 缩放由系统处理。每次甩动单独启动 60 Hz 定时器，停稳即销毁。窗口收起暂停绘图和命中测试；后台仍接收工作通知。

## 聊天与数据

窗口和 broker 使用继承的进程管道。选择本地模型时，每次推理在临时的 127.0.0.1 端口启动 llama.cpp，使用随机 token 与仅所属用户可读的临时 key 文件。生成结束或中断时释放模型进程。默认模型是 Qwen2.5-1.5B-Instruct Q4_K_M。模型按 JSON Schema 返回文字、emotion、action，文字逐步解码，两者组合选择兼容动作。完整回复才进入记忆。清空或取消使旧流失效，避免迟到的字符重新出现。默认不调用云端模型。模型推理使用的统一内存要单独计算，超过 200 MB。

主档案接收 hook、待办及日志。额外档案独立持有设置、记忆、窗口和日志观察器。主服务会经私有 socket 向运行中的其他档案转发已验证的 hook，包括审批事件。主伙伴退出后，额外档案继续使用只读日志。工作聊天内通过标准 deep link 跳到经过 UUID 校验的 thread。同步内置宠物只在显式授权的安装、切换或卸载时运行，调用官方 app-server 的 `mcpServer/tool/call` 和 `pets.select_pet`。使用临时本地会话承载 MCP，不启动模型回合。需要恢复的 ID 存于用户私有目录。

天气默认关闭；选择开启后使用 Open-Meteo 城市搜索和当前天气，缓存一小时。设置中的专注开关以及真实工作状态会抑制碎碎念。系统通知授权、系统朗读、额度快照、可选图像理解各自独立。用户发送的图片经校验后保存在相应档案，删除最后一条引用它的记录时同步清理。[Open-Meteo 接口](https://open-meteo.com/en/docs)

## 源码入口

- `src/state.py` 管理工作状态和空闲策略；`src/observe.py` 读取本地事件；`src/hook.m` 发送最小事件。
- `src/broker.py` 串行协调事件、聊天取消、持久化和通知；`chat.py` 管理推理进程，`weather.py` 管理城市缓存。
- `src/Host.swift` 管理原生应用、输入、物理和菜单；`Companion.swift` 管理配置、图集、聊天与设置视图。
- `src/mcp.py`、`reminders.py` 提供本地工具和提醒存储，`preference.py` 负责授权后的账户宠物选择。
- `scripts/plugin.py` 根据每台 Mac 的安装位置生成本地 marketplace、hooks、MCP 清单和 skill。GitHub Release 分发 arm64 应用和安装器。角色基础图集和预渲染动作随应用提供，同名用户角色包可覆盖默认资源。

本机通过 Apple SDK 确认存在 Focus Status API，自动读取需要应用能力和用户授权，当前独立本地签名版提供手动专注开关并在真实工作期间抑制碎碎念。[Apple 对 Focus 授权和应用能力的说明](https://developer.apple.com/documentation/UserNotifications/handling-communication-notifications-and-focus-status-updates)
