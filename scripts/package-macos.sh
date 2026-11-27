#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/python-runtime.sh
source scripts/download.sh
mkdir -p .runtime
fetch_checked "$python_url" .runtime/python-runtime.tar.gz "$python_sha"
case "${1:-}" in
  "") scripts/build.sh ;;
  --built-app) codesign --verify --deep --strict ".build/Codex Pet Plus.app" ;;
  *) echo "Usage: package-macos.sh [--built-app]" >&2; exit 2 ;;
esac
mkdir -p .build dist
stage=$(mktemp -d ".build/distribution.XXXXXXXX")
trap 'rm -rf "$stage"' EXIT
package=Cartethyia-Codex-Pet
folder="$stage/$package"
mkdir -p "$folder"/{payload,scripts,src}
ditto --norsrc --noextattr --noacl ".build/Codex Pet Plus.app" "$folder/payload/Codex Pet Plus.app"
cp docs/INSTALL-macOS.md "$folder/README.md"
cp '安装.command' install.sh uninstall.sh NOTICE "$folder/"
cp scripts/{macos-env.sh,plugin.py,stop-windows.py,get-engine.sh,get-model.sh,get-vision.sh,download.sh} "$folder/scripts/"
cp .runtime/python-runtime.tar.gz "$folder/payload/"
cp scripts/python-runtime.sh "$folder/scripts/"
cp src/preference.py "$folder/src/"
codesign --verify --deep --strict "$folder/payload/Codex Pet Plus.app"
archive="$PWD/dist/$package-macOS-arm64.zip"
/usr/bin/python3 - "$stage" "$package" <<'PYZIP'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import sys
stage, folder = Path(sys.argv[1]), sys.argv[2]
with ZipFile(stage / "archive.zip", "w", ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted((stage / folder).rglob("*")):
        if path.is_symlink():
            raise SystemExit("Unexpected symlink in release: " + str(path))
        archive.write(path, path.relative_to(stage))
PYZIP
mv "$stage/archive.zip" "$archive"
(cd dist && shasum -a 256 "$(basename "$archive")" > SHA256SUMS)
echo "$archive"
