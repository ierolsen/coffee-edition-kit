#!/usr/bin/env python3
"""What the nightly routine writes next, and the checks around it.

    python3 scripts/next_issue.py pick              the note, date and issue number (JSON)
    python3 scripts/next_issue.py verify FILE       the written issue is exactly that pick
    python3 scripts/next_issue.py wait FILE         prepare's verdict on the pushed FILE
    python3 scripts/next_issue.py plan [--days 14]  the coming mornings' picks

Which note: the first note in notes/ that has not printed yet, in the order scripts/notes.py
sets (print_on dates first, then `order`, then the path in natural order). Every note prints
once. When none is left, pick says {"status": "no_notes"}; when two or fewer are left, it warns.

Printed means a "queued" event in log/prints.jsonl: only a live issue uses up its note and its
number. A "drafted" one (printer.json "nightly": "dry-run") does not, so the dry-run nights
before going live redraft the same note and the first live night prints issue 1. A drafted
issue still holds its own morning: a second issue for that date is refused.

The issue's date is the next morning whose print time (printer.json "edition_print_time", in
its "timezone") is still ahead, so a run after it writes tomorrow's paper, never one that
would print at once. verify still accepts this morning's issue up to 30 minutes after its
print time; prepare.py drops anything later than an hour.

Exit codes of wait: 0 queued or drafted, 2 rejected by prepare, 3 skipped, 4 no verdict in time.
"""
import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import notes as notes_mod  # noqa: E402
import prepare  # noqa: E402
import printlog  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EDITION_SUFFIX = prepare.EDITION_SUFFIX
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
ISSUES = prepare.ISSUES  # nightly issues are kept on main under issues/YYYY/MM/
LATE = datetime.timedelta(minutes=30)   # verify accepts this morning's issue this long after print time
FEW = 2                                 # warn when this many notes or fewer are left
DEFAULT_PRINT_TIME = "07:30"


class Context:
    def __init__(self, root, cfg, notes, warnings=()):
        self.root, self.cfg, self.notes = Path(root), cfg, notes
        self.mode = cfg.get("nightly", "off")
        self.print_time = cfg.get("edition_print_time") or DEFAULT_PRINT_TIME
        self.tz = prepare.zone(cfg)
        self.warnings = list(warnings)
        self.events = printlog.load(root)


def load_context(root=ROOT):
    cfg = prepare.load_settings(Path(root))
    found, warnings = notes_mod.discover(root)
    return Context(root, cfg, found, warnings)


def issue_date(now, print_time, tz):
    """The next local morning whose print time is still ahead of `now`."""
    local = now.astimezone(tz)
    if local < print_at(local.date(), print_time, tz):
        return local.date()
    return local.date() + datetime.timedelta(days=1)


def print_at(day, print_time, tz):
    hour, minute = (int(x) for x in print_time.split(":"))
    return datetime.datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)


def nightly_inbox(root, skip=None):
    """Nightly issues waiting in inbox/, other than `skip`: [(path, issue)]."""
    found = []
    for path in sorted((Path(root) / "inbox").glob("*" + EDITION_SUFFIX)):
        if skip is not None and path.resolve() == Path(skip).resolve():
            continue
        issue = prepare.read_issue(path)
        if issue and prepare.nightly_fields(issue):
            found.append((path, issue))
    return found


def previous(ctx, path):
    """Earlier nightly issues written from the same note (drafts included), oldest first."""
    out = []
    for e in ctx.events:
        if e.get("event") in ("queued", "drafted") and e.get("note") == path and e.get("date"):
            rel = "%s/%s/%s/%s" % (ISSUES, e["date"][:4], e["date"][5:7], e.get("source", ""))
            out.append({"date": e["date"], "event": e["event"], "title": e.get("title", ""),
                        "file": rel if (ctx.root / rel).is_file() else None})
    return sorted(out, key=lambda x: x["date"])


