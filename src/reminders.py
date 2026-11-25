import sqlite3
import uuid
import time
from datetime import datetime


def db(base):
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    c = sqlite3.connect(base / "reminders.sqlite3", timeout=1)
    c.execute(
        "CREATE TABLE IF NOT EXISTS reminder(id TEXT PRIMARY KEY,body TEXT,due REAL,thread TEXT,done INTEGER,notified INTEGER)"
    )
    c.execute("CREATE TABLE IF NOT EXISTS cadence(id TEXT PRIMARY KEY, last REAL)")
    return c


def add(base, args):
    text = args["text"].strip()
    due = (
        datetime.fromisoformat(args["due"].replace("Z", "+00:00"))
        if args.get("due")
        else None
    )
    if not text or len(text) > 256 or (due and not due.tzinfo):
        raise ValueError("invalid reminder")
    thread = str(uuid.UUID(args["thread"])) if args.get("thread") else ""
    ident = str(uuid.uuid4())
    with db(base) as c:
        c.execute(
            "INSERT INTO reminder VALUES(?,?,?,?,0,0)",
            (ident, text, due.timestamp() if due else None, thread),
        )
    return {"id": ident}


def items(base):
    with db(base) as c:
        return [
            dict(id=id, text=text, due=due, done=bool(done))
            for id, text, due, done in c.execute(
                "SELECT id,body,due,done FROM reminder ORDER BY done,due IS NULL,due,rowid"
            )
        ]


def toggle(base, ident):
    with db(base) as c:
        c.execute("UPDATE reminder SET done=1-done,notified=0 WHERE id=?", (ident,))
        c.execute("DELETE FROM cadence WHERE id=?", (ident,))


def delete(base, ident):
    with db(base) as c:
        c.execute("DELETE FROM reminder WHERE id=?", (ident,))
        c.execute("DELETE FROM cadence WHERE id=?", (ident,))


def complete(base, i):
    with db(base) as c:
        if not c.execute(
            "UPDATE reminder SET done=1,notified=0 WHERE id=? AND done=0", (i,)
        ).rowcount:
            raise ValueError("unknown reminder")
    return {"done": True}


def interval(remaining):
    for boundary, delay in [
        (7 * 86400, None),
        (3 * 86400, 86400),
        (86400, 43200),
        (12 * 3600, 14400),
        (3 * 3600, 3600),
        (3600, 1200),
        (0, 300),
        (-86400, 1800),
        (-7 * 86400, 21600),
    ]:
        if remaining > boundary:
            return delay
    return None


def pending(base):
    now = time.time()
    result = []
    with db(base) as c:
        c.execute("BEGIN IMMEDIATE")
        for ident, body, due, thread, done, notified, last in c.execute(
            "SELECT r.id,body,due,thread,done,notified,last FROM reminder r LEFT JOIN cadence m ON m.id=r.id"
        ).fetchall():
            if done:
                if notified:
                    continue
                c.execute("UPDATE reminder SET notified=1 WHERE id=?", (ident,))
                label = "已完成"
            else:
                if due is None:
                    continue
                delay = interval(due - now)
                # One immediate overdue alert for a newly created/imported reminder.
                if delay is None and not (due < now and not notified):
                    continue
                if (
                    last
                    and (delay is None or now - last < delay)
                    and not (due <= now and last < due)
                ):
                    continue
                if notified and last is None:
                    continue
                c.execute("INSERT OR REPLACE INTO cadence VALUES(?,?)", (ident, now))
                c.execute("UPDATE reminder SET notified=1 WHERE id=?", (ident,))
                label = "待办已到期" if due <= now else "待办将到期"
            result.append(
                dict(text=label + " · " + body, thread=thread, completed=bool(done))
            )
    return result
