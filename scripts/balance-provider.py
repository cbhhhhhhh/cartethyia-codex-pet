#!/usr/bin/env python3
"""Optional official quota adapters. Start explicitly to add a local context menu."""

import argparse
import http.client
import json
import math
import os
import pathlib
import re
import time
from urllib.parse import urlsplit

PROVIDERS = {
    "deepseek": ("DeepSeek", "DEEPSEEK_API_KEY", "api.deepseek.com", "/user/balance"),
    "opencode-go": (
        "OpenCode Go",
        "OPENCODE_GO_API_KEY",
        "opencode.ai",
        "/inference/go/v1/usage",
    ),
}
SCENES = ["星囊充盈", "星囊闪耀", "细数星砂", "收好余星", "仅余星火", "星囊见底"]


def describe(name, data):
    if name == "deepseek":
        balances = [
            (r["currency"], str(r["total_balance"])) for r in data["balance_infos"]
        ]
        if not balances or any(
            c not in ("CNY", "USD") or not math.isfinite(float(b)) for c, b in balances
        ):
            raise ValueError("invalid-balance")
        return "DeepSeek · " + " / ".join(b + " " + c for c, b in balances), 5 if data[
            "is_available"
        ] is False else None
    windows = data["usage"]
    values = [
        float(windows[key]["percent"]) for key in ("rolling", "weekly", "monthly")
    ]
    if any(not 0 <= x <= 100 for x in values):
        raise ValueError("invalid-limit")
    return "OpenCode Go · " + " · ".join(
        f"{k} {v:g}%" for k, v in zip(("5 小时", "周", "月"), values)
    ), min(5, int(max(values) // 20))


def query(name):
    label, var, server, route = PROVIDERS[name]
    token = os.environ.get(var)
    if not token:
        return label + " · 未设置 " + var, None
    c = http.client.HTTPSConnection(server, timeout=6)
    try:
        c.request(
            "GET",
            route,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        r = c.getresponse()
        if r.status != 200:
            return f"{label} · 服务返回 HTTP {r.status}", None
        return describe(name, json.loads(r.read(131072)))
    finally:
        c.close()


def main():
    parser = argparse.ArgumentParser(
        description="为指定本地桌宠注册额度菜单，仅按需向所选服务发送 API key。"
    )
    parser.add_argument("provider", choices=PROVIDERS)
    parser.add_argument("--profile", default="main")
    parser.add_argument(
        "--interval", type=int, default=0, help="可选的自动查询间隔（分钟，最少 15）"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.profile):
        parser.error("档案名无效")
    path = (
        pathlib.Path.home()
        / "Library/Application Support/CodexPetPlus/profiles"
        / args.profile
        / "api.json"
    )
    if not path.is_file():
        parser.error("请先在这只伙伴的右键菜单打开「浏览器舞台与本地接口」。")
    access = json.loads(path.read_text())
    u = urlsplit(access["origin"])
    if u.scheme != "http" or u.hostname != "127.0.0.1" or not u.port:
        raise ValueError("invalid local stage")
    menu = "balance-" + args.provider

    def local(body=None):
        conn = http.client.HTTPConnection("127.0.0.1", u.port, timeout=3)
        try:
            conn.request(
                "POST" if body else "GET",
                "/v1/control" if body else "/v1/state",
                body=json.dumps(body).encode() if body else None,
                headers={
                    "Authorization": "Bearer " + access["token"],
                    "Content-Type": "application/json",
                },
            )
            r = conn.getresponse()
            if r.status != 200:
                raise RuntimeError("本地舞台暂不可用")
            return json.loads(r.read())
        finally:
            conn.close()

    local(
        dict(
            op="menu-add",
            id=menu,
            label="查看 " + PROVIDERS[args.provider][0] + " 额度",
        )
    )
    try:
        last = max((e["seq"] for e in local().get("events", [])), default=0)
        due = time.monotonic() + max(15, args.interval) * 60
        while True:
            state = local()
            events = [e for e in state.get("events", []) if e["seq"] > last]
            last = max([last] + [e["seq"] for e in events])
            if any(e["id"] == menu for e in events) or (
                args.interval and not state.get("asleep") and time.monotonic() >= due
            ):
                due = time.monotonic() + max(15, args.interval) * 60
                try:
                    message, tier = query(args.provider)
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    TypeError,
                    http.client.HTTPException,
                ):
                    message, tier = "暂时查不到额度。", None
                if not state.get("leased") and not state.get("asleep"):
                    local(dict(op="say", text=message))
                    if tier is not None:
                        local(dict(op="play", action=SCENES[tier]))
            time.sleep(1.5)
    finally:
        try:
            local(dict(op="menu-remove", id=menu))
        except (OSError, RuntimeError):
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