def pick_for(ctx, day, skip=None):
    """The issue for `day`; {"status": "already_prepared"} when that morning has one,
    {"status": "no_notes"} when every note has printed."""
    iso = day.isoformat()
    for e in ctx.events:
        if e.get("event") in ("queued", "drafted") and e.get("note") and e.get("date") == iso:
            return {"status": "already_prepared", "date": iso, "by": "log", "job": e.get("job"), "note": e["note"]}
    for path, issue in nightly_inbox(ctx.root, skip):
        if issue.get("date") == iso:
            return {"status": "already_prepared", "date": iso, "by": "inbox", "file": "inbox/" + path.name, "note": issue["note"]}
    printed = [e for e in ctx.events if e.get("event") == "queued" and e.get("note")]
    done = {e["note"] for e in printed}
    left = [n for n in notes_mod.in_order(ctx.notes, day) if n["path"] not in done]
    waiting = [n for n in ctx.notes if n["print_on"] and n["print_on"] > iso and n["path"] not in done]
    if not left:
        return {"status": "no_notes", "date": iso, "printed": len(done), "waiting": [n["path"] for n in waiting],
                "warnings": ctx.warnings + ["no unprinted note is ready: add a note to notes/ (see notes/README.md)"]}
    note = left[0]
    warnings = list(ctx.warnings)
    if len(left) - 1 <= FEW:
        warnings.append("%d note(s) left after this one: add more to notes/" % (len(left) - 1))
    when = print_at(day, ctx.print_time, ctx.tz)
    return {
        "status": "ready",
        "mode": ctx.mode,
        "date": iso,
        "weekday": DAYS[day.weekday()],
        "print_time": ctx.print_time,
        "timezone": getattr(ctx.tz, "key", "UTC"),
        "print_at": when.astimezone(datetime.timezone.utc).isoformat(),
        "issue": len(printed) + 1,
        "file": "inbox/%s%s" % (iso, EDITION_SUFFIX),
        "note": {k: note[k] for k in ("path", "abs_path", "title", "source", "license", "images", "words")},
        "remaining": len(left) - 1,
        "previous": previous(ctx, note["path"]),
        "warnings": warnings,
    }


def verify(ctx, file, now):
    """Reasons the written issue is not exactly the pick for its date, or not in time; [] if fine."""
    file = Path(file)
    issue = prepare.read_issue(file)
    if issue is None:
        return ["%s: not a readable issue (JSON object)" % file]
    try:
        day = datetime.date.fromisoformat(str(issue.get("date")))
    except ValueError:
        return ["date: YYYY-MM-DD, not %r" % issue.get("date")]
    want = pick_for(ctx, day, skip=file)
    if want["status"] == "already_prepared":
        return ["%s already has an issue (%s)" % (want["date"], want.get("job") or want.get("file"))]
    if want["status"] != "ready":
        return ["no note is left to print on %s" % want["date"]]
    errors = []
    if file.resolve() != (ctx.root / want["file"]).resolve():
        errors.append("file: must be %s" % want["file"])
    for key in ("note", "issue", "print_time"):
        expected = want["note"]["path"] if key == "note" else want[key]
        if issue.get(key) != expected:
            errors.append("%s: must be %r, not %r" % (key, expected, issue.get(key)))
    allowed = {p["src"] for p in want["note"]["images"]}
    for blocks in (issue.get("front") or [], (issue.get("results") or {}).get("blocks") or []):
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "image" and b.get("src") not in allowed:
                errors.append("%s: not a picture of %s (it may use: %s)" % (b.get("src"), want["note"]["path"], ", ".join(sorted(allowed)) or "none"))
    when = print_at(day, ctx.print_time, ctx.tz)
    if when < now - LATE:
        errors.append("too late: this issue printed at %s; the next run writes the next morning's" % printlog.local(when.isoformat(), ctx.tz))
    nxt = issue_date(now, ctx.print_time, ctx.tz)
    if day > nxt:
        errors.append("date %s is beyond the next print morning (%s)" % (day, nxt))
    return errors


# ---- after the push ----------------------------------------------------------------------

