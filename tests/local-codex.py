"""Run the genuine CLI on a loopback Responses fixture. No account or credentials."""

import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time


class Response(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def event(kind, **values):
            data = json.dumps(dict(type=kind, **values))
            self.wfile.write(("event: " + kind + "\ndata: " + data + "\n\n").encode())
            self.wfile.flush()

        response = dict(
            id="resp_local_pet", object="response", status="in_progress", output=[]
        )
        event("response.created", response=response)
        time.sleep(1.5)
        item = dict(
            id="msg_local_pet",
            type="message",
            role="assistant",
            content=[dict(type="output_text", text="OK", annotations=[])],
            status="completed",
        )
        event(
            "response.output_item.added",
            output_index=0,
            item=dict(item, content=[], status="in_progress"),
        )
        event(
            "response.output_text.delta",
            item_id=item["id"],
            output_index=0,
            content_index=0,
            delta="OK",
        )
        event("response.output_item.done", output_index=0, item=item)
        event(
            "response.completed",
            response=dict(
                response,
                status="completed",
                output=[item],
                usage=dict(input_tokens=2, output_tokens=1, total_tokens=3),
            ),
        )


def run(base, marker):
    base.mkdir(exist_ok=True, parents=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Response)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    (base / "config.toml").write_text(
        'model="pet-test"\nmodel_provider="loopback"\n[model_providers.loopback]\nname="local test"\nwire_api="responses"\nbase_url="http://127.0.0.1:'
        + str(server.server_port)
        + '/v1"\n[analytics]\nenabled=false\n[feedback]\nenabled=false\n'
    )
    with tempfile.TemporaryDirectory() as work:
        env = dict(
            HOME=work,
            CODEX_HOME=str(base),
            PATH=os.environ.get("PATH", "/usr/bin:/bin"),
            HTTP_PROXY="http://127.0.0.1:1",
            HTTPS_PROXY="http://127.0.0.1:1",
            ALL_PROXY="http://127.0.0.1:1",
            NO_PROXY="127.0.0.1,localhost",
            RUST_LOG="off",
        )
        exe = (
            shutil.which("codex")
            or "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
        )
        done = subprocess.run(
            [
                exe,
                "exec",
                "--skip-git-repo-check",
                "--json",
                "-s",
                "read-only",
                "-C",
                work,
                "Reply OK.",
            ],
            env=env,
            cwd=work,
            capture_output=True,
            timeout=35,
        )
        events = []
        for line in done.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        if done.returncode or not any(
            e.get("type") == "turn.completed" for e in events
        ):
            print(done.stderr.decode()[-750:], file=sys.stderr)
            print([x.get("type") for x in events], file=sys.stderr)
            sys.exit(1)
        marker.touch()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with tempfile.TemporaryDirectory() as temp:
            run(Path(temp, "codex"), Path(temp, "ok"))
            print("Real CLI completed locally")
    else:
        run(
            Path(os.environ["CODEX_HOME"]),
            Path(os.environ["PET_PLUS_HOME"], "real-cli-ok"),
        )
