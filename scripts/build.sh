#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .build
stage=$(mktemp -d ".build/app.XXXXXXXX")
trap 'rm -rf "$stage"' EXIT
app="$stage/Codex Pet Plus.app/Contents"
mkdir -p "$app"/{MacOS,Resources}
swiftc -target arm64-apple-macos27.2 -O -swift-version 5 src/*.swift -o "$app/MacOS/Companion"
clang -target arm64-apple-macos27.2 -Os -fobjc-arc -Wno-incompatible-pointer-types -framework Foundation src/hook.m -o "$app/MacOS/pet-hook"
scripts/install-art.sh ".build/bundled-art" "art/pets/cartethyia"
clips=$(cd ".build/bundled-art/appearance/cartethyia/current" && pwd -P)
ditto "$clips" "$app/Resources/pets/cartethyia"
cp art/pets/cartethyia/{pet.json,spritesheet.webp} "$app/Resources/pets/cartethyia/"
cp art/Cartethyia.icns LICENSE NOTICE "$app/Resources/"
cp scripts/pet-python "$app/Resources/"
cp src/*.py "$app/Resources/"
ditto src/web "$app/Resources/web"
python3 - "$app/Info.plist" <<'PY'
import plistlib,sys
with open(sys.argv[1],'wb') as f:
 plistlib.dump(dict(CFBundleIdentifier='local.cartethyia.petplus',CFBundleName='Codex Pet Plus',CFBundleExecutable='Companion',CFBundlePackageType='APPL',CFBundleShortVersionString='0.1.0',CFBundleVersion='5',LSMinimumSystemVersion='27.2',CFBundleInfoDictionaryVersion='6.0',CFBundleDisplayName='Codex Pet Plus',CFBundleIconFile='Cartethyia.icns',CFBundleIconName='Cartethyia',NSMicrophoneUsageDescription='按住话筒时在本机识别语音。',NSSpeechRecognitionUsageDescription='将语音在本机转换为对话草稿。',LSUIElement=True,NSHighResolutionCapable=True),f)
PY
codesign --force --sign - "$stage/Codex Pet Plus.app"
codesign --verify --deep --strict "$stage/Codex Pet Plus.app"
if [[ -e ".build/Codex Pet Plus.app" ]]; then mv ".build/Codex Pet Plus.app" "$stage/previous.app"; fi
mv "$stage/Codex Pet Plus.app" .build/