def verdict(events, name, blob):
    for e in events:
        if e.get("source") == name and e.get("blob") == blob and e.get("event") in ("queued", "drafted", "rejected", "skipped"):
            return e
    return None


def wait(file, timeout, poll):
    """Fetch main until prepare logs this exact file. Exit codes: 0 queued or drafted,
    2 rejected (fix the issue and push again), 3 skipped, 4 no verdict in time."""
    file = Path(file)
    blob = printlog.blob_id(file.read_bytes())
    deadline = time.monotonic() + timeout
    tz = prepare.zone(prepare.load_settings(ROOT))
    while True:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, check=False)
        shown = subprocess.run(["git", "show", "origin/main:log/prints.jsonl"], cwd=ROOT, capture_output=True, text=True)
        events = [json.loads(line) for line in shown.stdout.splitlines() if line.strip()]
        e = verdict(events, file.name, blob)
        if e and e["event"] == "queued":
            print("queued: job %s, %s page(s), prints %s" % (e["job"], e.get("pages"), printlog.local(e["print_at"], tz) if e.get("print_at") else "when the Pico sees it"))
            return 0
        if e and e["event"] == "drafted":
            print("drafted: job %s, %s page(s), PDF on the archive branch, not printed (nightly is not live)" % (e["job"], e.get("pages")))
            return 0
        if e and e["event"] == "rejected":
            print("rejected: " + e.get("error", ""))
            print("Fix the issue file and run scripts/commit_issue.sh again; the full report is in the prepare run's log.")
            return 2
        if e and e["event"] == "skipped":
            print("skipped: " + e.get("reason", ""))
            return 3
        if time.monotonic() > deadline:
            print("no verdict from prepare after %d s; see the Actions tab of the repository" % timeout)
            return 4
        time.sleep(poll)


# ---- the coming days ---------------------------------------------------------------------

def plan(ctx, start, days):
    """Picks for `days` mornings from `start`, as if each were printed live."""
    rows = []
    for i in range(days):
        day = start + datetime.timedelta(days=i)
        p = pick_for(ctx, day)
        if p["status"] == "ready":
            ctx.events.append({"event": "queued", "note": p["note"]["path"], "date": p["date"]})
        rows.append(p)
    return rows


def main():
    ap = argparse.ArgumentParser(description="Pick and check the nightly Coffee Edition issue.")
    ap.add_argument("--now", help="pretend it is this moment (ISO 8601 with offset), for tests")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pick", help="the note, date and issue number to write, as JSON")
    v = sub.add_parser("verify", help="check a written issue against its pick")
    v.add_argument("file")
    w = sub.add_parser("wait", help="wait for prepare's verdict on a pushed issue")
    w.add_argument("file")
    w.add_argument("--timeout", type=int, default=540)
    w.add_argument("--poll", type=int, default=20)
    pl = sub.add_parser("plan", help="the coming days' picks")
    pl.add_argument("--days", type=int, default=14)
    a = ap.parse_args()
    now = datetime.datetime.fromisoformat(a.now) if a.now else datetime.datetime.now(datetime.timezone.utc)

    if a.cmd == "wait":
        return wait(a.file, a.timeout, a.poll)
    ctx = load_context()
    if a.cmd == "pick":
        p = pick_for(ctx, issue_date(now, ctx.print_time, ctx.tz))
        print(json.dumps(p, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "verify":
        errors = verify(ctx, a.file, now)
        for e in errors:
            print("error: " + e)
        print("verify: " + ("FAILED" if errors else "OK, the issue matches its pick"))
        return 1 if errors else 0
    for p in plan(ctx, issue_date(now, ctx.print_time, ctx.tz), a.days):
        if p["status"] == "already_prepared":
            print("%s  already prepared (%s)" % (p["date"], p.get("note")))
        elif p["status"] == "no_notes":
            print("%s  no note left" % p["date"])
        else:
            print("%s %-9s #%03d  %s" % (p["date"], p["weekday"], p["issue"], p["note"]["path"]))
    for w in ctx.warnings:
        print("warning: " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
