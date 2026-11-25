# Download a pinned release, or reuse an intact copy already installed on this Mac.
fetch_checked() {
  local url=$1 dest=$2 hash=$3 previous=${4:-} partial="$2.part"
  verify_download() {
    [[ -f "$1" ]] && [[ "$(shasum -a 256 "$1" | cut -d' ' -f1)" == "$hash" ]]
  }
  if verify_download "$dest"; then return 0; fi
  if [[ -n "$previous" ]] && verify_download "$previous"; then
    cp -c "$previous" "$partial" 2>/dev/null || cp "$previous" "$partial"
  else
    echo "正在下载 $(basename "$dest") …"
    if ! curl -fL --retry 3 --retry-all-errors -C - "$url" -o "$partial" || ! verify_download "$partial"; then
      rm -f "$partial"
      curl -fL --retry 3 --retry-all-errors "$url" -o "$partial"
      verify_download "$partial" || { echo "下载文件校验失败：$(basename "$dest")" >&2; return 1; }
    fi
  fi
  mv -f "$partial" "$dest"
}
