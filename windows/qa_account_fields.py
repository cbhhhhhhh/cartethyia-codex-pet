"""Read current official interface shapes. Persist field availability, never account values or IDs."""

import json
from pathlib import Path
import queue
import sys
import time

app = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
sys.path[:0] = [str(app / "src"), str(Path(__file__).resolve().parent)]
from observe import quota_view
from providers import server
from qa_account import account_home

with account_home() as (_, empty), server(cwd=empty, isolate=True) as rpc:
    account = rpc.call("account/read", {"refreshToken": False}).get("account") or {}
    models = rpc.call("model/list", {"limit": 100})["data"]
    selected = next(m for m in models if m["model"] == "gpt-6.2-sol")
    limits = rpc.call("account/rateLimits/read", {})
    quota = quota_view(limits)["text"]
    thread = rpc.call(
        "thread/start",
        dict(
            cwd=str(empty),
            approvalPolicy="never",
            sandbox="read-only",
            baseInstructions="Arithmetic only. No tools.",
        ),
    )["thread"]["id"]

    def usage():
        response = rpc.call("account/usage/read", {"threadId": thread})
        detail = response.get("threadUsage") or {}
        fields = ("estimatedUsageCreditsMicros", "estimatedUsageUsdMicros", "nativeUsageUsdMicros")
        return dict(
            response_fields=sorted(response),
            thread_matched=detail.get("threadId") == thread,
            available={k: type(detail.get(k)) is int for k in fields},
        )

    opening = usage()
    turn = rpc.call(
        "turn/start",
        dict(threadId=thread, input=[dict(type="text", text="Reply only with 2+2.")], effort="low"),
    )["turn"]["id"]
    limit = time.monotonic() + 100
    while time.monotonic() < limit:
        try:
            event = rpc.next_event(0.5)
        except queue.Empty:
            continue
        if not event:
            raise RuntimeError("Official API closed before the synthetic turn finished")
        params = event.get("params", {})
        if event.get("method") == "turn/completed" and params.get("turn", {}).get("id") == turn:
            assert params["turn"]["status"] == "completed"
            break
    else:
        raise RuntimeError("Synthetic official turn timed out")
    closing = usage()
    hooks = rpc.call("hooks/list", {"cwds": [str(empty)]})
    result = dict(
        account_type=account.get("type"),
        model_count=len(models),
        selected_model=selected["model"],
        ultra_available=any(
            v.get("reasoningEffort") == "ultra" for v in selected.get("supportedReasoningEfforts", [])
        ),
        quota_7days="7 天额度" in quota,
        quota_fields=all(k in quota for k in ("剩余", "已用", "下次重置", "更新于")),
        hooks_list_available="data" in hooks,
        opening=opening,
        closing=closing,
    )
    assert result["account_type"] == "chatgpt" and result["quota_7days"] and result["quota_fields"]
    out.write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps(result))
