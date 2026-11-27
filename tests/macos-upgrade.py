"""Install two real release archives in an isolated macOS user home and downgrade."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("previous", type=Path)
parser.add_argument("current", type=Path)
args = parser.parse_args()
with tempfile.TemporaryDirectory(dir="/tmp",prefix="cpp-upgrade-") as work:
    root=Path(work); home=root/"home"; home.mkdir()
    codex=home/".codex"; codex.mkdir()
    config=codex/"config.toml"; original=b"# user's Codex file\n[analytics]\nenabled = false\n"; config.write_bytes(original)
    base=home/"Library/Application Support/CodexPetPlus"; app=home/"Applications/Codex Pet Plus.app"
    env=dict(os.environ,HOME=str(home),CODEX_HOME=str(codex),CFFIXED_USER_HOME=str(home),
             PET_PLUS_HOME=str(base),CODEX_DISABLE_UPDATE_CHECK="1",PATH="/usr/bin:/bin:/usr/sbin:/sbin")
    def unpack(file,name):
        dest=root/name;dest.mkdir()
        subprocess.run(["ditto","-x","-k",file.resolve(),dest],check=True)
        return dest/"Cartethyia-Codex-Pet"
    previous,current=unpack(args.previous,"v22"),unpack(args.current,"v23")
    def install(package,version):
        subprocess.run([package/"install.sh","--events","--no-launch"],env=env,check=True)
        assert plistlib.loads((app/"Contents/Info.plist").read_bytes())["CFBundleShortVersionString"]==version
        subprocess.run(["codesign","--verify","--deep","--strict",app],check=True)
    install(previous,"2.2.0")
    profile=base/"profiles/main";profile.mkdir(parents=True,exist_ok=True)
    persona=json.dumps({"persona":"Private local fixture","size":156,"custom":"keep"}).encode()
    memory=json.dumps([{"user":"one","assistant":"two"}]).encode()
    (profile/"config.json").write_bytes(persona);(profile/"history.json").write_bytes(memory)
    for package,version in [(current,"2.3.0"),(previous,"2.2.0"),(current,"2.3.0")]:
        install(package,version)
        assert (profile/"config.json").read_bytes()==persona and (profile/"history.json").read_bytes()==memory
    subprocess.run([base/"installer/uninstall.sh","--local-only"],env=env,check=True)
    assert config.read_bytes()==original and not app.exists() and not base.exists()
    print("PASS  v2.2.0 → v2.3.0 → v2.2.0 → v2.3.0; profile bytes preserved; complete local uninstall")
