#!/bin/bash
set -euo pipefail
base="$HOME/Library/Application Support/CodexPetPlus"
app="$HOME/Applications/Codex Pet Plus.app"
cfg="${CODEX_HOME:-$HOME/.codex}/config.toml"
[[ -f "$base/owned" ]] || { echo "未安装"; exit 0; }
cd "$(dirname "$0")"
source scripts/macos-env.sh
case "${1:-}" in ""|--local-only) ;; *) echo "用法：./uninstall.sh [--local-only]"; exit 2;; esac
pet_python=/usr/bin/python3
if [[ -x "$base/runtime/python/bin/python3" ]]; then pet_python="$base/runtime/python/bin/python3"; fi
if [[ -f "$base/native-account.json" && "${1:-}" != "--local-only" ]]; then
 "$pet_python" -B src/preference.py restore || { echo "恢复偏好失败。稍后重试，或明确选择 --local-only 只卸载本地文件。" >&2; exit 1; }
fi
"$pet_python" -B scripts/stop-windows.py
exact=false
if [[ -f "$base/backup/config.after" ]] && cmp -s "$cfg" "$base/backup/config.after"; then exact=true; fi
if grep -Fqx '[plugins."pet-plus@cartethyia-local"]' "$cfg" 2>/dev/null; then
 cli=$(find_codex); "$cli" plugin remove pet-plus@cartethyia-local
fi
if grep -Fqx '[marketplaces.cartethyia-local]' "$cfg" 2>/dev/null; then
 cli=$(find_codex); "$cli" plugin marketplace remove cartethyia-local
fi
rmdir "${CODEX_HOME:-$HOME/.codex}/plugins/cache/cartethyia-local" 2>/dev/null || true
if $exact; then
 if [[ -f "$base/backup/config.before" ]]; then cp -p "$base/backup/config.before" "$cfg";else rm -f "$cfg";fi
fi
rm -rf "$app" "$base"
echo "桌宠及其本地设置、记忆和运行时已卸载；工程目录保留。"
