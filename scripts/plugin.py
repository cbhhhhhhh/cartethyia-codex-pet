"""Generate the per-install absolute command path; never interpolate hook data in a shell."""

import json
import sys
import shlex
from pathlib import Path

p = Path(sys.argv[1])
exe = Path(sys.argv[2])


def write(path, d):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d, indent=2) + "\n")


name = "cartethyia-local"
write(
    p / ".agents/plugins/marketplace.json",
    dict(
        name=name,
        interface=dict(displayName="Cartethyia Local"),
        plugins=[
            dict(
                name="pet-plus",
                source=dict(source="local", path="./plugins/pet-plus"),
                policy=dict(installation="AVAILABLE", authentication="ON_INSTALL"),
                category="Productivity",
            )
        ],
    ),
)
plugin = p / "plugins/pet-plus"
events = "UserPromptSubmit PreToolUse PermissionRequest PostToolUse Stop Interrupt SubagentStop".split()
hooks = {
    e: [
        {
            "hooks": [
                dict(
                    type="command",
                    command=shlex.quote(str(exe / "MacOS/pet-hook")),
                    timeout=1,
                    **{"async": True},
                )
            ]
        }
    ]
    for e in events
}
write(
    plugin / ".codex-plugin/plugin.json",
    dict(
        name="pet-plus",
        version="1.0.0",
        description="Local Cartethyia desktop companion",
        hooks={"hooks": hooks},
        mcpServers="./.mcp.json",
        skills="./skills",
    ),
)
write(
    plugin / ".mcp.json",
    {
        "mcpServers": {
            "pet_plus": {
                "command": str(exe / "Resources/pet-python"),
                "args": ["-B", str(exe / "Resources/mcp.py")],
            }
        }
    },
)
skill = plugin / "skills/pet-plus/SKILL.md"
skill.parent.mkdir(parents=True, exist_ok=True)
skill.write_text(
    "---\nname: pet-plus\ndescription: Read local companion status or manage an explicitly requested pet reminder.\n---\nFor current pet status use pet_status. For a requested reminder use pet_remind with an ISO timestamp including timezone. Complete a reminder only when requested.\n"
)
