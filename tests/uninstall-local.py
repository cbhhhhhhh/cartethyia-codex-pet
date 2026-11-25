"""Exercise Codex CLI registration/removal in a disposable local home."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
real = Path.home()
actual_config = real / ".codex/config.toml"
actual_app = real / "Applications/Codex Pet Plus.app"


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


before = [
    digest(actual_config),
    digest(actual_app / "Contents/MacOS/Companion"),
    digest(real / ".codex/pets/cartethyia/spritesheet.webp"),
]
exe = (
    shutil.which("codex")
    or "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
)
with tempfile.TemporaryDirectory(prefix="pet-undo-", dir="/tmp") as tmp:
    home = Path(tmp)
    cfgdir = home / ".codex"
    cfgdir.mkdir()
    cfg = cfgdir / "config.toml"
    pristine = b"# fixture retained during a local upgrade\n[analytics]\nenabled = false\n[feedback]\nenabled = false\n"
    cfg.write_bytes(pristine)
    base = home / "Library/Application Support/CodexPetPlus"
    backup = base / "backup"
    backup.mkdir(parents=True)
    (base / "owned").touch()
    (backup / "config.before").write_bytes(pristine)
    app = home / "Applications/Codex Pet Plus.app"
    app.parent.mkdir()
    subprocess.run(["/usr/bin/ditto", str(actual_app), str(app)], check=True)
    env = dict(
        os.environ,
        HOME=tmp,
        CODEX_HOME=str(cfgdir),
        HTTP_PROXY="http://127.0.0.1:1",
        HTTPS_PROXY="http://127.0.0.1:1",
        ALL_PROXY="http://127.0.0.1:1",
        NO_PROXY="127.0.0.1,localhost",
        CODEX_DISABLE_UPDATE_CHECK="1",
    )

    def command(args):
        p = subprocess.run(
            args,
            env=env,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if p.returncode:
            raise RuntimeError(
                "fixture command failed: " + args[1] + " " + p.stderr.decode()[-200:]
            )

    command(
        [
            "/usr/bin/python3",
            "scripts/plugin.py",
            str(base / "marketplace"),
            str(app / "Contents"),
        ]
    )
    command([exe, "plugin", "marketplace", "add", str(base / "marketplace")])
    command([exe, "plugin", "add", "pet-plus@cartethyia-local"])
    (backup / "config.after").write_bytes(cfg.read_bytes())
    command([str(root / "uninstall.sh"), "--local-only"])
    assert not app.exists() and not base.exists() and cfg.read_bytes() == pristine
    assert not (cfgdir / "plugins/cache/cartethyia-local").exists()
after = [
    digest(actual_config),
    digest(actual_app / "Contents/MacOS/Companion"),
    digest(real / ".codex/pets/cartethyia/spritesheet.webp"),
]
data = dict(
    disposable_registration_and_uninstall=True,
    fixture_config_byte_identical=True,
    owned_app_and_store_removed=True,
    owned_plugin_cache_removed=True,
    live_companion_unaffected=before == after,
)
assert before == after
(root / "docs/v2-uninstall-qa.json").write_text(json.dumps(data, indent=2))
print(data)
