# Windows 构建与接口

Windows 0.2.0 沿用 0.1.0 移植，使用 v0.2.0 标签所在合并提交的动作与插画。macOS 应用继续使用原有 AppKit、Swift 构建脚本和发行流程。Windows 版本使用 PySide6、Win32 分层窗口、当前用户命名管道与 Inno Setup。

## 在开发机生成安装包

使用原生 x64 Windows、Python 3.13、curl.exe、Windows 自带 .NET Framework 4.x 的 C# 编译器，以及 Inno Setup 6。构建脚本从 PATH 或当前用户 Programs/Inno Setup 6 寻找 ISCC.exe。在仓库根目录运行以下命令。

```powershell
python windows/build.py
Get-FileHash .\dist\Cartethyia-0.2.0-Windows-x64-Setup.exe -Algorithm SHA256
```

构建脚本固定 CPython 3.13.9 x64 embeddable、PySide6 Essentials 6.9.3、shiboken6 6.9.3 的归档摘要。构建脚本从仓库的 art/performances/pet-plus.json 与 art/repertoire.json 核对动作标题、109 条 WebP 路径和每条 24 帧的声明，复制当前插画及说明。中文地名表取自固定 SHA-256 的 jieba 词典，附带 MIT 许可。构建目录按应用版本隔离。生成的安装包附带图集、插画、动作、图标及运行环境。可选模型和 llama.cpp 引擎通过 Windows 设置页按需获取，版本和哈希在 model_store.py 中。源码署名见 NOTICE 和 windows/THIRD-PARTY.txt。

## 工作与聊天

本机 Codex CLI 的 `HooksListResponse` 架构列出 14 种事件。Windows 插件注册其中七种，分别为 `UserPromptSubmit`、`PreToolUse`、`PostToolUse`、`PermissionRequest`、`Stop`、`Interrupt`、`SubagentStop`。同一架构还列出模型请求前后、压缩前后、会话开始和结束、子代理启动七种事件。一次回合可能只发送其中一部分，验收报告记录了每个真实回合实际收到的事件。

- Windows 角色窗口和独立气泡运行于登录用户的图形会话。鼠标在分层 HWND 上按 alpha 命中。Qt 提供逻辑坐标和每显示器缩放，Win32 注册全局快捷键。重复启动通过用户管道请求已有进程将设置置前。每个档案使用独立的进程锁。
- 安装器通过 Codex CLI 增删 pet-plus@cartethyia-windows-local。服务在更改前备份当前配置并核对来源。Windows hook 调用使用当前环境的 PowerShell 命令形式，发送器仅投递规范化事件。接收端和本地档案目录的 DACL 限定为当前用户。审批决定留给 Codex 的会话客户端。
- core.py 将官方 hook、rollout 增量记录和本机分页历史的活动条目交给 src/state.py。observe.py 解析 rollout。events.py 使用 Windows 目录变化通知，并以只读 SQLite 连接投影回合状态及工具标识。SQLite 表结构和 JSONL 字段属于本机兼容路径。优先从 thread 的来源、父 ID、回合归属与 subagent_history_start_ordinal 识别继承记录，后续时间戳不改变其归属。Stop 和 SubagentStop 只作辅助信息。Windows 额外检查 task_complete 携带的 error。启动从现有尾部起读。无信号、回合超时、审批超时均会收敛到待机。
- 桌面协调逻辑在 windows/app.py。Mac broker.py 的 Unix 数据报、Objective-C hook、launchd 和应用内 Unix 执行路径由 Windows 管道、独立窗口应用、嵌入式 Python 和 Inno Setup 替代。待办和对话沿用 src/reminders.py、archive.py、chat.py、weather.py。聊天进程按请求启动，监听临时回环端口，用私有临时文件传递随机密钥。
- 已提交的 Windows 安装脚本按内容哈希检查运行库，升级时可跳过相同文件。升级与卸载识别本项目安装路径和 MCP 服务命令，关闭关联的 stdio 助手。升级失败回滚时，安装器会尝试重新启动已有桌宠。

## 复验入口

`windows/qa_turns.py` 使用本机真实 Codex app-server 发起回合。`qa_transition.py` 在已安装代码上记录实际绘制切换，用测试线程 ID 排除同时运行的其他 Codex 工作。测试专用的 `--review-project-hooks` 核对安装内容后，仅在该验收进程中采用本项目七项定义的当前哈希。

