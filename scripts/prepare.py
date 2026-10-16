#!/usr/bin/env python3
"""coffee-edition cloud step: turn documents in inbox/ into print jobs for the Pico.

For every file in inbox/ (HTML, PDF, JPEG or a Coffee Edition issue) this
creates queue/<job-id>/ with the formats listed in printer.json and records the
job in queue/index.json. The Pico later picks the best format its printer
accepts. Jobs older than keep_days are removed.

The queue lives under --queue-root, which the workflow publishes as the queue
branch (rewritten every run, so old print files drop out of history). Each PDF
is also copied to --archive-root/archive/YYYY/MM/ for the archive branch, and
every queued job gets a line in the print log on main (log/, see printlog.py).

An issue is printed at its print_time (HH:MM in printer.json's "timezone", an IANA name such
as Europe/London, default UTC) on its date, falling back to edition_print_time in printer.json.
The job carries that moment as print_at (UTC) and as print_local (the same moment as local
time, for the Pico's log), and the Pico holds it until then. Daylight saving time is handled
by the timezone database. Other documents print as soon as the Pico sees them.

A Coffee Edition issue (*.edition.json) goes through edition/build.mjs, which
paginates it and checks the PDF before anything is queued. If that check fails,
no job is created, the issue stays in inbox/ for a fixed version, the first error
goes to the print log as "rejected", and the reasons are written to
edition-failures.txt so the workflow can fail loudly.

Pictures in an issue are files next to its note in notes/; build.mjs reads them from the repo.

A nightly issue (one that names the `note` it was written from, written by the nightly
routine from scripts/next_issue.py) has two more guards, so a paper never comes
out at a wrong hour or twice: it is dropped ("skipped" in the log, removed from
inbox/) when its print time passed more than an hour ago or when its date already
has an issue. It is printed only while printer.json has "nightly": "live"; with
"off" or "dry-run" it is built and archived as a "drafted" event and never queued.

Printers that take only raster (many cheap lasers) get image/pwg-raster, rendered from the
PDF by scripts/pwg.py.

Usage:  python3 scripts/prepare.py [--root DIR] [--queue-root DIR] [--archive-root DIR]
Needs:  pdftoppm and pdfinfo (poppler-utils) for JPEG pages, PWG raster and page counts,
        Chrome/Chromium or WeasyPrint for HTML,
        Node 22+, Chrome/Chromium and pdftotext for editions.
"""

import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import zoneinfo
from pathlib import Path

import printlog
import pwg

DEFAULTS = {
    "formats": ["application/pdf", "image/jpeg"],  # what to prepare for the Pico
    "jpeg_dpi": 300,
    "jpeg_quality": 85,
    "pwg_dpi": 300,
    "timezone": "UTC",           # IANA name the print times are in, like Europe/London
    "edition_print_time": None,  # "07:30": when issues print, in that timezone
    "nightly": "off",            # nightly issues: off | dry-run (built, never printed) | live
    "grayscale": False,
    "keep_days": 3,
    "radar": False,              # the RADAR back page: five new AI methods every night (radar.yml)
}
PAGE_CSS = "<style>@page { size: A4; margin: 14mm; }</style>"
EDITION_SUFFIX = ".edition.json"
FAILURES = "edition-failures.txt"
ISSUES = "issues"  # nightly issues that became jobs or drafts are kept here, by date
STALE = datetime.timedelta(hours=1)  # a nightly issue later than this is dropped, not printed


class EditionRejected(Exception):
    """edition/build.mjs refused the issue; the message is its report."""


def load_settings(root):
    cfg = dict(DEFAULTS)
    path = root / "printer.json"
    if path.exists():
        cfg.update(json.loads(path.read_text()))
    return cfg


def slug(text):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")
    return s[:40] or "doc"


