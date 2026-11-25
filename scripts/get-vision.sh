#!/bin/bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
source scripts/download.sh
store=".runtime/vision"
mkdir -p "$store"
base=https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/52d6c8ffea26cc873ac5ad116f8631268d7eb503
app_data="$HOME/Library/Application Support/CodexPetPlus"
for file in Qwen3VL-2B-Instruct-Q4_K_M.gguf mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf; do
 case "$file" in
   mmproj*) hash=f9a68fabba69c3b81e153367b2c7521030b0fa8bb0de400c9599c8e6725f9c82;;
   *) hash=089d75c52f4b7ffc56ba998ffc50aae89fcafc755f9e7208aacca281dca6c2ae;;
 esac
 fetch_checked "$base/$file" "$store/$file" "$hash" "$app_data/runtime/$file"
 if [[ -f "$app_data/owned" ]]; then
   cp -c "$store/$file" "$app_data/runtime/" 2>/dev/null || cp "$store/$file" "$app_data/runtime/"
 fi
done