`qa_widgets.py` 使用已安装的 Qt 组件，测试轨迹、菜单、设置、文字与图片回复及中断。`qa_hit.py` 检查实际窗口命中、底层按钮和 DACL。`qa_desktop.py` 需要已解锁桌面，在专用测试档案上投递系统鼠标输入。`qa_geometry.py` 可配合 QT_SCALE_FACTOR 复验缩放。`qa_soak.py PID 输出目录` 按墙钟每 30 秒采样，默认持续 3,600 秒；它记录常驻进程的 CPU 时间、工作集及采样时存在的子进程。验收工具依各自用途使用 psutil、pywin32、pywinauto，桌宠安装包本身附带其所需依赖。

## 0.2.0 验收入口

安装版测试与采样结果列在版本化报告中。所有账户探测只提交合成题，兼容 API 回归使用本机回环服务。[Windows 0.2.0 实测](QA-WINDOWS-0.2.0.md)

| 入口 | 用途 |
| --- | --- |
| `windows/qa_upgrade.py 输出目录 --upgrade-user` | 先备份和检验隔离安装、升级、回退、卸载，再升级当前用户实际安装。需先在 dist 准备发行过的 0.1.0 EXE。 |
| `qa_family.py`、`qa_transitions_isolated.py`、`qa_ownership.py` | 两个真实子任务和并行主回合，四种回合到首次绘制的延迟，以及三种事件来源、通知排队、归属和费用差值。 |
| `qa_routes.py`、`qa_account_fields.py`、`qa_memory.py` | 三条线路的禁谈和点播、官方账户字段、两个进程间的十轮上下文及清空。 |
| `qa_art.py`、`qa_widgets.py`、`qa_geometry.py`、`qa_native_motion.py` | 安装目录的全部实际帧、气泡、鼠标消息、不同 DPI 与模拟双屏。 |
| `qa_idle.py`、`qa_inference.py`、`qa_soak.py PID 输出目录 --installer EXE --probes` | 分别测量独立待机窗口、完整 CPU/Vulkan 回复、指定安装 PID 连续 3,600 秒和五次真实账户响应。 |

Qt 界面测试请使用安装目录的 `runtime/python.exe -X utf8 -B`；依赖 psutil、pywin32 的采样和 Win32 输入脚本使用开发机 Python。测试脚本的 `install` 参数是含 Cartethyia.exe 的安装目录。Mac 的构建与发布命令继续见原有文档。

在仓库根目录可用以下命令重跑真实父子任务及三种聊天线路。两个脚本创建临时工作目录和合成问题，复用当前用户的官方登录以及本机已校验的模型。

```powershell
$appDir = Join-Path $env:LOCALAPPDATA 'Programs/CartethyiaPet'
$qtPython = Join-Path $appDir 'runtime/python.exe'
$outDir = New-Item -ItemType Directory -Force '.build/check-windows'
& $qtPython -X utf8 -B windows/qa_family.py $appDir "$outDir/family.json"
& $qtPython -X utf8 -B windows/qa_routes.py $appDir "$outDir/routes.json"
python -X utf8 -B windows/qa_transitions_isolated.py $appDir "$outDir/turns"
```

对一小时测试，使用主档案的实例锁取得真正绘制窗口的 PID，再传入同一安装包。五次探测各自建立隔离的官方算术回合。

```powershell
$lock = Join-Path $env:LOCALAPPDATA 'CartethyiaPet/instance-main.lock'
$guiProcessId = [int](Get-Content $lock -TotalCount 1)
python -X utf8 -B windows/qa_soak.py $guiProcessId "$outDir/soak" --installer '.\dist\Cartethyia-0.2.0-Windows-x64-Setup.exe' --probes
```

多显示器复测使用 `windows/qa_monitors.json` 描述的 100% 主屏与左侧 150% 副屏。开发环境使用同版 PySide6 Essentials 的 platforms 插件目录设置 `QT_QPA_PLATFORM_PLUGIN_PATH`，再以 `QT_QPA_PLATFORM=offscreen:configfile=windows/qa_monitors.json` 运行 `qa_geometry.py`。单屏实测使用 Windows 原生 qwindows 后端，用 `QT_SCALE_FACTOR` 组合四种有效缩放。最终用户安装仅需原生 Windows 插件。
