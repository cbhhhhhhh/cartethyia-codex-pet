import json
import socket
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from conversation import Broker


@unittest.skipIf(sys.platform == "win32", "Mac broker uses Unix datagrams; Windows uses per-user named pipes")
class FanoutTests(unittest.TestCase):
    def test_peer_pose_and_impulse_use_distinct_channel(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as folder:
            main = Broker(Path(folder))
            other = Broker(Path(folder), "second")
            try:
                for peer in (main, other):
                    self.assertTrue(peer.until("peer-count", 5)[0]["peers"])
                other.send(
                    "peer", kind="pose", x=100, y=120, w=120, h=144, visible=True
                )
                got = main.until("peer", 2)[0]
                self.assertEqual(
                    (got["kind"], got["from"], got["x"]), ("pose", "second", 100)
                )
                main.send("peer", kind="impulse", target="second", vx=340, vy=95)
                hit = other.until("peer", 2)[0]
                self.assertEqual(
                    (hit["kind"], hit["vx"], hit["target"]), ("impulse", 340, "second")
                )
            finally:
                main.close()
                other.close()

    def test_unidentified_approval_reaches_secondary_and_is_released(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as folder:
            base = Path(folder)
            primary = Broker(base)
            secondary = Broker(base, "second")

            def state(broker, target):
                for _ in range(5):
                    packet, _ = broker.until("status", 2)
                    if packet["state"] == target:
                        return packet
                self.fail(target)

            try:
                state(primary, "idle")
                state(secondary, "idle")
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:

                    def send(kind, **fields):
                        data = dict(
                            v=1,
                            kind=kind,
                            thread=thread,
                            turn=turn,
                            token=(base / "token").read_text(),
                            source="hook",
                            tool="Bash",
                        )
                        data.update(fields)
                        client.sendto(
                            json.dumps(data).encode(), str(base / "events.sock")
                        )

                    thread = str(uuid.uuid4())
                    turn = str(uuid.uuid4())
                    send("tool", call="42", token="incorrect")
                    send("tool", call="42")
                    for b in (primary, secondary):
                        state(b, "working")
                    send("approval")
                    for b in (primary, secondary):
                        state(b, "waiting-for-approval")
                    send("result", call="42")
                    for b in (primary, secondary):
                        state(b, "thinking")
                    send("abort")
                    for b in (primary, secondary):
                        state(b, "idle")
            finally:
                secondary.close()
                primary.close()
