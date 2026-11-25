#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
scratch=$(mktemp -d "${TMPDIR:-/tmp}/cppqa.XXXXXXXX")
trap 'rm -rf "$scratch"' EXIT
out="$scratch/Test.app/Contents"
mkdir -p "$out/MacOS" "$out/Resources" "$scratch/data"
export PET_PLUS_CLI_TEST="$PWD/tests/local-codex.py"
export PET_PLUS_HOME="$scratch/data" CODEX_HOME="$scratch/codex" PET_PLUS_PREVIEW="$scratch/native-preview.png"
# A short socket path is necessary on macOS.
if (( ${#PET_PLUS_HOME} > 80 )); then echo "测试目录过长" >&2; exit 1; fi
cp ".build/Codex Pet Plus.app/Contents/Info.plist" "$out/"
/usr/libexec/PlistBuddy -c 'Set CFBundleIdentifier local.cartethyia.test' "$out/Info.plist"
swiftc -O -swift-version 5 $(find src -name "*.swift" ! -name main.swift) tests/native/main.swift -o "$out/MacOS/Companion"
clang -Os -DPET_PLUS_TEST -fobjc-arc -Wno-incompatible-pointer-types -framework Foundation src/hook.m -o "$out/MacOS/pet-hook"
cp scripts/pet-python "$out/Resources/"
cp src/*.py "$out/Resources/"
ditto src/web "$out/Resources/web"
ditto ".build/Codex Pet Plus.app/Contents/Resources/pets" "$out/Resources/pets"
model_dir="$HOME/Library/Application Support/CodexPetPlus/runtime"
if [[ ! -f "$model_dir/qwen2.5-1.5b-instruct-q4_k_m.gguf" ]]; then model_dir="$PWD/.runtime"; fi
ln -s "$model_dir" "$PET_PLUS_HOME/runtime"
if [[ -d "$HOME/Library/Application Support/CodexPetPlus/appearance" ]]; then
 ln -s "$HOME/Library/Application Support/CodexPetPlus/appearance" "$PET_PLUS_HOME/appearance"
elif [[ -d "$PWD/.build/character-repertoire" ]]; then
 mkdir -p "$PET_PLUS_HOME/appearance/cartethyia"
 ln -s "$PWD/.build/character-repertoire" "$PET_PLUS_HOME/appearance/cartethyia/current"
fi
codesign --force --sign - "$scratch/Test.app"
rm -f .build/native.json .build/native-exercise.log
open -n -W -a "$scratch/Test.app" --env "PET_PLUS_HOME=$PET_PLUS_HOME" --env "CODEX_HOME=$CODEX_HOME" --env "PET_PLUS_PREVIEW=$PET_PLUS_PREVIEW" --stdout "$scratch/qa.json" --stderr "$scratch/qa.log" --args exercise
cp "$scratch/qa.json" .build/native.json
cp "$scratch/qa.log" .build/native-exercise.log
[[ -s .build/native.json ]] || { cat .build/native-exercise.log >&2; exit 1; }
cp "$PET_PLUS_PREVIEW" .build/native-preview.png
for card in "$scratch"/v21-*.png; do [[ ! -f "$card" ]] || cp "$card" docs/; done
"$out/MacOS/Companion" restore > .build/restore.json
"$out/MacOS/Companion" real-cli > .build/real-cli.json
"$out/MacOS/Companion" recovery > docs/v21-recovery-qa.json
if [[ "${1:-}" == "--preview" ]]; then
 "$out/MacOS/Companion" actions > .build/v2-animation-qa.json
 cp "$scratch/v2-actions.gif" docs/v2-actions.gif
fi
python3 - <<'PY'
import json,pathlib
root=pathlib.Path('.build')
d=dict(json.loads((root/'native.json').read_text()),**json.loads((root/'restore.json').read_text()),**json.loads((root/'real-cli.json').read_text()))
pathlib.Path('docs/v21-native-qa.json').write_text(json.dumps(d,indent=2,sort_keys=True))
print(json.dumps(d,indent=2))
PY
