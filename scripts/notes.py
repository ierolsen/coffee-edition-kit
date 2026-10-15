#!/usr/bin/env python3
"""The notes the nightly writer turns into issues: which ones, in what order, with what pictures.

A note is any Markdown file under notes/, except README.md files, files and folders whose name
starts with "_" or "." (drafts, templates), and notes whose frontmatter says `skip: true`. Its
id is its path in the repository, notes/<...>.md; an issue names it in its "note" field.

Frontmatter is optional: `key: value` lines between two `---` lines at the very top.
  title     what the writer is told the note is about; default: the first "# " heading, then
            the file name
  order     a number; lower prints first
  print_on  YYYY-MM-DD; the note waits until that morning, then goes before the others
  skip      true leaves the note out
  source    where the note's facts come from (a URL); the writer puts it in the sources line
  license   the source's license when it asks for credit (CC BY 4.0, ...)

Order: notes whose print_on has come (earliest first), then the rest by order, then by path
in natural order (2 before 10). A note with a print_on still ahead waits. A note is used once:
when every note has printed, the pick says "no_notes" until you add more.

Pictures: a note shows one with ![alt](figure.png) or ![[figure.png]], a path relative to the
note (not inside code, where it is only an example). The writer may use only those pictures, by their path in the repository. A picture
counts only when git tracks it (the cloud routine and GitHub Actions see committed files
only), it is png, jpg or webp, and it is at most 1.5 MB; anything else is a warning.

    python3 scripts/notes.py            lists the notes in print order, with warnings
"""
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES = "notes"
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp")
IMAGE_MAX_BYTES = 1500000  # the same limit edition/build.mjs applies
KEYS = ("title", "order", "print_on", "skip", "source", "license")
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)>\s]+)>?(?:\s+\"[^\"]*\")?\s*\)")
WIKI_IMAGE = re.compile(r"!\[\[([^\]|#]+?)(?:\|([^\]]*))?\]\]")
FENCED = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.M | re.S)
INLINE_CODE = re.compile(r"`[^`\n]+`")


def parse_frontmatter(text):
    """(fields, body, problem): the known keys of a leading --- block, the text after it, and
    why the block was ignored (None when it was read, or when there is none)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, text, "the frontmatter has no closing --- line"
    fields = {}
    for n, line in enumerate(lines[1:end], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            return {}, "\n".join(lines[end + 1:]), "frontmatter line %d is not `key: value`" % n
        key, raw = m.group(1), m.group(2).strip()
        if key in KEYS:
            fields[key] = scalar(raw)
    return fields, "\n".join(lines[end + 1:]), None


def scalar(raw):
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if raw.lower() in ("true", "yes"):
        return True
    if raw.lower() in ("false", "no"):
        return False
    if re.fullmatch(r"-?\d+(\.\d+)?", raw):
        return float(raw) if "." in raw else int(raw)
    return raw


def natural_key(path):
    """Sort key that reads numbers as numbers: 2-intro before 10-outro."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path)]


def tracked(root, paths):
    """The subset of repo-relative paths git tracks; empty outside a git checkout."""
    if not paths:
        return set()
    proc = subprocess.run(["git", "ls-files", "-z", "--", *paths], cwd=root, capture_output=True)
    if proc.returncode != 0:
        return set()
    return set(p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p)


