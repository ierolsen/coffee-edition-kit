#!/usr/bin/env python3
"""Print log on main: what entered the queue and what the printer actually printed.

log/prints.jsonl holds one event per line and is only ever appended to; log/prints.md is
rebuilt from it as a table, newest first. prepare.py adds a "queued" event when a job enters
the queue (title, topic, pages); the print-log workflow adds "printed" or "failed" when the
Pico reports back after the printer finished.

Nightly issues (written from a note in notes/, see scripts/next_issue.py) also leave
"drafted" (built and archived but not printed, while printer.json has nightly off or dry-run),
"rejected" (build.mjs refused it, the first error is kept) and "skipped" (too late to print,
or its date already has an issue). Events about an inbox file carry its git blob id, so the
writer that pushed a file can find the event for exactly that version.

Times are stored in UTC and shown in prints.md in printer.json's "timezone" (default UTC).

Usage (print-log workflow):
  python3 scripts/printlog.py report --job ID --state printed|failed [--printer-job N[,N...]]
  python3 scripts/printlog.py render
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
import zoneinfo
from pathlib import Path

LOG_DIR = "log"
EVENTS = "prints.jsonl"
TABLE = "prints.md"
JOB_ID = re.compile(r"^\d{8}-\d{6}-\d{2}-[A-Za-z0-9._-]{1,40}$")
PRINTER_JOB = re.compile(r"^[0-9]{1,9}(,[0-9]{1,9}){0,19}$")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def zone(root="."):
    """printer.json's timezone (an IANA name like Europe/London), UTC when it names none."""
    path = Path(root) / "printer.json"
    name = (json.loads(path.read_text()) if path.exists() else {}).get("timezone") or "UTC"
    try:
        return zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        raise SystemExit("printer.json: unknown timezone %r (use an IANA name like Europe/London)" % name)


def local(ts, tz=None):
    """A UTC timestamp as "17 Oct 2026 07:30" in tz (UTC when None)."""
    dt = datetime.datetime.fromisoformat(ts).astimezone(tz or datetime.timezone.utc)
    return "%d %s %d %02d:%02d" % (dt.day, MONTHS[dt.month - 1], dt.year, dt.hour, dt.minute)


def blob_id(data):
    """The id git gives this content (what `git hash-object` prints)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def load(root):
    path = Path(root) / LOG_DIR / EVENTS
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(root, event):
    path = Path(root) / LOG_DIR / EVENTS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    render(root)


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ").strip() or "-"


def short(text, limit=90):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def render(root):
    tz = zone(root)
    jobs, problems = {}, {}
    for e in load(root):
        kind = e.get("event")
        if kind in ("queued", "drafted"):
            jobs[e["job"]] = dict(e, status=kind)
            problems.pop(e.get("source"), None)  # the fixed file made it; its rejection is history
        elif e.get("job") in jobs and kind in ("printed", "failed"):
            jobs[e["job"]].update(status=kind, done_at=e["at"], printer_job=e.get("printer_job", ""))
        elif kind in ("rejected", "skipped"):
            problems[e.get("source")] = dict(e, status=kind)
    rows = []
    for j in sorted(list(jobs.values()) + list(problems.values()), key=lambda j: j["at"], reverse=True):
        when = local(j["at"], tz)
        if j["status"] == "printed":
            when, status = local(j["done_at"], tz), "printed" + (" · printer job %s" % j["printer_job"] if j.get("printer_job") else "")
        elif j["status"] == "failed":
            when, status = local(j["done_at"], tz), "not printed"
        elif j["status"] == "drafted":
            status = "draft · not printed"
        elif j["status"] == "rejected":
            status = "rejected · " + short(j.get("error", ""))
        elif j["status"] == "skipped":
            status = "skipped · " + short(j.get("reason", ""))
        else:
            status = "queued" + (" · prints " + local(j["print_at"], tz) if j.get("print_at") else "")
        rows.append("| %s | %s | %s | %s | %s |" % (
            cell(when), cell(j.get("title", "")), cell(j.get("topic", "")), cell(j.get("pages", "")), cell(status)))
    name = getattr(tz, "key", "UTC")
    text = ["# Print log", "",
            "One row per print job, newest first. For a printed job the time is when the printer "
            "finished, otherwise when the event happened (%s). Built from `prints.jsonl`; do not "
            "edit it by hand." % name, "",
            "| When | Title | Topic | Pages | Status |",
            "|---|---|---|---:|---|"] + rows
    (Path(root) / LOG_DIR / TABLE).write_text("\n".join(text) + "\n", encoding="utf-8")


def report(root, job, state, printer_job):
    """Record what the Pico says happened to a queued job. Refuses anything malformed."""
    if not JOB_ID.match(job):
        raise SystemExit("not a queue job id: %r" % job)
    if state not in ("printed", "failed"):
        raise SystemExit("state must be printed or failed, not %r" % state)
    if printer_job and not PRINTER_JOB.match(printer_job):
        raise SystemExit("printer job must be numbers separated by commas, not %r" % printer_job)
    if not any(e.get("event") == "queued" and e.get("job") == job for e in load(root)):
        raise SystemExit("no queued job %s in the log" % job)
    append(root, {"event": state, "job": job, "at": utc_now(), "printer_job": printer_job})


def main():
    ap = argparse.ArgumentParser(description="Keep the print log on main.")
    ap.add_argument("--root", default=".", help="repository root (default: current folder)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="record what the Pico reported")
    r.add_argument("--job", required=True)
    r.add_argument("--state", required=True)
    r.add_argument("--printer-job", default="")
    sub.add_parser("render", help="rebuild prints.md from prints.jsonl")
    a = ap.parse_args()
    if a.cmd == "report":
        report(a.root, a.job, a.state, a.printer_job)
        print("logged %s for %s" % (a.state, a.job))
    else:
        render(a.root)


if __name__ == "__main__":
    sys.exit(main())
