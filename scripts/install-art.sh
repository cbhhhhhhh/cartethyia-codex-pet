#!/bin/bash
# Build additional Cartethyia footage entirely from the user's existing sprite sheet.
set -euo pipefail
cd "$(dirname "$0")/.."
base=$1
pack=${2:-"${CODEX_HOME:-$HOME/.codex}/pets/cartethyia"}
[[ -f "$pack/pet.json" ]] || exit 0
sheet=$(/usr/bin/python3 - "$pack" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();img=(root/json.loads((root/'pet.json').read_text())['spritesheetPath']).resolve()
if img.parent!=root or not img.is_file():raise SystemExit(1)
print(img)
PY
)
fingerprint=$(cat "$sheet" art/repertoire.json scripts/render-repertoire.swift | shasum -a 256 | cut -d' ' -f1)
target="$base/appearance/cartethyia"
mkdir -p "$target"
[[ -s "$target/$fingerprint/pet-plus.json" ]] || {
  if [[ ! -x .build/render-repertoire || scripts/render-repertoire.swift -nt .build/render-repertoire ]]; then
    swiftc -O scripts/render-repertoire.swift -o .build/render-repertoire
  fi
  staging=$(mktemp -d "$target/.drawing.XXXXXXXX")
  trap 'rm -rf "$staging"' EXIT
  .build/render-repertoire "$sheet" art/repertoire.json "$staging"
  /usr/bin/python3 - "$staging" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);clips=json.loads((root/'pet-plus.json').read_text())['clips']
assert len(clips)==109 and all((root/s['file']).is_file() for s in clips.values())
PY
  mv "$staging" "$target/$fingerprint"
}
link="$target/.current-$$"
ln -s "$fingerprint" "$link"
/usr/bin/python3 - "$link" "$target/current" <<'PY'
import os,sys
os.replace(sys.argv[1],sys.argv[2])
PY
