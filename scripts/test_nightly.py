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
import radar  # noqa: E402

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


def radar_root(tmp):
    """A night's candidates by hand: five papers and a repository, each paper with a stored text."""
    root = Path(tmp) / "radar"
    night = root / "sources" / "radar" / "2026-10-18"
    (night / "texts").mkdir(parents=True)
    (root / "log").mkdir(parents=True)
    (root / "inbox").mkdir()
    (root / "log" / "prints.jsonl").write_text("")
    cands = []
    for i in range(1, 6):
        cid = "arxiv:2610.1000%d" % i
        text = ("Abstract\nMethod%d gates the update by agreement. It improves accuracy by %d.5 points "
                "over the baseline on 1,324 problems, at 2.7x lower cost.\n" % (i, i))
        (night / "texts" / radar.safe(cid)).write_text(text)
        cands.append({"id": cid, "kind": "paper", "from": ["hf"], "title": "Method%d: A Study" % i, "url": "https://arxiv.org/abs/2610.1000%d" % i,
                      "code": "https://github.com/lab/method%d" % i, "hf_upvotes": 100 + i, "abstract": "Method%d in short." % i,
                      "text": "texts/" + radar.safe(cid), "authors": ["A. Author"], "authors_total": 3})
    cands.append({"id": "github:lab/tool", "kind": "repo", "from": ["github"], "title": "lab/tool", "url": "https://github.com/lab/tool",
                  "code": "https://github.com/lab/tool", "stars_today": 812, "abstract": "A tool that cuts tokens by 40x.", "text": None})
    (night / "index.json").write_text(json.dumps({"version": 1, "date": "2026-10-18", "scanned": {"hf": 150, "arxiv": 400, "github": 8, "blogs": 9},
                                                  "errors": [], "candidates": cands}))
    card = lambda i: {"id": "arxiv:2610.1000%d" % i, "area": "TRAINING", "signal": "HF %d upvotes" % (100 + i), "name": "Method%d" % i,  # noqa: E731
                      "what": "A method.", "how": "It gates the update by agreement.", "when": "With small models.",
                      "number": {"value": "+%d.5 pts" % i, "says": "on 1,324 problems, at 2.7x lower cost",
                                 "quote": "It improves accuracy by %d.5 points over the baseline on 1,324 problems" % i},
                      "code": "github.com/lab/method%d" % i, "source": "Author et al. · arXiv 2610.1000%d" % i}
    issue = {"version": 1, "issue": 2, "date": "2026-10-18", "print_time": "07:30",
             "radar": {"date": "2026-10-18", "scanned": {"hf": 150, "arxiv": 400, "github": 8, "blogs": 9},
                       "headline": "Five methods, 2.7x cheaper", "items": [card(i) for i in range(1, 6)],
                       "also": [{"id": "github:lab/tool", "title": "lab/tool", "text": "A tool that cuts tokens by 40x."}]}}
    return root, issue


