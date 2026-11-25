#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
scratch=$(mktemp -d /tmp/pet-finder.XXXXXXXX)
app="$scratch/Cartethyia QA.app"
base="$scratch/store"
cleanup() {
  for pid in $(pgrep -f "^(/private)?$scratch/Cartethyia QA.app/Contents/MacOS/Companion( |$)" || true); do kill "$pid" 2>/dev/null || true; done
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -u "$app" >/dev/null 2>&1 || true
  rm -rf "$scratch"
}
trap cleanup EXIT
mkdir -p "$base/profiles/main"
ditto "${1:-$HOME/Applications/Codex Pet Plus.app}" "$app"
/usr/libexec/PlistBuddy -c "Set CFBundleIdentifier local.cartethyia.finderqa.$(basename "$scratch" | cut -d. -f2)" "$app/Contents/Info.plist"
codesign -fs - "$app"
ln -s "$HOME/Library/Application Support/CodexPetPlus/appearance" "$base/appearance"
python3 - "$base" <<'PY'
import json,sys,pathlib
cfg=json.loads(pathlib.Path('examples/config.json').read_text())
cfg.update(x=440,y=300,randomActions=False,notifications=False)
(pathlib.Path(sys.argv[1])/'profiles/main/config.json').write_text(json.dumps(cfg))
PY
swiftc tests/finder-and-circle.swift -o "$scratch/check"
"$scratch/check" "$app" "$base" "$PWD/docs/v21-finder-qa.json"
