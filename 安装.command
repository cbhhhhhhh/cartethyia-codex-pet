#!/bin/bash
set -u
cd "$(dirname "$0")" || exit 1
echo '卡提希娅codex桌宠 · Apple Silicon'
echo '1  桌宠 + 本地文字聊天（首次下载约 1.1 GB）'
echo '2  桌宠 + 工作提醒（不下载模型）'
echo '3  桌宠 + 文字和图片聊天（首次共下载约 2.7 GB）'
read -r -p '选择安装方式 [默认 1，输入 q 退出]：' choice || exit 1
case "$choice" in
  ''|1) args=(--full);;
  2) args=(--events);;
  3) args=(--full --vision);;
  q|Q) exit 0;;
  *) echo '请输入 1、2、3 或 q。'; exit 2;;
esac
/bin/bash ./install.sh "${args[@]}"
result=$?
if (( result != 0 )); then echo '安装未完成。请按上面的提示处理后重新打开安装器。'; fi
read -r -p '按回车关闭。' _ || true
exit "$result"