def check_radar(tmp):
    """RADAR: every card is one of the night's candidates, never printed before, and every number
    in it stands in the candidate's text; the sources' parsers read canned pages without a network."""
    import copy
    root, good = radar_root(tmp)
    assert radar.check(good, root)[0] == [], radar.check(good, root)[0]

    def errs(change):
        issue = copy.deepcopy(good)
        change(issue["radar"])
        return radar.check(issue, root)[0]
    cases = [
        (lambda r: r["items"][0]["number"].__setitem__("value", "+9.5 pts"), "the number 9.5 is not in"),
        (lambda r: r["items"][0].__setitem__("how", "It reaches 61.2 points."), "the number 61.2 is not in"),
        (lambda r: r["items"][1]["number"].__setitem__("quote", "It improves everything"), "not found word for word"),
        (lambda r: r["items"][2].__setitem__("id", "arxiv:2610.99999"), "is not one of this night's candidates"),
        (lambda r: r["items"][3].__setitem__("code", "github.com/other/repo"), "is not the candidate's code link"),
        (lambda r: r["items"][4].__setitem__("name", "Methodx"), "does not appear in the candidate's title"),
        (lambda r: r.__setitem__("headline", "Five methods, 9x cheaper"), "radar.headline: the number 9"),
        (lambda r: r["scanned"].__setitem__("hf", 151), "copy it from the index as is"),
        (lambda r: r["also"][0].__setitem__("title", "Tool"), "copy the candidate's title as is"),
        (lambda r: r["also"][0].__setitem__("text", "Cuts tokens by 50x."), "the number 50 is not in"),
        (lambda r: r["items"].pop(), "4 cards, RADAR carries 5 to 17"),
    ]
    for change, want in cases:
        found = errs(change)
        assert any(want in e for e in found), (want, found)
    # printed works: a card or a list entry of any page prepare queued is never offered again
    printlog.append(root, {"event": "queued", "job": "j", "at": "2026-10-17T02:00:00+00:00", "source": "x.edition.json",
                           **prepare.radar_ids({"radar": {"items": [{"id": "arxiv:2610.10003"}], "also": [{"id": "github:lab/tool"}]}})})
    found = radar.check(copy.deepcopy(good), root)[0]
    assert any("arxiv:2610.10003 was printed before" in e for e in found), found
    assert any("radar.also[0].id: github:lab/tool was printed before" in e for e in found), found
    assert prepare.radar_ids({"front": []}) == {}, "an issue without RADAR adds nothing to its log line"
    # the pick: off unless printer.json says "radar": true; then it names the night's index
    assert ni.radar_pick(root, D(2026, 10, 18), {})["ready"] is False
    on = {"radar": True}
    assert ni.radar_pick(root, D(2026, 10, 18), on)["ready"] is True and ni.radar_pick(root, D(2026, 10, 18), on)["candidates"] == 6
    assert ni.radar_pick(root, D(2026, 10, 19), on)["ready"] is False
    wrong_day = copy.deepcopy(good)
    wrong_day["radar"]["date"] = "2026-10-17"
    assert any("radar.date: must be the issue's date" in e for e in ni.radar_problems(root, root / "inbox" / "x.edition.json", wrong_day))
    # a night's candidates stay once its page is queued, and only then
    assert radar.page_for(root, D(2026, 10, 18)) is None
    (root / "issues" / "2026" / "10").mkdir(parents=True)
    (root / "issues" / "2026" / "10" / "2026-10-18-note.edition.json").write_text(json.dumps(good))
    assert radar.page_for(root, D(2026, 10, 18)) == "issues/2026/10/2026-10-18-note.edition.json"
    # numbers: English thousands and decimal commas are the same number
    assert "1324" in radar.numbers("on 1,324 problems") and "18.6" in radar.spellings("18,6") and "1324" in radar.spellings("1.324")
    # the parsers, on canned pages
    html = ('<html><nav>Menu 99</nav><article><h1>Title ' + 'word ' * 120 + '</h1><p>Speed is <math alttext="2.8\\times"><mi>x</mi></math> faster.</p>'
            '<script>var x = 77;</script><table><tr><td>A</td><td>12.5</td></tr></table></article><footer>2026</footer></html>')
    text = radar.page_text(html)
    assert "Speed is" in text and "2.8\\times" in text and "12.5" in text and "Menu" not in text and "77" not in text, text
    canned = {
        "huggingface.co/api/daily_papers": json.dumps([{"paper": {"id": "2610.20001", "title": "X: Y", "upvotes": 50, "summary": "Real abstract 3.4.",
                                                                  "ai_summary": "Never this.", "authors": [{"name": "A"}, {"name": "B"}], "githubRepo": "https://github.com/a/x"},
                                                        "summary": "Real abstract 3.4."}]).encode(),
        "rss.arxiv.org": ('<?xml version="1.0"?><rss xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'
                          '<item><title>New One</title><link>https://arxiv.org/abs/2610.20002</link><description>arXiv:2610.20002v1 Announce Type: new  '
                          'Abstract: Code at https://github.com/b/new. Gains 4.2.</description><category>cs.CL</category><arxiv:announce_type>new</arxiv:announce_type>'
                          '<dc:creator>C, D</dc:creator><pubDate>Fri, 16 Oct 2026 00:00:00 -0400</pubDate></item>'
                          '<item><title>Old</title><link>https://arxiv.org/abs/2610.20003</link><description>Abstract: replaced</description>'
                          '<arxiv:announce_type>replace</arxiv:announce_type></item></channel></rss>').encode(),
        "github.com/trending": ('<article class="Box-row"><h2><a href="/o/agent-kit">o / agent-kit</a></h2><p class="col-9 color-fg-muted">An LLM agent toolkit.</p>'
                                '<span itemprop="programmingLanguage">Python</span><a href="/o/agent-kit/stargazers"><svg></svg> 1,234</a> 321 stars today</article>'
                                '<article class="Box-row"><h2><a href="/o/game">o / game</a></h2><p class="col-9">A platform game.</p> 999 stars today</article>').encode(),
    }
    real_fetch = radar.fetch
    radar.fetch = lambda url, **kw: next(v for k, v in canned.items() if k in url)
    try:
        hf = radar.hf_papers(D(2026, 10, 18))
        new = radar.arxiv_new()
        repos = radar.github_trending()
    finally:
        radar.fetch = real_fetch
    assert len(hf) == 1 and hf[0]["abstract"] == "Real abstract 3.4." and "Never" not in json.dumps(hf), hf
    assert [c["id"] for c in new] == ["arxiv:2610.20002"] and new[0]["code"] == "https://github.com/b/new", new
    assert [c["id"] for c in repos] == ["github:o/agent-kit"] and repos[0]["stars"] == 1234 and repos[0]["stars_today"] == 321, repos
    print("radar ok: off unless turned on; cards only from the night's candidates, never twice, every number and quote "
          "in the source text, the headline and the list too; HF, arXiv and GitHub pages parse offline")


