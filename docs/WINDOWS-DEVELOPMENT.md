# Windows 构建与接口

本移植以仓库 main 的 3fc5934 和 v2.2.0 发行素材为基准。macOS 应用继续使用原有 AppKit、Swift 构建脚本和发行流程。Windows 版本使用 PySide6、Win32 分层窗口、当前用户命名管道与 Inno Setup。

## 在开发机生成安装包

使用原生 x64 Windows、Python 3.13、curl.exe、Windows 自带 .NET Framework 4.x 的 C# 编译器，以及 Inno Setup 6。构建脚本从 PATH 或当前用户 Programs/Inno Setup 6 寻找 ISCC.exe。在仓库根目录运行以下命令。

```powershell
python windows/build.py
Get-FileHash .\dist\Cartethyia-2.2.0-Windows-x64-Setup.exe -Algorithm SHA256
```

构建脚本固定 CPython 3.13.9 x64 embeddable、PySide6 Essentials 6.9.3、shiboken6 6.9.3 的归档摘要。它验证 v2.2.0 的 SHA256SUMS，并用清单校验 Mac ZIP，再从应用 Resources/pets/cartethyia 提取预渲染素材。生成的安装包附带图集、插画、动作、图标及运行环境。可选模型和 llama.cpp 引擎通过 Windows 设置页按需获取，版本和哈希在 model_store.py 中。源码署名见 NOTICE 和 windows/THIRD-PARTY.txt。

## 工作与聊天

- Windows 角色窗口和独立气泡运行于登录用户的图形会话。鼠标在分层 HWND 上按 alpha 命中。Qt 提供逻辑坐标和每显示器缩放，Win32 注册全局快捷键。重复启动通过用户管道请求已有进程将设置置前。每个档案使用独立的进程锁。
- 安装器通过 Codex CLI 增删 pet-plus@cartethyia-windows-local。服务在更改前备份当前配置并核对来源。Windows hook 调用使用当前环境的 PowerShell 命令形式，发送器仅投递规范化事件。接收端和本地档案目录的 DACL 限定为当前用户。审批决定留给 Codex 的会话客户端。
- core.py 将官方 hook、rollout 增量记录和本机分页历史的活动条目交给 src/state.py。observe.py 解析 rollout。events.py 使用 Windows 目录变化通知，并以只读 SQLite 连接投影回合状态及工具标识。SQLite 表结构和 JSONL 字段属于本机兼容路径。启动从现有尾部起读。无信号、回合超时、审批超时均会收敛到待机。
- 桌面协调逻辑在 windows/app.py。Mac broker.py 的 Unix 数据报、Objective-C hook、launchd 和应用内 Unix 执行路径由 Windows 管道、独立窗口应用、嵌入式 Python 和 Inno Setup 替代。待办和对话沿用 src/reminders.py、archive.py、chat.py、weather.py。聊天进程按请求启动，监听临时回环端口，用私有临时文件传递随机密钥。
- 已提交的 Windows 安装脚本按内容哈希检查运行库，升级时可跳过相同文件。升级与卸载识别本项目安装路径和 MCP 服务命令，关闭关联的 stdio 助手。升级失败回滚时，安装器会尝试重新启动已有桌宠。

## 复验入口

`windows/qa_turns.py` 使用本机真实 Codex app-server 发起回合。`qa_transition.py` 在已安装代码上记录实际绘制切换，用测试线程 ID 排除同时运行的其他 Codex 工作。测试专用的 `--review-project-hooks` 核对安装内容后，仅在该验收进程中采用本项目七项定义的当前哈希。

`qa_widgets.py` 使用已安装的 Qt 组件，测试轨迹、菜单、设置、文字与图片回复及中断。`qa_hit.py` 检查实际窗口命中、底层按钮和 DACL。`qa_desktop.py` 需要已解锁桌面，在专用测试档案上投递系统鼠标输入。`qa_geometry.py` 可配合 QT_SCALE_FACTOR 复验缩放。`qa_soak.py PID 输出目录` 按墙钟每 30 秒采样，默认持续 3,600 秒；它记录常驻进程的 CPU 时间、工作集及采样时存在的子进程。验收工具依各自用途使用 psutil、pywin32、pywinauto，桌宠安装包本身附带其所需依赖。