def pictures(root, rel, body, warnings):
    """The pictures a note shows that an issue may carry: [{src, alt}] with src from the repo root."""
    body = INLINE_CODE.sub("", FENCED.sub("", body))  # an example in code is not a picture
    found = []
    for m in MD_IMAGE.finditer(body):
        found.append((m.group(2), m.group(1)))
    for m in WIKI_IMAGE.finditer(body):
        found.append((m.group(1).strip(), (m.group(2) or "").strip()))
    out, seen = [], set()
    for target, alt in found:
        if re.match(r"^[a-z]+://", target) or target.startswith("data:"):
            warnings.append("%s: %s is not a file in the repository; only local pictures can print" % (rel, target))
            continue
        path = (root / rel).parent / target
        try:
            src = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            warnings.append("%s: %s points outside the repository" % (rel, target))
            continue
        if src in seen:
            continue
        seen.add(src)
        if not src.startswith(NOTES + "/"):
            warnings.append("%s: %s is outside notes/" % (rel, target))
        elif path.suffix.lower() not in IMAGE_TYPES:
            warnings.append("%s: %s is not png, jpg or webp" % (rel, target))
        elif not path.is_file():
            warnings.append("%s: %s does not exist" % (rel, target))
        elif path.stat().st_size > IMAGE_MAX_BYTES:
            warnings.append("%s: %s is %.1f MB; pictures can be at most 1.5 MB" % (rel, target, path.stat().st_size / 1e6))
        else:
            out.append({"src": src, "alt": alt})
    committed = tracked(root, [p["src"] for p in out])
    for p in out:
        if p["src"] not in committed:
            warnings.append("%s: %s is not committed; commit it so the cloud can see it" % (rel, p["src"]))
    return [p for p in out if p["src"] in committed]


def discover(root=ROOT):
    """Every note with its fields, in path order, and the warnings found on the way."""
    root = Path(root)
    base = root / NOTES
    notes, warnings = [], []
    if not base.is_dir():
        return notes, ["there is no notes/ folder"]
    for path in sorted(base.rglob("*.md"), key=lambda p: natural_key(p.relative_to(root).as_posix())):
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(base).parts
        if path.name.lower() == "readme.md" or any(p.startswith((".", "_")) for p in parts):
            continue
        fields, body, problem = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if problem:
            warnings.append("%s: %s; the note is used without it" % (rel, problem))
            body = path.read_text(encoding="utf-8", errors="replace")
        if fields.get("skip") is True:
            continue
        heading = re.search(r"^#\s+(.+?)\s*#*\s*$", body, flags=re.M)
        note = {
            "path": rel,
            "abs_path": str(path.resolve()),
            "title": str(fields.get("title") or (heading.group(1) if heading else path.stem)),
            "order": fields.get("order"),
            "print_on": None,
            "source": str(fields["source"]) if fields.get("source") else None,
            "license": str(fields["license"]) if fields.get("license") else None,
            "images": pictures(root, rel, body, warnings),
            "words": len(body.split()),
        }
        if note["order"] is not None and not isinstance(note["order"], (int, float)):
            warnings.append("%s: order must be a number, not %r; ignored" % (rel, note["order"]))
            note["order"] = None
        if fields.get("print_on") is not None:
            try:
                note["print_on"] = datetime.date.fromisoformat(str(fields["print_on"])).isoformat()
            except ValueError:
                warnings.append("%s: print_on must be YYYY-MM-DD, not %r; ignored" % (rel, fields["print_on"]))
        notes.append(note)
    return notes, warnings


def in_order(notes, day):
    """The notes that may print on `day` (a date), first one first; those still waiting are left out."""
    iso = day.isoformat()
    ready = [n for n in notes if not n["print_on"] or n["print_on"] <= iso]
    return sorted(ready, key=lambda n: (0 if n["print_on"] else 1, n["print_on"] or "",
                                        n["order"] if n["order"] is not None else float("inf"), natural_key(n["path"])))


def main():
    notes, warnings = discover()
    today = datetime.date.today()
    ordered = in_order(notes, today)
    waiting = [n for n in notes if n not in ordered]
    for i, n in enumerate(ordered, start=1):
        extra = ", %d picture(s)" % len(n["images"]) if n["images"] else ""
        print("%3d. %s  (%s%s)" % (i, n["path"], n["title"], extra))
    for n in waiting:
        print("  waits until %s: %s" % (n["print_on"], n["path"]))
    for w in warnings:
        print("warning: " + w)
    if "--json" in sys.argv:
        print(json.dumps({"notes": notes, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