def check_radar_sources():
    """The added RADAR sources on canned pages: HF Trending Papers, trending models with their cards,
    Hacker News and the newsletters, which only nominate and add their signal to a candidate."""
    import html as htmlmod
    trending = {"dailyPapers": [
        {"paper": {"id": "2610.30001", "title": "Fresh: A Method", "githubStars": 900, "upvotes": 40, "publishedAt": "2026-10-10T00:00:00.000Z",
                   "summary": "Fresh gains 7.5 points.", "githubRepo": "https://github.com/f/fresh", "authors": [{"name": "A"}]}},
        {"paper": {"id": "2412.20138", "title": "Old: Agents", "githubStars": 99999, "upvotes": 9, "publishedAt": "2024-12-28T00:00:00.000Z",
                   "summary": "Old.", "authors": []}}]}
    card = "---\nlicense: mit\n---\n\n# NewModel\n\n<!-- note -->\nNewModel is a 7B model that scores 61.2 on MMLU-Pro.\n\n" + "Details. " * 80
    hn = {"hits": [
        {"title": "NewModel is out on Hugging Face", "url": "https://huggingface.co/lab/NewModel", "points": 900, "num_comments": 300, "objectID": "1"},
        {"title": "A guide to fine-tuning small LLMs", "url": "https://example.com/post", "points": 300, "num_comments": 50, "objectID": "2"},
        {"title": "Show HN: a bread recipe", "url": "https://example.com/bread", "points": 800, "num_comments": 10, "objectID": "3"}]}
    letter = ('<?xml version="1.0"?><rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><title>Week</title>'
              '<pubDate>Fri, 16 Oct 2026 10:00:00 GMT</pubDate><content:encoded>' + htmlmod.escape(
                  '<a href="https://github.com/t/template">t</a> <a href="https://arxiv.org/abs/2610.30002">p</a> '
                  '<a href="https://github.com/u/agentkit">a</a> <a href="https://arxiv.org/abs/2610.30003">q</a> '
                  '<a href="https://arxiv.org/abs/2610.30004">r</a> <a href="https://arxiv.org/abs/2610.30005">s</a>')
              + '</content:encoded></item></channel></rss>')
    arxiv_api = ('<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(
        '<entry><id>http://arxiv.org/abs/2610.3000%dv1</id><title>Paper %d</title><summary>Abstract %d with 3.%d points.</summary>'
        '<published>2026-10-15T00:00:00Z</published><author><name>X</name></author></entry>' % (i, i, i, i) for i in (2, 3, 4)) + "</feed>")
    canned = [
        ("huggingface.co/papers/trending", '<div data-target="DailyPapers" data-props="%s"></div>' % htmlmod.escape(json.dumps(trending))),
        ("huggingface.co/api/models?", json.dumps([
            {"id": "lab/NewModel", "createdAt": "2026-10-12T00:00:00.000Z", "likes": 500, "downloads": 10, "pipeline_tag": "text-generation"},
            {"id": "someone/NewModel-GGUF", "createdAt": "2026-10-13T00:00:00.000Z", "likes": 900},
            {"id": "lab/OldModel", "createdAt": "2025-01-01T00:00:00.000Z", "likes": 9000}])),
        ("huggingface.co/api/models/", json.dumps({"id": "lab/NewModel", "likes": 500})),
        ("/raw/main/README.md", card),
        ("hn.algolia.com", json.dumps(hn)),
        ("raw.githubusercontent.com/t/template", "# Template\nA cookiecutter for Python libraries."),
        ("raw.githubusercontent.com/u/agentkit", "# AgentKit\nAn LLM agent toolkit with MCP tools."),
        ("export.arxiv.org", arxiv_api),
        ("example.com/post", "<html><article><h1>Fine-tuning</h1><p>" + "Fine-tune a 1B LLM in 20 minutes. " * 30 + "</p></article></html>"),
        ("interconnects", letter),
    ]
    real_fetch, real_letters = radar.fetch, radar.LETTERS
    def fake(url, **kw):
        for key, body in canned:
            if key in url:
                return body.encode()
        raise RuntimeError("%s: HTTP 404" % url)
    radar.fetch, radar.LETTERS = fake, (("interconnects", "Interconnects", "https://www.interconnects.ai/feed"),)
    try:
        papers = radar.hf_trending(D(2026, 10, 19))
        models = radar.hf_models(D(2026, 10, 19))
        hits, stories = radar.hn_stories(datetime.datetime(2026, 10, 18, 20, 0, tzinfo=UTC))
        links, items, errors = radar.letter_links(D(2026, 10, 19))
        have = {c["id"]: c for c in models}
        nominees = radar.nominated(stories, links, have)
    finally:
        radar.fetch, radar.LETTERS = real_fetch, real_letters
    assert [c["id"] for c in papers] == ["arxiv:2610.30001"] and papers[0]["github_stars"] == 900, "only recent trending papers"
    assert [c["id"] for c in models] == ["model:lab/NewModel"], "re-quantized and old models are left out"
    assert "61.2 on MMLU-Pro" in models[0]["abstract"] and "license" not in models[0]["_text"], "the card's prose, not its YAML"
    assert len(hits) == 3 and [h["objectID"] for h in stories] == ["1", "2"], "Hacker News: AI stories only, best first"
    assert items == 1 and len(links) == 3 and [k for _, _, k, _ in links] == ["paper", "paper", "paper"], links
    assert have["model:lab/NewModel"]["hn_points"] == 900 and "hn" in have["model:lab/NewModel"]["from"], "HN's link to a model page signals the model"
    ids = [c["id"] for c in nominees]
    assert "web:example.com:post" in ids and "arxiv:2610.30002" in ids and not any(i.startswith("github:t/") for i in ids), ids
    paper = next(c for c in nominees if c["id"] == "arxiv:2610.30002")
    assert paper["mentioned_in"] == ["Interconnects"] and paper["abstract"].startswith("Abstract 2"), paper
    print("radar sources ok: trending papers of the last month, new models with their cards (no re-uploads), HN stories "
          "about AI, newsletters a few links each; signals land on the candidate they point at")


def main():
    check_dates()
    check_frontmatter()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        check_discovery(tmp)
        check_pick(tmp)
        check_verify(tmp)
        check_log_table(tmp)
        check_radar(tmp)
    check_radar_sources()
    check_prepare_guards()
    check_repo_notes()
    return 0


if __name__ == "__main__":
    if not shutil.which("git"):
        sys.exit("git is needed for these checks")
    sys.exit(main())
