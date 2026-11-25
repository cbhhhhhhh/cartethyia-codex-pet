# Shared by the source installer, release installer and uninstaller.
find_codex() {
  local executable bundle
  if executable=$(command -v codex); then printf '%s\n' "$executable"; return 0; fi
  for bundle in "/Applications/ChatGPT.app" "/Applications/Codex.app" "$HOME/Applications/ChatGPT.app" "$HOME/Applications/Codex.app"; do
    for executable in "$bundle/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex" "$bundle/Contents/Resources/codex"; do
      if [[ -x "$executable" && ! -d "$executable" ]]; then printf '%s\n' "$executable"; return 0; fi
    done
  done
  echo "未找到 Codex CLI。请先安装支持本地插件的 Codex 桌面版，或将 codex 加入 PATH。" >&2
  return 1
}

check_mac() {
  if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    echo "需要以原生模式运行的 Apple Silicon（M 系列）Mac。" >&2; return 1
  fi
  local major minor patch
  IFS=. read -r major minor patch <<< "$(/usr/bin/sw_vers -productVersion)"
  if (( major < 27 || (major == 27 && ${minor:-0} < 2) )); then
    echo "本版本需要 macOS 27.2 或更新。" >&2; return 1
  fi
  if [[ ! -f payload/python-runtime.tar.gz ]] && ! /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    echo "请运行 xcode-select --install，装好 Apple Command Line Tools 后重新打开安装器。" >&2
    return 1
  fi
}
