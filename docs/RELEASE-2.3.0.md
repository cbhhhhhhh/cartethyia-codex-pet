# 卡提希娅 Codex 桌宠 2.3.0

这次更新面向 Apple Silicon Mac。卡提学会了提裙行礼、在本子上落笔、解开礼盒，也能记得刚刚给你看的那张图。工作时，她会等你发起的主回合真正结束才庆祝。

![从安装包中取出的提裙行礼、写字、拆礼物动画](https://raw.githubusercontent.com/cbhhhhhhh/cartethyia-codex-pet/v2.3.0/docs/v23-actions.gif)

## 下载

| 平台 | 2.3.0 安装包 |
| --- | --- |
| Apple M 系列芯片，macOS 27.2 或更新版本 | **[下载 macOS arm64 ZIP（约 61.3 MiB）](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/download/v2.3.0/Cartethyia-Codex-Pet-macOS-arm64.zip)** |
| Windows | |

Windows 版这次尚未更新。每个版本的安装包都保留在各自的发布页。[全部版本](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases)

## 更新内容

- **工作播报。** 修复子智能体复制父会话历史时触发提前庆祝的问题。子任务先结束、计划全部打勾、同一回合收到重复事件，都只更新相应信息。同时进行的主会话分别结算。鼠标悬停时保持安静，要看工具、耗时和计划，右键打开「工作详情」。
- **109 段点播动作。** 每段各有四个专属关键姿势，展开成 24 帧透明动画。横步、折返等动作会在桌面上移动。部分动作带跟随节拍的短台词。可以直接说「给我行个礼」「刚才那个再来一次」。
- **配图。** 右键「配图」可以先看缩略图和中文名称。点一张图，卡提会用碎碎念模型结合这张图说一句。普通聊天默认使用文字。开启按内容配图后仍控制频率，想回看可以说「刚才那张图再给我看看」。
- **人设与模型。** 默认聊天继续用本地 Qwen2.5-1.5B-Instruct。聊天和碎碎念可分别选本地 GGUF、兼容 API 或 Codex 账户可用的模型。明确禁止地名、天气或自定义词语时，共用的规则会检查历史、环境信息和生成结果，检查过的整句才会显示、朗读并写入记忆。
- **额度与本次任务用量。** 原来的「10080 窗口」现在显示为「7 天额度」，附剩余、已用、下次重置和更新时间。「当前任务用量」可切换主回合，列出主任务与已关联子会话的 token。缓存输入和推理输出作为明细展示。积分与美元估值采用账户接口返回值，单轮缺少可用基线时会标明。卡提聊天与碎碎念单独计数。

## 安装、升级和回退

1. 确认已安装支持本地插件的 Codex。下载上述 Mac ZIP 并解压，双击 **安装.command**。已有桌宠可直接运行新版安装器，保留个人设置、人设和聊天。
2. 默认的本地文字聊天首次需下载约 1.1 GB。选择「仅事件」可先使用角色和工作提醒，之后也可在「设置 → 模型」选择已有的 Codex 账户或兼容 API。
3. 在 Codex 的「设置 → Hooks」审阅 pet-plus 的 hooks。从应用列表打开 **Codex Pet Plus** 可调整设置。单击卡提聊天，右键打开动作、配图、账户额度或任务用量。

如需校验下载文件，把 ZIP 与校验文件放在同一目录，运行 `shasum -a 256 -c SHA256SUMS`。应用使用本地临时签名。回退时退出桌宠，运行所需旧版本的 Mac 安装器。手册含 Gatekeeper、备份和完整卸载步骤。[下载 SHA256SUMS](https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/download/v2.3.0/SHA256SUMS) · [安装与卸载手册](https://github.com/cbhhhhhhh/cartethyia-codex-pet/blob/v2.3.0/docs/INSTALL-macOS.md) · [本版实测](https://github.com/cbhhhhhhh/cartethyia-codex-pet/blob/v2.3.0/docs/QA-2.3.0.md)
