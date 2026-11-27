#!/bin/bash
set -euo pipefail
umask 077
cd "$(dirname "$0")"
source scripts/macos-env.sh
base="$HOME/Library/Application Support/CodexPetPlus"
app="$HOME/Applications/Codex Pet Plus.app"
cfg="${CODEX_HOME:-$HOME/.codex}/config.toml"
stage=--full
sync_native=false
vision=false
launch=true
for mode in "$@"; do
 case "$mode" in --events|--full) stage="$mode";; --sync-native) sync_native=true;; --vision) vision=true;; --no-launch) launch=false;; *) echo "用法：./install.sh [--events|--full] [--sync-native] [--vision] [--no-launch]" >&2; exit 2;; esac
done
check_mac
codex_cli=$(find_codex)
"$codex_cli" plugin marketplace add --help >/dev/null || { echo "请更新 Codex 到支持本地 marketplace 的版本。" >&2; exit 1; }
if $vision && [[ "$stage" != --full ]]; then echo "--vision 需要 --full" >&2; exit 2; fi
if [[ ! -f "$base/owned" && -f "$cfg" ]] && grep -Eq '^\[(marketplaces\.cartethyia-local|plugins\."pet-plus@cartethyia-local")\]' "$cfg"; then
 echo "本机已有同名 marketplace 或插件，安装已停止。" >&2; exit 1
fi
if [[ ( -e "$app" || -e "$base" ) && ! -f "$base/owned" ]]; then echo "目标位置已有同名应用，停止安装" >&2; exit 1; fi
mkdir -p "$HOME/Applications" "$base/backup" "$base/runtime"
if [[ ! -f "$base/owned" ]]; then
 [[ ! -e "$cfg" ]] || cp -p "$cfg" "$base/backup/config.before"
 touch "$base/owned"
fi
if [[ -f payload/python-runtime.tar.gz ]]; then
  source scripts/python-runtime.sh
  install_python_runtime payload/python-runtime.tar.gz "$base/runtime"
fi
pet_python=/usr/bin/python3
if [[ -x "$base/runtime/python/bin/python3" ]]; then pet_python="$base/runtime/python/bin/python3"; fi
if [[ "$stage" == "--full" ]]; then scripts/get-engine.sh; scripts/get-model.sh; fi
if [[ -d "payload/Codex Pet Plus.app" ]]; then
  source_app="payload/Codex Pet Plus.app"
else
  scripts/build.sh
  source_app=".build/Codex Pet Plus.app"
fi
codesign --verify --deep --strict "$source_app"
stage_dir=$(mktemp -d "$HOME/Applications/.pet-plus-install.XXXXXX")
trap 'rm -rf "$stage_dir"' EXIT
ditto "$source_app" "$stage_dir/new.app"
codesign --verify --strict "$stage_dir/new.app"
"$pet_python" -B scripts/stop-windows.py
if [[ -d "$app" ]]; then mv "$app" "$stage_dir/old.app"; fi
if ! mv "$stage_dir/new.app" "$app"; then
  if [[ -d "$stage_dir/old.app" ]]; then mv "$stage_dir/old.app" "$app"; fi
  exit 1
fi
# Complete the first macOS executable launch before Codex registers the hook.
"$app/Contents/MacOS/pet-hook" </dev/null >/dev/null
if [[ "$stage" == "--full" ]]; then
rm -f "$base/events-only"
cp -cR .runtime/llama-b12675 "$base/runtime/" 2>/dev/null || ditto .runtime/llama-b12675 "$base/runtime/llama-b12675"
cp -c .runtime/*.gguf "$base/runtime/" 2>/dev/null || cp .runtime/*.gguf "$base/runtime/"
if $vision; then scripts/get-vision.sh; fi
else touch "$base/events-only"; fi
"$pet_python" -B scripts/plugin.py "$base/marketplace" "$app/Contents"
if [[ ! -f "$base/registered" ]]; then
 if ! grep -Fqx '[marketplaces.cartethyia-local]' "$cfg" 2>/dev/null; then
   "$codex_cli" plugin marketplace add "$base/marketplace"
 fi
 if ! grep -Fqx '[plugins."pet-plus@cartethyia-local"]' "$cfg" 2>/dev/null; then
   "$codex_cli" plugin add pet-plus@cartethyia-local
 fi
 touch "$base/registered"
 cp -p "$cfg" "$base/backup/config.after"
fi
if $sync_native; then "$pet_python" -B src/preference.py enable-sync; fi
# Only our current app should appear in Launch Services. Retain configuration backups for uninstall.
lsregister=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
previous="$base/backup/previous-app/Codex Pet Plus.app"
if [[ -d "$previous" ]] && [[ "$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$previous/Contents/Info.plist")" == "local.cartethyia.petplus" ]]; then
  "$lsregister" -u "$previous" >/dev/null 2>&1 || true
  rm -rf "$previous"
  rmdir "$base/backup/previous-app" 2>/dev/null || true
fi
# ditto preserves directory times, including from a version that did not have an icon.
touch "$app/Contents/Resources" "$app/Contents" "$app"
if $launch; then
  "$lsregister" -f "$app"
  mdimport "$app" >/dev/null 2>&1 || true
fi
mkdir -p "$base/installer/scripts" "$base/installer/src"
cp uninstall.sh "$base/installer/"
cp scripts/{macos-env.sh,stop-windows.py} "$base/installer/scripts/"
cp src/preference.py "$base/installer/src/"
if $launch; then open -g "$app" --args --background; fi
echo "Cartethyia 安装成功。打开 ~/Applications/Codex Pet Plus.app 可调整设置。"
echo "在 Codex 的 Hooks 设置中审阅 pet-plus 的 hook 后，用一次本地任务测试状态提醒。"
