# The binary release ships the original, checksum-pinned archive and its licenses.
python_build=3.13.18+20261124
python_sha=296f0903cccda15a5c9d3d8393cd2204718aeffd9b095a00f812d75c7b1c0967
python_url="https://github.com/astral-sh/python-build-standalone/releases/download/20261124/cpython-$python_build-aarch64-apple-darwin-install_only_stripped.tar.gz"

install_python_runtime() {
  local package=$1 runtime=$2 dest="$2/cpython-$python_build" stage
  (echo "$python_sha  $package" | shasum -a 256 -c -) || return 1
  if [[ ! -x "$dest/bin/python3" ]]; then
    stage=$(mktemp -d "$runtime/.python.XXXXXXXX")
    if ! /usr/bin/tar -xzf "$package" -C "$stage" || ! "$stage/python/bin/python3" -I -B -c 'import sqlite3, ssl'; then
      rm -rf "$stage"; return 1
    fi
    mv "$stage/python" "$dest"
    rmdir "$stage"
  fi
  ln -s "cpython-$python_build" "$runtime/.python-link-$$"
  /bin/mv -fh "$runtime/.python-link-$$" "$runtime/python"
}
