#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/download.sh
mkdir -p .runtime
cd .runtime
fetch_checked https://github.com/ggml-org/llama.cpp/releases/download/b12675/llama-b12675-bin-macos-arm64.tar.gz llama.tar.gz 70c8f63d7b56477f950b12071d6ea2ef1a0d39a416779359dbb80a1d98da1626
tar xzf llama.tar.gz
