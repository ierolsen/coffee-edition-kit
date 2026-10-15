"""Checks the nightly rules on hand-made notes, logs and inboxes. Runs in CPython:

    python3 scripts/test_nightly.py

A slip here prints a paper at a wrong hour, twice in a morning, or the same note twice, so each
rule is tried in a scratch git repository: the issue date around the print time, midnight and
the daylight saving switches (UTC, Europe/London, America/New_York), the frontmatter reader,
which notes count and in what order, pictures next to notes (committed or not), the issue
number with dry-run nights in between, "already prepared", "no notes", verify, prepare's guards
and the print log's table. Last, the kit's own notes/ folder must be readable and give a pick.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zoneinfo
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import next_issue as ni  # noqa: E402
import notes  # noqa: E402
import prepare  # noqa: E402
import printlog  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FIXTURE_PICTURE = REPO / "edition" / "fixtures" / "assets" / "fixture-slide.png"
UTC = datetime.timezone.utc
D = datetime.date


def at(text):
    return datetime.datetime.fromisoformat(text)


def git(root, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


def repo(tmp, name, files, settings=None):
    """A scratch git repository with notes and a printer.json; every file is committed."""
    root = tmp / name
    (root / "inbox").mkdir(parents=True)
    (root / "printer.json").write_text(json.dumps({"timezone": "UTC", "edition_print_time": "07:30", "nightly": "live", **(settings or {})}))
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "notes")
    return root


def context(root, events=()):
    ctx = ni.load_context(root)
    ctx.events = list(events)
    return ctx


def queued(path, date, n=None):
    return {"event": "queued", "note": path, "date": date, "job": "j%s" % (n or date), "source": date + ".edition.json"}


def drafted(path, date):
    return {"event": "drafted", "note": path, "date": date, "job": "d" + date, "source": date + ".edition.json"}


def check_dates():
    tz = zoneinfo.ZoneInfo
    cases = [
        # (now, timezone, print time, the morning it writes for)
        ("2026-10-05T07:29:00+00:00", "UTC", "07:30", D(2026, 10, 5)),
        ("2026-10-05T07:30:00+00:00", "UTC", "07:30", D(2026, 10, 6)),
        ("2026-10-05T23:59:00+00:00", "UTC", "07:30", D(2026, 10, 6)),
        # London: summer time ends 25 Oct 2026 (UTC+1 -> UTC+0)
        ("2026-10-24T06:29:00+00:00", "Europe/London", "07:30", D(2026, 10, 24)),
        ("2026-10-25T07:29:00+00:00", "Europe/London", "07:30", D(2026, 10, 25)),
        ("2026-10-25T07:31:00+00:00", "Europe/London", "07:30", D(2026, 10, 26)),
        # New York: summer time ends 1 Nov 2026 (UTC-4 -> UTC-5); late evening is still the day before
        ("2026-10-31T23:00:00+00:00", "America/New_York", "07:30", D(2026, 11, 1)),
        ("2026-11-01T12:29:00+00:00", "America/New_York", "07:30", D(2026, 11, 1)),
        ("2026-11-01T12:31:00+00:00", "America/New_York", "07:30", D(2026, 11, 2)),
        ("2026-11-02T03:00:00+00:00", "America/New_York", "07:30", D(2026, 11, 2)),
    ]
    for now, zone, when, want in cases:
        got = ni.issue_date(at(now), when, tz(zone))
        assert got == want, (now, zone, got, want)
    utc = lambda day, zone: ni.print_at(day, "07:30", tz(zone)).astimezone(UTC).strftime("%H:%M")  # noqa: E731
    assert utc(D(2026, 10, 24), "Europe/London") == "06:30" and utc(D(2026, 10, 26), "Europe/London") == "07:30"
    assert utc(D(2026, 10, 31), "America/New_York") == "11:30" and utc(D(2026, 11, 2), "America/New_York") == "12:30"
    print("dates ok: %d cases around print time, midnight and both daylight saving switches; print_at follows the clock change" % len(cases))


def check_frontmatter():
    fields, body, problem = notes.parse_frontmatter('---\ntitle: "A: B"\norder: 3\nprint_on: 2026-11-01\nskip: false\nother: x\n---\n# H\ntext')
    assert problem is None and fields == {"title": "A: B", "order": 3, "print_on": "2026-11-01", "skip": False}, fields
    assert body.strip().startswith("# H")
    assert notes.parse_frontmatter("# no frontmatter\n") == ({}, "# no frontmatter\n", None)
    _, _, problem = notes.parse_frontmatter("---\ntitle: x\n")
    assert problem and "closing" in problem, problem
    _, _, problem = notes.parse_frontmatter("---\njust words\n---\n")
    assert problem and "key: value" in problem, problem
    assert sorted(["notes/10-b.md", "notes/2-a.md", "notes/1-c.md"], key=notes.natural_key) == ["notes/1-c.md", "notes/2-a.md", "notes/10-b.md"]
    print("frontmatter ok: known keys, quotes, numbers and booleans read; broken blocks are named; natural order")


def check_discovery(tmp):
    png = FIXTURE_PICTURE.read_bytes()
    root = repo(tmp, "discover", {
        "notes/README.md": "# how to write notes\n",
        "notes/_template.md": "# a template\n",
        "notes/.hidden/x.md": "# hidden\n",
        "notes/10-late.md": "# Ten\n",
        "notes/2-early.md": "# Two\n",
        "notes/skipped.md": "---\nskip: true\n---\n# Skipped\n",
        "notes/ordered.md": "---\norder: 1\n---\n# First by order\n",
        "notes/dated.md": "---\nprint_on: 2026-10-20\ntitle: Dated\n---\nbody\n",
        "notes/broken.md": "---\ntitle: x\n# no closing line\n",
        "notes/pics/with-picture.md": "# Pictures\n![a figure](fig.png)\n![[fig.png|same one]]\n![web](https://example.com/x.png)\n![missing](nope.png)\n![big](big.png)\n![[../../printer.json]]\n"
                                      "Write `![x](in-code.png)` to show one.\n```markdown\n![y](in-fence.png)\n```\n",
        "notes/pics/fig.png": png,
        "notes/pics/big.png": b"\x89PNG" + b"0" * 1600000,
    })
    (root / "notes" / "pics" / "uncommitted.png").write_bytes(png)
    (root / "notes" / "pics" / "late.md").write_text("# Late\n![x](uncommitted.png)\n")
    found, warnings = notes.discover(root)
    paths = [n["path"] for n in found]
    assert "notes/README.md" not in paths and "notes/_template.md" not in paths and "notes/.hidden/x.md" not in paths, paths
    assert "notes/skipped.md" not in paths and "notes/broken.md" in paths, paths
    order = [n["path"] for n in notes.in_order(found, D(2026, 10, 15))]
    assert order[0] == "notes/ordered.md" and order.index("notes/2-early.md") < order.index("notes/10-late.md"), order
    assert "notes/dated.md" not in order, "a note dated ahead waits"
    order = [n["path"] for n in notes.in_order(found, D(2026, 10, 20))]
    assert order[0] == "notes/dated.md", "on its day a dated note goes first: %s" % order
    pics = next(n for n in found if n["path"] == "notes/pics/with-picture.md")
    assert pics["images"] == [{"src": "notes/pics/fig.png", "alt": "a figure"}], pics["images"]
    said = "\n".join(warnings)
    for words in ("broken.md: the frontmatter has no closing", "https://example.com/x.png is not a file", "nope.png does not exist",
                  "big.png is 1.6 MB", "printer.json is outside notes/", "uncommitted.png is not committed"):
        assert words in said, (words, said)
    assert "in-code.png" not in said and "in-fence.png" not in said, "an example inside code is not a picture"
    assert next(n for n in found if n["path"] == "notes/pics/late.md")["images"] == [], "an uncommitted picture is not offered"
    print("notes ok: README, _ and . files and skip: true left out; order, print_on and natural sort; only committed local pictures offered, the rest named")


def check_pick(tmp):
    root = repo(tmp, "pick", {"notes/001-a.md": "# A\n", "notes/002-b.md": "# B\n", "notes/003-c.md": "# C\n"})
    day = D(2026, 10, 16)
    p = ni.pick_for(context(root), day)
    assert p["status"] == "ready" and p["note"]["path"] == "notes/001-a.md" and p["issue"] == 1 and p["remaining"] == 2, p
    assert p["file"] == "inbox/2026-10-16.edition.json" and p["print_at"] == "2026-10-16T07:30:00+00:00" and p["timezone"] == "UTC", p
    assert any("2 note(s) left" in w for w in p["warnings"]), p["warnings"]
    # dry-run nights redraft the same note and keep the number; only live issues use them up
    dry = [drafted("notes/001-a.md", "2026-10-14"), drafted("notes/001-a.md", "2026-10-15")]
    p = ni.pick_for(context(root, dry), day)
    assert p["note"]["path"] == "notes/001-a.md" and p["issue"] == 1, ("drafts must not use up a note", p)
    assert [x["date"] for x in p["previous"]] == ["2026-10-14", "2026-10-15"], p["previous"]
    live = dry + [queued("notes/001-a.md", "2026-10-16")]
    p = ni.pick_for(context(root, live), D(2026, 10, 17))
    assert p["note"]["path"] == "notes/002-b.md" and p["issue"] == 2, p
    # a morning that has an issue, from the log (drafts too) or waiting in inbox/
    p = ni.pick_for(context(root, dry), D(2026, 10, 15))
    assert p["status"] == "already_prepared" and p["by"] == "log", p
    (root / "inbox" / "2026-10-18.edition.json").write_text(json.dumps({"note": "notes/002-b.md", "date": "2026-10-18"}))
    p = ni.pick_for(context(root, live), D(2026, 10, 18))
    assert p["status"] == "already_prepared" and p["by"] == "inbox", p
    (root / "inbox" / "2026-10-18.edition.json").unlink()
    done = [queued("notes/00%d-%s.md" % (i, c), "2026-10-1%d" % i) for i, c in ((1, "a"), (2, "b"), (3, "c"))]
    p = ni.pick_for(context(root, done), D(2026, 10, 20))
    assert p["status"] == "no_notes" and p["printed"] == 3, p
    rows = ni.plan(context(root), D(2026, 10, 16), 4)
    assert [r.get("note", {}).get("path") if r["status"] == "ready" else r["status"] for r in rows] == \
        ["notes/001-a.md", "notes/002-b.md", "notes/003-c.md", "no_notes"], rows
    print("pick ok: first unprinted note, numbers count live issues only, dry-run nights redraft, already prepared, no_notes, plan")


def check_verify(tmp):
    png = FIXTURE_PICTURE.read_bytes()
    root = repo(tmp, "verify", {"notes/001-a.md": "# A\n![fig](fig.png)\n", "notes/fig.png": png, "notes/other.png": png})
    ctx = context(root)
    want = ni.pick_for(ctx, D(2026, 10, 16))
    path = root / want["file"]
    issue = {"version": 1, "issue": want["issue"], "date": want["date"], "print_time": "07:30", "note": want["note"]["path"],
             "front": [{"type": "image", "src": "notes/fig.png"}]}
    path.write_text(json.dumps(issue))
    night = at("2026-10-16T04:15:00+00:00")
    assert ni.verify(ctx, path, night) == [], ni.verify(ctx, path, night)
    assert ni.verify(ctx, path, at("2026-10-16T07:59:00+00:00")) == [], "07:59 is still within 30 minutes"
    late = ni.verify(ctx, path, at("2026-10-16T08:01:00+00:00"))
    assert len(late) == 1 and late[0].startswith("too late"), late
    early = ni.verify(ctx, path, at("2026-10-14T12:00:00+00:00"))
    assert len(early) == 1 and "beyond the next print morning" in early[0], early
    for key, value in (("issue", 7), ("note", "notes/other.md"), ("print_time", "05:00")):
        path.write_text(json.dumps(dict(issue, **{key: value})))
        errors = ni.verify(ctx, path, night)
        assert len(errors) == 1 and errors[0].startswith(key + ":"), (key, errors)
    path.write_text(json.dumps(dict(issue, front=[{"type": "image", "src": "notes/other.png"}])))
    errors = ni.verify(ctx, path, night)
    assert len(errors) == 1 and "not a picture of notes/001-a.md" in errors[0], errors
    other = root / "inbox" / "2026-10-16-x.edition.json"
    path.rename(other)
    assert any(e.startswith("file:") for e in ni.verify(ctx, other, night)), "the file name is fixed"
    print("verify ok: exact pick, only the note's own pictures, 30 minutes of grace, no date beyond the next morning, fixed name")


def check_prepare_guards():
    now = at("2026-10-05T06:30:00+00:00")
    fields = {"note": "notes/n.md", "issue": 2, "date": "2026-10-05"}
    london = zoneinfo.ZoneInfo("Europe/London")
    assert prepare.nightly_problem([], fields, "2026-10-05T06:45:00+00:00", now) is None
    late = prepare.nightly_problem([], fields, "2026-10-05T05:00:00+00:00", now, london)
    assert late == "past its print time (5 Oct 2026 06:00)", late
    assert prepare.nightly_problem([], fields, "2026-10-05T05:31:00+00:00", now) is None, "within the hour still prints"
    twice = [{"event": "drafted", "note": "notes/m.md", "date": "2026-10-05"}]
    assert prepare.nightly_problem(twice, fields, "2026-10-05T06:45:00+00:00", now).startswith("this date already has an issue")
    assert prepare.nightly_fields({"note": "n.md", "issue": 2, "date": "x"}) == {"note": "n.md", "issue": 2, "date": "x"}
    assert prepare.nightly_fields({"headline": "manual"}) == {} and prepare.nightly_fields(None) == {}
    assert prepare.first_error("edition: x\n  error: page 3 is too full\n  error: other") == "page 3 is too full"
    try:
        prepare.zone({"timezone": "Mars/Olympus"})
        raise AssertionError("an unknown timezone must stop prepare")
    except SystemExit as e:
        assert "unknown timezone" in str(e)
    print("prepare ok: late issues and second issues of a day are refused, manual ones are not nightly, a bad timezone stops")


def check_log_table(tmp):
    root = tmp / "log-root"
    (root / "log").mkdir(parents=True)
    (root / "printer.json").write_text(json.dumps({"timezone": "Europe/London"}))
    rejected = {"event": "rejected", "at": "2026-10-05T02:40:00+00:00", "source": "2026-10-05.edition.json",
                "title": "Title", "topic": "Topic", "error": "page 5 needed"}
    queued_e = {"event": "queued", "job": "j", "at": "2026-10-05T02:55:00+00:00", "source": rejected["source"],
                "title": "Title", "topic": "Topic", "pages": 2, "print_at": "2026-10-05T06:30:00+00:00"}
    printlog.append(root, rejected)
    table = (root / "log" / "prints.md").read_text()
    assert "rejected · page 5 needed" in table and "(Europe/London)" in table, table
    printlog.append(root, queued_e)
    table = (root / "log" / "prints.md").read_text()
    assert "rejected" not in table.split("|---")[1] and "queued · prints 5 Oct 2026 07:30" in table, table
    printlog.append(root, {"event": "printed", "job": "j", "at": "2026-10-05T06:31:00+00:00", "printer_job": "22"})
    printlog.append(root, {"event": "skipped", "at": "2026-10-06T05:00:00+00:00", "source": "s.edition.json",
                           "title": "Late", "reason": "past its print time"})
    printlog.append(root, {"event": "drafted", "job": "d", "at": "2026-10-06T02:50:00+00:00", "source": "d.edition.json",
                           "title": "Draft", "pages": 2})
    table = (root / "log" / "prints.md").read_text()
    for words in ("| 5 Oct 2026 07:31 | Title | Topic | 2 | printed · printer job 22 |", "skipped · past its print time", "draft · not printed"):
        assert words in table, (words, table)
    try:
        printlog.report(root, "20261005-000000-00-nope", "printed", "1")
        raise AssertionError("a report for a job the log never queued must be refused")
    except SystemExit as e:
        assert "no queued job" in str(e)
    assert printlog.blob_id(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a", "git hash-object of hello"
    print("log ok: times in the printer's timezone, a fixed rejection leaves the table, printed, drafts and skips show, blob ids match git")


def check_repo_notes():
    """This repository's own notes/ folder reads without errors; its warnings are shown, not fatal."""
    found, warnings = notes.discover(REPO)
    raven = next((n for n in found if n["path"] == "notes/002-raven.md"), None)
    if raven:
        assert raven["source"] == "https://arxiv.org/abs/2609.33439" and raven["license"] == "CC BY 4.0", raven
    for w in warnings:
        print("  warning: " + w)
    print("notes/ ok: %d note(s) read%s" % (len(found), ", the Raven example carries its source and license" if raven else ""))


def main():
    check_dates()
    check_frontmatter()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        check_discovery(tmp)
        check_pick(tmp)
        check_verify(tmp)
        check_log_table(tmp)
    check_prepare_guards()
    check_repo_notes()
    return 0


if __name__ == "__main__":
    if not shutil.which("git"):
        sys.exit("git is needed for these checks")
    sys.exit(main())
