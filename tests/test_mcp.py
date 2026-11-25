import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class McpTests(unittest.TestCase):
    def test_stdio_reminder_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as temp:
            requests = [
                "bad json",
                json.dumps(
                    dict(
                        id=1,
                        method="initialize",
                        params={"protocolVersion": "2024-11-05"},
                    )
                ),
                json.dumps(dict(id=2, method="tools/list")),
                json.dumps(
                    dict(
                        id=3,
                        method="tools/call",
                        params={"name": "pet_status", "arguments": {}},
                    )
                ),
                json.dumps(
                    dict(
                        id=4,
                        method="tools/call",
                        params={
                            "name": "pet_remind",
                            "arguments": {
                                "text": "本机测试",
                                "due": "2030-01-01T12:00:00+08:00",
                            },
                        },
                    )
                ),
            ]
            p = subprocess.run(
                [sys.executable, "-B", str(ROOT / "src/mcp.py")],
                input="\n".join(requests) + "\n",
                env=dict(os.environ, HOME=temp, LOCALAPPDATA=temp, PYTHONIOENCODING="utf-8"),
                encoding="utf-8",
                text=True,
                capture_output=True,
                check=True,
            )
            responses = [json.loads(s) for s in p.stdout.splitlines()]
            self.assertIn("error", responses[0])
            self.assertEqual(responses[1]["result"]["protocolVersion"], "2024-11-05")
            self.assertEqual(
                {x["name"] for x in responses[2]["result"]["tools"]},
                {"pet_status", "pet_remind", "pet_complete"},
            )
            state = json.loads(responses[3]["result"]["content"][0]["text"])
            self.assertEqual(state, {"state": "idle", "online": False})
            i = json.loads(responses[4]["result"]["content"][0]["text"])["id"]
            path = Path(
                temp, "Library/Application Support/CodexPetPlus/reminders.sqlite3"
            )
            if sys.platform == "win32":
                path = Path(temp, "CartethyiaPet/reminders.sqlite3")
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(
                    db.execute("SELECT body FROM reminder WHERE id=?", (i,)).fetchone()[
                        0
                    ],
                    "本机测试",
                )