def html_to_pdf(src, dst):
    page_html = src.read_text(encoding="utf-8", errors="replace")
    if "@page" not in page_html:  # default to A4 unless the document sets its own page
        page_html = (re.sub(r"(<head[^>]*>)", r"\1" + PAGE_CSS, page_html, count=1, flags=re.I)
                     if re.search(r"<head[^>]*>", page_html, re.I) else PAGE_CSS + page_html)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(page_html, encoding="utf-8")
        candidates = [os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
        candidates += [shutil.which(exe) for exe in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
        for path in candidates:
            if not path or not os.path.exists(path):
                continue
            try:
                subprocess.run([path, "--headless=new", "--no-sandbox", "--disable-gpu",
                                "--no-pdf-header-footer", "--print-to-pdf-no-header",
                                "--print-to-pdf=" + str(dst), page.as_uri()],
                               check=True, timeout=120,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (subprocess.CalledProcessError, OSError):
                continue  # a broken install: try the next browser
            if dst.exists() and dst.stat().st_size > 0:
                return
        if shutil.which("weasyprint"):
            subprocess.run(["weasyprint", str(page), str(dst)], check=True, timeout=120)
            return
    raise RuntimeError("no HTML to PDF converter found (install Chrome or WeasyPrint)")


def read_issue(src):
    """The issue as a dict, or None when it is not readable JSON (build.mjs then says why)."""
    try:
        issue = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return issue if isinstance(issue, dict) else None


def nightly_fields(issue):
    """What a nightly issue adds to its log events; {} for any other document."""
    if not issue or not isinstance(issue.get("note"), str) or not issue["note"].strip():
        return {}
    return {"note": issue["note"], "issue": issue.get("issue"), "date": issue.get("date")}


def nightly_problem(events, fields, print_at, now, tz=None):
    """Why a nightly issue must not print, or None: never at a wrong hour, never twice a day."""
    if print_at and datetime.datetime.fromisoformat(print_at) < now - STALE:
        return "past its print time (%s)" % printlog.local(print_at, tz)
    for e in events:
        if e.get("event") in ("queued", "drafted") and e.get("note") and e.get("date") == fields["date"]:
            return "this date already has an issue (%s)" % fields["date"]
    return None


def radar_ids(issue):
    """The works a RADAR page prints, for the log: its cards and its list. scripts/radar.py never
    offers them again."""
    radar = (issue or {}).get("radar") or {}
    ids = lambda key: [c["id"] for c in radar.get(key) or [] if isinstance(c, dict) and isinstance(c.get("id"), str)]  # noqa: E731
    out = {"radar": ids("items"), "radar_also": ids("also")}
    return {k: v for k, v in out.items() if v}


def first_error(report):
    lines = [line.strip() for line in str(report).splitlines() if line.strip()]
    errors = [line[len("error:"):].strip() for line in lines if line.startswith("error:")]
    return (errors or lines or ["unknown error"])[0]


def keep_issue(root, src, issue):
    """Keep a nightly issue on main (issues/YYYY/MM/<file>): the writer reads earlier issues
    from here so it does not repeat itself."""
    day = str((issue or {}).get("date") or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        dst = root / ISSUES / day[:4] / day[5:7] / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def consume(src):
    """Remove an inbox file that became a job (or was dropped)."""
    src.unlink()


def edition_to_pdf(root, src, dst):
    node = shutil.which("node")
    if not node:
        raise EditionRejected("node not found (Node 22+ is needed for editions)")
    cmd = [node, str(root / "edition" / "build.mjs"), str(src), "--pdf", str(dst), "--root", str(root)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print(proc.stdout.rstrip())
    if proc.returncode != 0 or not dst.exists():
        raise EditionRejected((proc.stdout + proc.stderr).strip())


def pdf_to_jpegs(pdf, outdir, cfg):
    cmd = ["pdftoppm", "-r", str(cfg["jpeg_dpi"]), "-jpeg",
           "-jpegopt", "quality=%d" % cfg["jpeg_quality"]]
    if cfg["grayscale"]:
        cmd.append("-gray")
    subprocess.run(cmd + [str(pdf), str(outdir / "p")], check=True, timeout=300)
    return sorted(outdir.glob("p-*.jpg"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))


def pdf_info(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=60).stdout
    pages = re.search(r"^Pages:\s+(\d+)", out, re.M)
    title = re.search(r"^Title:\s+(.+)$", out, re.M)
    return (int(pages.group(1)) if pages else None), (title.group(1).strip() if title else "")


def describe(src, pdf):
    """Title, topic and page count for the print log."""
    pages, pdf_title = pdf_info(pdf) if pdf else (1, "")
    if src.name.endswith(EDITION_SUFFIX):
        issue = json.loads(src.read_text(encoding="utf-8"))
        return issue.get("headline") or src.name, issue.get("short_title", ""), pages
    if src.suffix.lower() in (".html", ".htm"):
        m = re.search(r"<title[^>]*>(.*?)</title>", src.read_text(encoding="utf-8", errors="replace"), re.S | re.I)
        if m and m.group(1).strip():
            return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip(), "", pages
    return pdf_title or src.stem, "", pages


def zone(cfg):
    try:
        return zoneinfo.ZoneInfo(cfg.get("timezone") or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        raise SystemExit("printer.json: unknown timezone %r (use an IANA name like Europe/London)" % cfg.get("timezone"))


def schedule(src, cfg, workdir):
    """For an issue: the file to build (with print_time filled in) and print_at in UTC, or (src, None)."""
    issue = read_issue(src) if src.name.endswith(EDITION_SUFFIX) else None
    if issue is None:
        return src, None  # not an issue, or unreadable (build.mjs reports that)
    when = issue.get("print_time") or cfg.get("edition_print_time")
    if not isinstance(when, str) or not isinstance(issue.get("date"), str):
        return src, None
    try:
        day = datetime.date.fromisoformat(issue["date"])
        hour, minute = (int(x) for x in when.split(":"))
        local = datetime.datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone(cfg))
    except ValueError:
        return src, None  # build.mjs reports the malformed field
    if "print_time" in issue:
        return src, local.astimezone(datetime.timezone.utc).isoformat()
    issue["print_time"] = when  # the masthead shows the same time the Pico waits for
    copy = workdir / src.name
    copy.write_text(json.dumps(issue, ensure_ascii=False), encoding="utf-8")
    return copy, local.astimezone(datetime.timezone.utc).isoformat()


def entry(qroot, path):
    return {"path": path.relative_to(qroot).as_posix(), "size": path.stat().st_size}


def to_pdf(root, src, pdf):
    if src.name.endswith(EDITION_SUFFIX):
        edition_to_pdf(root, src, pdf)
    elif src.suffix.lower() == ".pdf":
        shutil.copyfile(src, pdf)
    else:
        html_to_pdf(src, pdf)


def build_job(root, qroot, src, job_id, cfg, workdir):
    """Make the job's files under qroot/queue/<job_id>/; returns (formats, pdf or None)."""
    jobdir = qroot / "queue" / job_id
    jobdir.mkdir(parents=True)
    formats = {}
    if src.suffix.lower() in (".jpg", ".jpeg"):
        dst = jobdir / "p-1.jpg"
        shutil.copyfile(src, dst)
        formats["image/jpeg"] = [entry(qroot, dst)]
        return formats, None
    pdf = workdir / (job_id + ".pdf")
    to_pdf(root, src, pdf)
    if "image/pwg-raster" in cfg["formats"]:
        raster = jobdir / "doc.pwg"
        pwg.pdf_to_pwg(pdf, raster, dpi=cfg["pwg_dpi"])
        formats["image/pwg-raster"] = [entry(qroot, raster)]
    if "image/jpeg" in cfg["formats"]:
        formats["image/jpeg"] = [entry(qroot, p) for p in pdf_to_jpegs(pdf, jobdir, cfg)]
    if "application/pdf" in cfg["formats"]:
        shutil.copyfile(pdf, jobdir / "doc.pdf")
        formats["application/pdf"] = [entry(qroot, jobdir / "doc.pdf")]
    return formats, pdf


def main():
    ap = argparse.ArgumentParser(description="Prepare print jobs for the coffee-edition Pico.")
    ap.add_argument("--root", default=".", help="repository root: inbox/, printer.json, log/ (default: current folder)")
    ap.add_argument("--queue-root", help="where queue/ lives, published as the queue branch (default: --root)")
    ap.add_argument("--archive-root", help="where archive/YYYY/MM/<job>.pdf go, published as the archive branch")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    qroot = Path(a.queue_root).resolve() if a.queue_root else root
    aroot = Path(a.archive_root).resolve() if a.archive_root else None
    inbox, queue = root / "inbox", qroot / "queue"
    index_path = queue / "index.json"
    queue.mkdir(parents=True, exist_ok=True)
    cfg = load_settings(root)
    tz = zone(cfg)
    index = json.loads(index_path.read_text()) if index_path.exists() else {"version": 1, "jobs": []}

    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    sources = sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith(".")) if inbox.exists() else []
    new = 0
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, src in enumerate(sources):
            edition = src.name.endswith(EDITION_SUFFIX)
            if not edition and src.suffix.lower() not in (".html", ".htm", ".pdf", ".jpg", ".jpeg"):
                print("skipped (unsupported type): %s" % src.name)
                continue
            stem = src.name[:-len(EDITION_SUFFIX)] if edition else src.stem
            job_id = "%s-%02d-%s" % (stamp, n, slug(stem))
            issue = read_issue(src) if edition else None
            nightly = nightly_fields(issue)
            seen = {"at": now.isoformat(), "source": src.name, "blob": printlog.blob_id(src.read_bytes()),
                    "title": (issue or {}).get("headline") or src.name, "topic": (issue or {}).get("short_title", "")}
            build_src, print_at = schedule(src, cfg, Path(tmp))
            if nightly:
                why = nightly_problem(printlog.load(root), nightly, print_at, now, tz)
                if why:
                    printlog.append(root, {"event": "skipped", **seen, "reason": why, **nightly})
                    consume(src)
                    print("skipped (%s), removed from inbox: %s" % (why, src.name))
                    continue
            draft = bool(nightly) and cfg.get("nightly") != "live"
            try:
                if draft:
                    formats, pdf = {}, Path(tmp) / (job_id + ".pdf")
                    to_pdf(root, build_src, pdf)
                else:
                    formats, pdf = build_job(root, qroot, build_src, job_id, cfg, Path(tmp))
            except EditionRejected as e:
                shutil.rmtree(queue / job_id, ignore_errors=True)
                failures.append("%s\n%s" % (src.name, e))
                # the same file version fails the same way on every run; log it once
                if not any(x.get("event") == "rejected" and x.get("blob") == seen["blob"] for x in printlog.load(root)):
                    printlog.append(root, {"event": "rejected", **seen, "error": first_error(e), **nightly})
                print("rejected (kept in inbox): %s" % src.name)
                continue
            title, topic, pages = describe(src, pdf)
            if aroot and pdf:
                kept = aroot / "archive" / now.strftime("%Y") / now.strftime("%m") / (job_id + ".pdf")
                kept.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pdf, kept)
            event = {"event": "drafted" if draft else "queued", "job": job_id, **seen,
                     "title": title, "topic": topic, "pages": pages, **nightly, **radar_ids(issue)}
            if print_at:
                event["print_at"] = print_at
            if not draft:
                job = {"id": job_id, "name": src.name, "title": title, "pages": pages,
                       "created": now.isoformat(), "formats": formats}
                if print_at:
                    job["print_at"] = print_at
                    job["print_local"] = printlog.local(print_at, tz) + " " + getattr(tz, "key", "UTC")
                index["jobs"].append(job)
            printlog.append(root, event)
            if nightly or (issue and issue.get("radar") and not issue.get("front")):  # a RADAR page queued on its own too
                keep_issue(root, src, issue)
            consume(src)
            if draft:
                print("drafted %s -> %s, %s page(s), not printed (printer.json nightly: %s)" % (
                    src.name, job_id, pages, cfg.get("nightly")))
                continue
            new += 1
            print("queued %s -> %s, %s page(s), %s (%s)" % (src.name, job_id, pages,
                  "prints at " + printlog.local(print_at, tz) if print_at else "prints when the Pico sees it", ", ".join(
                      "%s: %d file" % (k, len(v)) for k, v in formats.items())))

    cutoff = now - datetime.timedelta(days=cfg["keep_days"])
    kept_jobs = []
    for job in index["jobs"]:
        if datetime.datetime.fromisoformat(job["created"]) < cutoff:
            shutil.rmtree(queue / job["id"], ignore_errors=True)
            print("removed old job %s" % job["id"])
        else:
            kept_jobs.append(job)
    index["jobs"] = kept_jobs
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    print("%d new job(s), %d in queue" % (new, len(kept_jobs)))
    failures_path = root / FAILURES
    if failures:
        failures_path.write_text("\n\n".join(failures) + "\n")
        print("%d edition(s) rejected, see %s" % (len(failures), FAILURES))
    elif failures_path.exists():
        failures_path.unlink()


if __name__ == "__main__":
    main()
