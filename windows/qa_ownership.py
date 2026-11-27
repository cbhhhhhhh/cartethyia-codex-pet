"""Windows-specific regression on inherited ordinals, hooks, queued cards and billing baselines."""

import datetime, json, os, sqlite3, sys, tempfile, threading, time, uuid
from pathlib import Path
from unittest.mock import patch

install = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
sys.path[:0] = [str(install / "windows"), str(install / "src")]


def uid():
    return str(uuid.uuid4())


def clock():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


with tempfile.TemporaryDirectory(prefix="cart-ownership-") as d:
    area = Path(d)
    home = area / "codex"
    day = home / "sessions" / datetime.datetime.now().strftime("%Y/%m/%d")
    day.mkdir(parents=True)
    os.environ.update(LOCALAPPDATA=d, CODEX_HOME=str(home))
    from app import QApplication, Companion, QLocalServer
    from transport import name, send
    from observe import quota_view
    from state import allow_whisper

    db = sqlite3.connect(home / "thread_history_1.sqlite")
    db.executescript(
        """create table thread_turns(thread_id,turn_id,rollout_ordinal,root_turn_id,started_at,status);
    create table thread_items(thread_id,turn_id,rollout_ordinal,item_id,item_type,completed_at_ms,item_json);"""
    )
    q = QApplication([])
    q.setQuitOnLastWindowClosed(False)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    assert server.listen(name("qa-ownership"))
    gui = Companion("qa-ownership", server)
    gui.config.update(notifications=True, muted=False, randomActions=False)
    w = gui.work
    w.timer.stop()
    gui.tick.stop()
    notices = []
    shown = []
    w.notice.connect(lambda k, t, u: notices.append((k, t, u)))
    w.record = lambda row: shown.append(row) if "bubble" in row else None

    def events(t, *rows):
        with (day / ("rollout-" + t + ".jsonl")).open("a", encoding="utf8") as f:
            for kind, payload in rows:
                f.write(json.dumps(dict(type=kind, payload=payload, timestamp=clock())) + "\n")

    def meta(t, **kw):
        return ("session_meta", dict(id=t, timestamp=clock(), **kw))

    def task(turn, kind):
        return ("event_msg", dict(type=kind, turn_id=turn))

    def native(t, turn, kind, **extra):
        result = []
        message = dict(v=1, source="hook", thread=t, turn=turn, kind=kind, **extra)
        sender = threading.Thread(
            target=lambda: result.append(send("qa-ownership", message)), daemon=True
        )
        sender.start()
        deadline = time.monotonic() + 2
        while sender.is_alive() and time.monotonic() < deadline:
            q.processEvents()
            time.sleep(0.004)
        assert result == [True]
        pump(0.04)

    def pump(seconds=0.22):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            q.processEvents()
            w.poll()
            time.sleep(0.012)

    def assert_jump_matches(thread):
        assert gui.card.jump.isVisible()
        with patch("app.QDesktopServices.openUrl", return_value=True) as dispatch:
            gui.card.jump.click()
        dispatch.assert_called_once()
        assert dispatch.call_args.args[0].toString() == "codex://threads/" + thread

    try:
        root, one, child, two, root2, parallel, foreign = (uid() for _ in range(7))
        pump(0.05)
        events(root, meta(root, source="cli"), task(one, "task_started"))
        pump()
        assert w.last["thread"] == root
        # All inherited records deliberately carry timestamps from after the child was born.
        events(
            child,
            meta(
                child,
                source={"subagent": {"thread_spawn": {"parent_thread_id": root}}},
                parent_thread_id=root,
                thread_source="subagent",
                subagent_history_start_ordinal=3,
            ),
            task(one, "task_started"),
            task(one, "task_complete"),
            task(foreign, "task_complete"),
            (
                "event_msg",
                dict(
                    type="task_started",
                    turn_id=two,
                    turn_attribution=dict(root_turn_id=one, parent_turn_id=one),
                ),
            ),
            task(two, "task_complete"),
        )
        db.execute(
            "insert into thread_turns values(?,?,?,?,?,?)",
            (child, one, 1, one, int(time.time()), "completed"),
        )
        db.execute(
            "insert into thread_items values(?,?,?,?,?,?,?)",
            (child, one, 2, "copy", "commandExecution", 1, "{}"),
        )
        db.commit()
        native(child, two, "child-stop")
        native(child, one, "stop-attempt")
        native(root, one, "stop-attempt")
        pump()
        w.accept(
            dict(
                v=1, source="jsonl", thread=root, turn=one, kind="plan", progress="2/2", completed=True
            )
        )
        assert not any(k == "success" for k, t, u in notices) and w.last["state"] != "success"
        assert child + "/" + one not in w.ledger.turns and child + "/" + foreign not in w.ledger.turns
        assert len(w.ledger.view()["options"]) == 1
        events(root2, meta(root2, source="cli"), task(parallel, "task_started"))
        pump()
        gui.compose()
        events(root2, task(parallel, "task_complete"))
        pump()
        assert w.last["thread"] == root and not shown and len(gui.notices) == 1
        gui.card.close_card()
        gui.present_notice()
        assert shown[-1]["thread"] == root2 and gui.card.mode == "notice"
        assert_jump_matches(root2)
        events(root, task(one, "task_complete"), task(one, "task_complete"))
        native(root, one, "tool", tool="late")
        pump()
        gui.end_notice()
        assert [v["thread"] for v in shown] == [root2, root]
        assert_jump_matches(root)
        assert sum(n[0] == "success" for n in notices) == 2
        # A newer turn in the same thread removes the preceding unshown notice.
        new, nextturn = uid(), uid()
        gui.card.close_card()
        gui.compose()
        events(root, task(new, "task_started"), task(new, "task_complete"))
        pump()
        assert gui.notices
        events(root, task(nextturn, "task_started"))
        pump()
        assert not gui.notices
        native(root, nextturn, "tool", tool="read", call="x")
        pump()
        w.reducer.turns[(root, nextturn)].expires = time.monotonic() - 0.1
        w.refresh()
        assert w.last["state"] == "idle" and notices[-1][0] == "timeout"
        assert allow_whisper(400, 0, 5, 14, 22, 8, True, False, False)
        assert all(
            not allow_whisper(400, 0, 5, h, 22, 8, True, m, focus)
            for h, m, focus in ((22, False, False), (14, True, False), (14, False, True))
        )
        quota = quota_view(
            {"primary": {"usedPercent": 25, "windowDurationMins": 10080, "resetsAt": time.time() + 500}}
        )
        assert all(
            s in quota["text"] for s in ("7 天额度", "剩余 75%", "已用 25%", "下次重置", "更新于")
        )
        # Actual Work.received validates the read result's thread and lifecycle phase.
        billing = uid()
        events(root2, task(billing, "task_started"))
        pump()
        w.received(
            ("billing", root2, billing, "start"),
            dict(threadId=root2, estimatedUsageCreditsMicros=900000, nativeUsageUsdMicros=0),
        )
        events(root2, task(billing, "task_complete"))
        pump()
        w.received(
            ("billing", root2, billing, "end"),
            dict(threadId=root2, estimatedUsageCreditsMicros=1200000, nativeUsageUsdMicros=0),
        )
        gui.show_usage()
        gui.usage_selection(root2 + "/" + billing)
        view = gui.card.body.text()
        assert "估算积分 0.3" in view and "原生美元用量 $0" in view and "估算美元 暂未提供" in view
        gui.usage_selection(root + "/" + one)
        assert "缺少可靠起止基线" in gui.card.body.text()
        assert gui.card.turns.count() >= 3
        result = dict(
            real_named_pipe=True,
            rewritten_fork_timestamps=True,
            sqlite_inherited_rows_ignored=True,
            child_stop_ignored=True,
            completed_plan_no_notice=True,
            late_tool_and_duplicate_end_ignored=True,
            active_root_preferred=True,
            notifications_queued_and_drained=True,
            obsolete_notice_cancelled=True,
            selected_notice_routes_to_its_thread_uri=True,
            timeout_to_idle=True,
            quiet_mute_focus=True,
            quota_window_format=True,
            switchable_task_usage=True,
            official_shape_fixture_microcredit_delta=0.3,
            true_zero_preserved=True,
            unknown_fields_marked=True,
        )
        out.write_text(json.dumps(result, indent=2), encoding="utf8")
        print(json.dumps(result))
    finally:
        db.close()
        gui.shutdown()
        gui.pet.hide()
