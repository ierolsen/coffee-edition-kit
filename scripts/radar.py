#!/usr/bin/env python3
"""RADAR: a back page of five new AI methods for every issue, from sites the cloud routine cannot reach.

    python3 scripts/radar.py collect [--date YYYY-MM-DD]   # GitHub Actions (radar.yml), before the routine
    python3 scripts/radar.py check <issue.edition.json>    # the radar part's facts against that night's index

collect reads Hugging Face Daily Papers, arXiv's new submissions (cs.CL, cs.LG, cs.AI), GitHub
trending and six lab blogs, keeps the candidates worth a card, stores their text under
sources/radar/<date>/texts/ and writes sources/radar/<date>/index.json. A source that fails is
recorded in the index and the others go on; the routine reads only these files.

check: every card is one of that night's candidates and was never printed before, every number
in a card stands in the candidate's stored text, the callout number's sentence is quoted from
it word for word, and the name and the code link are the candidate's own.

Standard library only: it runs in Actions, on the Mac and on the routine's cloud machine.
"""
import argparse
import datetime
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import next_issue  # noqa: E402  (issue_date: the same morning the routine will write for)
import prepare  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RADAR = Path("sources") / "radar"
UA = "coffee-edition-radar/1.0"   # no address or name: these requests go to outside services
CARDS = 5

HF_DAYS = 3          # Daily Papers lists read back from the day before the issue (weekends are thin)
HF_KEEP = 30         # by upvotes
ARXIV_CATS = ("cs.CL", "cs.LG", "cs.AI")
ARXIV_KEEP = 20      # new submissions that link their code, not already on Hugging Face
GITHUB_KEEP = 8
BLOG_DAYS = 4
BLOG_KEEP = 10
FULL_HF, FULL_ARXIV = 12, 6   # full texts: the candidates a card is most likely to come from
TEXT_MAX, README_MAX, POST_MAX = 25000, 10000, 8000

BLOGS = (
    ("openai", "OpenAI", "rss", "https://openai.com/news/rss.xml"),
    ("deepmind", "Google DeepMind", "rss", "https://deepmind.google/blog/rss.xml"),
    ("google-research", "Google Research", "rss", "https://research.google/blog/rss/"),
    ("huggingface", "Hugging Face", "rss", "https://huggingface.co/blog/feed.xml"),
    ("anthropic", "Anthropic", "html", "https://www.anthropic.com/news"),
    ("meta", "Meta AI", "html", "https://ai.meta.com/blog/"),
)
OPENAI_KINDS = {"Research", "Engineering", "Product", "Safety", "Security", "API"}
AI_REPO = re.compile(r"\b(llms?|agents?|agentic|ai|gpt|claude|gemini|model|models|rag|diffusion|transformers?|inference|"
                     r"embeddings?|prompts?|fine-?tun\w*|reasoning|neural|deep learning|machine learning|vision|speech|"
                     r"tokens?|mcp|rl|reinforcement|multimodal|vlm|lora|quantiz\w*)\b", re.I)


# ---- fetching ----------------------------------------------------------------------------

def fetch(url, accept=None, tries=3, timeout=40, token=None):
    """The body of `url` as bytes (gzip undone, some servers send it unasked); raises after `tries`."""
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    if token:
        headers["Authorization"] = "Bearer " + token
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                body = r.read()
            return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            if e.code in (403, 404, 410):
                break   # asking again will not help
        except Exception as e:  # timeouts, resets, DNS
            last = type(e).__name__ + ": " + str(e)[:120]
        time.sleep(2 + 3 * attempt)
    raise RuntimeError("%s: %s" % (url, last))


class Text(HTMLParser):
    """Readable text of an HTML page: paragraphs on their own lines, table cells split by " | ",
    math as its LaTeX alttext; navigation, scripts, the bibliography and the table of contents left out."""

    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "svg", "noscript", "button", "select"}
    SKIP_CLASS = re.compile(r"\bltx_(bibliography|page_footer|toclist|tocentry|authors|role_navigation)\b|\bltx_appendix\b")
    BLOCK = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "figcaption",
             "table", "br", "blockquote", "pre", "dd", "dt", "caption"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip, self.math = [], [], 0, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        void = tag in ("br", "img", "hr", "meta", "link", "input")
        skipping = tag in self.SKIP or bool(self.SKIP_CLASS.search(a.get("class") or ""))
        if tag == "math" and not self.skip:
            self.out.append(" " + (a.get("alttext") or "") + " ")
        if not void:
            self.stack.append((tag, skipping, tag == "math"))
            self.skip += skipping
            self.math += tag == "math"
        if tag in self.BLOCK:
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append(" | ")

    def handle_endtag(self, tag):
        if not any(t == tag for t, _, _ in self.stack):
            return   # a void tag written as <br/>, or a stray end tag
        while self.stack:
            t, skipping, math = self.stack.pop()
            self.skip -= skipping
            self.math -= math
            if t == tag:
                break
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip and not self.math:
            self.out.append(data)

    def text(self):
        s = "".join(self.out).replace("\xa0", " ")
        lines = [re.sub(r"[ \t    ]+", " ", line).strip(" |") for line in s.split("\n")]
        return "\n".join(line for line in lines if line.strip())


def page_text(raw, part=None):
    """The text of an HTML page: its longest <article> or <main> (a blog page also has small
    <article> cards for other posts and models), or the whole page when it has neither."""
    s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw

    def text_of(chunk):
        p = Text()
        p.feed(chunk)
        return p.text()

    if part is None:
        blocks = [m.group(0) for tag in ("article", "main") for m in re.finditer(r"<%s[\s>].*?</%s>" % (tag, tag), s, re.S | re.I)]
        texts = [text_of(b) for b in blocks]
        if texts and max(len(t) for t in texts) > 400:
            return max(texts, key=len)
    return text_of(s)


def arxiv_text(arxiv_id):
    """The paper's full text from arxiv.org/html (LaTeXML), up to the references; None when there is no HTML version."""
    try:
        raw = fetch("https://arxiv.org/html/" + arxiv_id, tries=2)
    except RuntimeError:
        return None
    text = page_text(raw, part="whole")
    start = text.find("Abstract")
    text = text[start:] if 0 <= start < 4000 else text
    end = re.search(r"\n(References|Bibliography)\n", text)
    return (text[:end.start()] if end else text)[:TEXT_MAX]


# ---- the sources ---------------------------------------------------------------------------

def authors_of(names):
    names = [n for n in names if n]
    return {"authors": names[:3], "authors_total": len(names)}


def hf_papers(day):
    """Hugging Face Daily Papers of the HF_DAYS days before the issue, best upvoted first. A day
    the API refuses (one still ahead in UTC is answered with 400) is left out; all of them failing is an error."""
    seen, out, failed = {}, [], []
    for back in range(1, HF_DAYS + 1):
        d = (day - datetime.timedelta(days=back)).isoformat()
        try:
            listed = json.loads(fetch("https://huggingface.co/api/daily_papers?date=" + d, tries=2))
        except (RuntimeError, ValueError) as e:
            failed.append(str(e))
            continue
        for x in listed:
            p = x.get("paper") or {}
            pid = p.get("id")
            if not pid or pid in seen:
                continue
            seen[pid] = True
            org = (p.get("organization") or x.get("organization") or {}).get("fullname")
            out.append({
                "id": "arxiv:" + pid, "kind": "paper", "from": ["hf"], "title": " ".join((p.get("title") or "").split()),
                **authors_of([a.get("name") for a in p.get("authors") or []]), "org": org,
                "url": "https://arxiv.org/abs/" + pid, "code": p.get("githubRepo") or None,
                "hf_upvotes": p.get("upvotes", 0), "github_stars": p.get("githubStars"),
                "hf_day": d, "published": (p.get("publishedAt") or "")[:10],
                # the paper's own abstract; HF's ai_summary is a model's rewrite and is never a source
                "abstract": " ".join((p.get("summary") or "").split()),
            })
    if len(failed) == HF_DAYS:
        raise RuntimeError("; ".join(failed))
    out.sort(key=lambda c: -(c["hf_upvotes"] or 0))
    return out


def arxiv_new():
    """Today's new submissions in ARXIV_CATS (cross-lists and replacements left out); empty on the
    nights arXiv makes no announcement (Friday and Saturday, US time)."""
    ns = {"arxiv": "http://arxiv.org/schemas/atom", "dc": "http://purl.org/dc/elements/1.1/"}
    seen, out, listed = set(), [], None
    for cat in ARXIV_CATS:
        root = ET.fromstring(fetch("https://rss.arxiv.org/rss/" + cat))
        for it in root.iter("item"):
            if (it.findtext("arxiv:announce_type", namespaces=ns) or "").strip() != "new":
                continue
            m = re.search(r"abs/(\d{4}\.\d{4,5})", it.findtext("link") or "")
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            desc = " ".join((it.findtext("description") or "").split())
            abstract = desc.split("Abstract:", 1)[1].strip() if "Abstract:" in desc else desc
            listed = listed or (it.findtext("pubDate") or "")
            code = re.search(r"https?://github\.com/[\w.-]+/[\w.-]+", abstract)
            out.append({
                "id": "arxiv:" + m.group(1), "kind": "paper", "from": ["arxiv"], "title": " ".join((it.findtext("title") or "").split()),
                **authors_of([a.strip() for a in (it.findtext("dc:creator", namespaces=ns) or "").split(",")]), "org": None,
                "url": "https://arxiv.org/abs/" + m.group(1), "code": code.group(0).rstrip(".") if code else None,
                "categories": [c.text for c in it.findall("category")], "published": listed[:16],
                "abstract": abstract,
            })
    return out


def github_trending():
    """Today's trending repositories on GitHub that are about AI, most new stars first."""
    page = fetch("https://github.com/trending?since=daily").decode("utf-8", "replace")
    out = []
    for a in re.findall(r'<article class="Box-row">(.*?)</article>', page, re.S):
        repo = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([\w.-]+/[\w.-]+)"', a)
        if not repo:
            continue
        desc = re.search(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', a, re.S)
        desc = html.unescape(re.sub(r"<[^>]+>", "", desc.group(1))).strip() if desc else ""
        if not AI_REPO.search(desc + " " + repo.group(1).replace("-", " ")):
            continue
        num = lambda rx: int(re.search(rx, a, re.S).group(1).replace(",", "")) if re.search(rx, a, re.S) else None  # noqa: E731
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', a)
        out.append({
            "id": "github:" + repo.group(1), "kind": "repo", "from": ["github"], "title": repo.group(1),
            "url": "https://github.com/" + repo.group(1), "code": "https://github.com/" + repo.group(1),
            "stars": num(r'/stargazers"[^>]*>.*?</svg>\s*([\d,]+)'), "stars_today": num(r"([\d,]+) stars today"),
            "language": lang.group(1).strip() if lang else None, "abstract": desc,
        })
    out.sort(key=lambda c: -(c["stars_today"] or 0))
    return out[:GITHUB_KEEP]


def readme(repo, token=None):
    for url, accept in (("https://raw.githubusercontent.com/%s/HEAD/README.md" % repo, None),
                        ("https://api.github.com/repos/%s/readme" % repo, "application/vnd.github.raw")):
        try:
            return fetch(url, accept=accept, tries=2, token=token if "api.github" in url else None).decode("utf-8", "replace")[:README_MAX]
        except RuntimeError:
            continue
    return None


MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}, 20\d\d"


def listing_posts(key, base, page):
    """(url, date) pairs from a blog's listing page: each link with the first date that follows it."""
    s = page.decode("utf-8", "replace")
    host = re.match(r"https://[^/]+", base).group(0)
    rx = r'href="(/(?:news|research)/[a-z0-9-]+)"' if key == "anthropic" else r'href="(https://ai\.meta\.com/blog/[a-z0-9-]+/?)"'
    out, seen = [], set()
    for m in re.finditer(rx, s):
        url = m.group(1) if m.group(1).startswith("http") else host + m.group(1)
        if url in seen:
            continue
        seen.add(url)
        d = re.search(MONTH, s[m.end():m.end() + 1500])
        out.append((url, d.group(0) if d else None))
    return out


def parse_day(s):
    s = (s or "").replace(".", "")
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return parsedate_to_datetime(s).date()
    except (TypeError, ValueError):
        return None


def blog_posts(day):
    """The labs' posts of the last BLOG_DAYS days; one candidate per post, with the post's text."""
    since = day - datetime.timedelta(days=BLOG_DAYS)
    out, errors, blocked, last_block = [], [], {}, {}
    for key, lab, kind, url in BLOGS:
        try:
            raw = fetch(url)
            if kind == "rss":
                posts = []
                for it in ET.fromstring(raw).iter("item"):
                    cats = {c.text for c in it.findall("category")}
                    if key == "openai" and cats and not cats & OPENAI_KINDS:
                        continue
                    posts.append((it.findtext("link"), it.findtext("pubDate"), " ".join((it.findtext("title") or "").split()),
                                  html.unescape(re.sub(r"<[^>]+>", " ", it.findtext("description") or "")).strip()))
            else:
                posts = [(u, d, None, "") for u, d in listing_posts(key, url, raw)]
            for link, date, title, desc in posts:
                when = parse_day(date)
                if not link or not when or not (since <= when < day):
                    continue
                text = None
                try:
                    body = fetch(link, tries=1 if blocked.get(lab) else 2)
                    text = page_text(body)[:POST_MAX] or None
                    if not title:
                        t = re.search(r"<title>(.*?)</title>", body.decode("utf-8", "replace"), re.S)
                        title = html.unescape(t.group(1)).split("|")[0].split(" \\ ")[0].strip() if t else link
                except RuntimeError as e:
                    blocked[lab] = blocked.get(lab, 0) + 1
                    last_block[lab] = str(e).rsplit(": ", 1)[-1]
                slug = re.sub(r"[^a-z0-9-]+", "-", link.rstrip("/").rsplit("/", 1)[-1].lower())[:60]
                out.append({"id": "blog:%s:%s" % (key, slug), "kind": "post", "from": [key], "lab": lab,
                            "title": title or link, "url": link, "code": None, "published": when.isoformat(),
                            "abstract": desc or (text or "")[:600], "_text": text})
        except (RuntimeError, ET.ParseError) as e:
            errors.append("%s: %s" % (lab, e))
    for lab, n in blocked.items():   # the post stays a candidate with its feed summary
        errors.append("%s: %d post page(s) not readable (%s), kept with the feed's summary" % (lab, n, last_block[lab]))
    out.sort(key=lambda c: c["published"], reverse=True)
    return out[:BLOG_KEEP], errors


# ---- what was printed before ---------------------------------------------------------------

def printed(root, skip=None):
    """Candidate ids already printed: every work a RADAR page showed so far, as a card or in its
    list (prepare logs them with the job), and the same from the files in issues/ and inbox/.
    `skip` is a file name left out: the issue being checked."""
    ids = set()
    for e in prepare.printlog.load(root):
        if e.get("event") in ("queued", "drafted"):
            ids.update((e.get("radar") or []) + (e.get("radar_also") or []))
    for f in list((root / "issues").rglob("*.edition.json")) + list((root / "inbox").glob("*.edition.json")):
        if skip and f.name == skip:
            continue
        try:
            issue = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        radar = issue.get("radar") or {}
        ids.update(c.get("id") for c in (radar.get("items") or []) + (radar.get("also") or []) if isinstance(c, dict))
    return ids


def page_for(root, day):
    """The file of `day`'s RADAR page once it is queued (kept under issues/, or waiting in inbox/), or None."""
    for f in sorted((root / "issues" / day.strftime("%Y") / day.strftime("%m")).glob("*.edition.json")) + sorted((root / "inbox").glob("*.edition.json")):
        try:
            issue = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if issue.get("date") == day.isoformat() and issue.get("radar"):
            return str(f.relative_to(root))
    return None


# ---- collect -------------------------------------------------------------------------------

def default_day(root):
    """The morning the next routine run writes for, as next_issue.py decides it."""
    cfg = prepare.load_settings(root)
    now = datetime.datetime.now(datetime.timezone.utc)
    return next_issue.issue_date(now, cfg.get("edition_print_time") or next_issue.DEFAULT_PRINT_TIME, prepare.zone(cfg))


def safe(cid):
    return re.sub(r"[^A-Za-z0-9.-]+", "-", cid).strip("-") + ".txt"


def collect(day, root=ROOT, token=None, log=print):
    out_dir = root / RADAR / day.isoformat()
    texts = out_dir / "texts"
    texts.mkdir(parents=True, exist_ok=True)
    errors, scanned, groups = [], {}, {}
    done = printed(root)

    def source(name, fn, *args):
        t = time.time()
        try:
            got = fn(*args)
        except (RuntimeError, ET.ParseError, ValueError) as e:
            errors.append("%s: %s" % (name, e))
            got = []
        log("%-8s %4d in %.1fs" % (name, len(got[0]) if isinstance(got, tuple) else len(got), time.time() - t))
        return got

    hf = source("hf", hf_papers, day)
    arxiv = source("arxiv", arxiv_new)
    github = source("github", github_trending)
    posts, post_errors = source("blogs", blog_posts, day) or ([], [])
    errors += post_errors
    scanned = {"hf": len(hf), "arxiv": len(arxiv), "github": len(github), "blogs": len(posts)}

    on_hf = {c["id"]: c for c in hf}
    for c in arxiv:   # a new submission that is also on HF: one candidate, seen by both
        if c["id"] in on_hf:
            on_hf[c["id"]]["from"].append("arxiv")
    groups["hf"] = [c for c in hf if c["id"] not in done][:HF_KEEP]
    groups["arxiv"] = [c for c in arxiv if c["id"] not in on_hf and c["id"] not in done and c["code"]][:ARXIV_KEEP]
    groups["github"] = [c for c in github if c["id"] not in done]
    groups["blogs"] = [c for c in posts if c["id"] not in done]

    # full texts, politely (arXiv asks for no more than one request a second)
    for c in groups["hf"][:FULL_HF] + groups["arxiv"][:FULL_ARXIV]:
        text = arxiv_text(c["id"].split(":", 1)[1])
        time.sleep(1)
        if text:
            c["_text"] = text
    for c in groups["github"]:
        c["_text"] = readme(c["title"], token)
    candidates = groups["hf"] + groups["arxiv"] + groups["github"] + groups["blogs"]
    for c in candidates:
        text = c.pop("_text", None)
        c["text"] = None
        if text:
            (texts / safe(c["id"])).write_text(text + "\n", encoding="utf-8")
            c["text"] = "texts/" + safe(c["id"])
    for old in texts.iterdir():   # a rerun of the same night leaves no stale text behind
        if "texts/" + old.name not in {c["text"] for c in candidates}:
            old.unlink()

    index = {
        "version": 1, "date": day.isoformat(),
        "collected_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "scanned": scanned, "kept": {k: len(v) for k, v in groups.items()},
        "errors": errors, "printed_before": len(done), "candidates": candidates,
    }
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log("%d candidates, %d with text, %d errors -> %s" % (len(candidates), sum(1 for c in candidates if c["text"]), len(errors),
                                                         (out_dir / "index.json").relative_to(root)))
    for e in errors:
        log("  error: " + e)
    return index


# ---- check ---------------------------------------------------------------------------------

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers(text):
    """The numbers a text states, each with the spellings it may be written in on the page."""
    out = set()
    for n in NUMBER.findall(text):
        out.add(n)
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", n):   # 1,324 or 12,500.5 in English
            out.add(n.replace(",", ""))
    return out


def spellings(n):
    """How a number written in a card may stand in an English source: 18,6 -> 18.6, 1.324 -> 1324."""
    out = {n, n.replace(",", ".")}
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", n):
        out.add(n.replace(".", ""))
    return out


def flat(s):
    return " ".join(str(s).split())


def source_text(index_dir, c):
    meta = " ".join(str(c.get(k) or "") for k in ("id", "title", "url", "code", "org", "hf_upvotes", "github_stars",
                                                    "stars", "stars_today", "published", "lab"))
    meta += " " + " ".join(c.get("authors") or []) + " " + str(c.get("authors_total") or "")
    body = c.get("abstract") or ""
    if c.get("text"):
        body += "\n" + (index_dir / c["text"]).read_text(encoding="utf-8")
    return meta, body


def check(issue, root=ROOT, name=None):
    """(errors, warnings) of an issue's radar part against sources/radar/<date>/index.json.
    `name` is the issue's file name, so its own cards do not count as printed before."""
    radar = issue.get("radar")
    if not radar:
        return [], []
    errors = []
    index_dir = root / RADAR / str(radar.get("date") or issue.get("date"))
    try:
        index = json.loads((index_dir / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["radar: no candidate index at %s" % (index_dir / "index.json").relative_to(root)], []
    if radar.get("date") != index["date"]:
        errors.append("radar.date: %s, the index is for %s" % (radar.get("date"), index["date"]))
    if radar.get("scanned") != index["scanned"]:
        errors.append("radar.scanned: copy it from the index as is: %s" % json.dumps(index["scanned"]))
    by_id = {c["id"]: c for c in index["candidates"]}
    # the same page in another language (same date, other lang) is not a second printing
    same_day = set()
    for f in list((root / "issues").rglob("*.edition.json")) + list((root / "inbox").glob("*.edition.json")):
        if f.name == name:
            continue
        try:
            other = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if other.get("date") == issue.get("date") and other.get("radar") and (other.get("lang") or "tr") != (issue.get("lang") or "tr"):
            same_day |= {c.get("id") for c in (other["radar"].get("items") or []) + (other["radar"].get("also") or []) if isinstance(c, dict)}
    done = printed(root, skip=name) - same_day
    seen = set()
    items = radar.get("items") or []
    if len(items) != CARDS:
        errors.append("radar.items: %d cards, a RADAR page has %d" % (len(items), CARDS))
    for i, card in enumerate(items):
        at = "radar.items[%d]" % i
        c = by_id.get(card.get("id"))
        if not c:
            errors.append("%s.id: %s is not one of this night's candidates" % (at, card.get("id")))
            continue
        if card["id"] in seen:
            errors.append("%s.id: %s is on the page twice" % (at, card["id"]))
        seen.add(card["id"])
        if card["id"] in done:
            errors.append("%s.id: %s was printed before" % (at, card["id"]))
        meta, body = source_text(index_dir, c)
        everything = meta + "\n" + body
        have = numbers(everything)
        fields = [card.get(k) for k in ("name", "what", "how", "when", "source")]
        num = card.get("number") or {}
        fields += [num.get("value"), num.get("says")]
        for n in sorted({n for f in fields if f for n in NUMBER.findall(str(f))}):
            if not spellings(n) & have:
                errors.append("%s (%s): the number %s is not in the candidate's text" % (at, card["id"], n))
        name = flat(card.get("name") or "").lower()
        if name and name not in flat(everything).lower():
            errors.append("%s.name: %r does not appear in the candidate's title or text" % (at, card.get("name")))
        # the callout number: its sentence must stand in the source word for word, and hold the number
        quote = flat(num.get("quote") or "")
        value = NUMBER.findall(str(num.get("value") or ""))
        if not quote:
            errors.append("%s.number.quote: the source sentence the number comes from, word for word" % at)
        elif quote not in flat(body):
            errors.append("%s.number.quote: not found word for word in the candidate's text: %r" % (at, quote[:80]))
        elif not value or not all(spellings(v) & numbers(quote) for v in value):
            errors.append("%s.number.value: %r is not in its quote" % (at, num.get("value")))
        code = (card.get("code") or "").strip()
        if code:
            bare = lambda u: re.sub(r"^https?://", "", str(u or "")).rstrip("/").lower()  # noqa: E731
            if bare(code) != bare(c.get("code")) and bare(code) not in flat(body).lower():
                errors.append("%s.code: %s is not the candidate's code link (%s)" % (at, code, c.get("code")))
    # the headline sums up the cards: every number in it comes from one of them
    pool = set()
    for card in items:
        c = by_id.get(card.get("id"))
        if c:
            pool |= numbers("\n".join(source_text(index_dir, c)))
    for n in sorted(set(NUMBER.findall(str(radar.get("headline") or "")))):
        if not spellings(n) & pool:
            errors.append("radar.headline: the number %s is in none of the cards' texts" % n)
    for i, extra in enumerate(radar.get("also") or []):
        at = "radar.also[%d]" % i
        c = by_id.get(extra.get("id"))
        if not c:
            errors.append("%s.id: %s is not one of this night's candidates" % (at, extra.get("id")))
            continue
        if extra["id"] in seen:
            errors.append("%s.id: %s already has a card" % (at, extra["id"]))
        if extra["id"] in done:
            errors.append("%s.id: %s was printed before" % (at, extra["id"]))
        if flat(extra.get("title") or "") != flat(c["title"]):
            errors.append("%s.title: copy the candidate's title as is: %r" % (at, c["title"]))
        meta, body = source_text(index_dir, c)
        have = numbers(meta + "\n" + body)
        for n in sorted(set(NUMBER.findall(str(extra.get("text") or "")))):
            if not spellings(n) & have:
                errors.append("%s (%s): the number %s is not in the candidate's text" % (at, extra["id"], n))
    return errors, []


# ---- command line --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="read the sources and write sources/radar/<date>/")
    c.add_argument("--date", help="the issue date, YYYY-MM-DD (default: the morning the next routine run writes for)")
    k = sub.add_parser("check", help="check an issue's radar part against its night's index")
    k.add_argument("file")
    args = ap.parse_args(argv)
    if args.cmd == "collect":
        day = datetime.date.fromisoformat(args.date) if args.date else default_day(ROOT)
        cfg = prepare.load_settings(ROOT)
        if not cfg.get("radar"):
            print('radar: off in printer.json ("radar": false), nothing to collect')
            return 0
        if cfg.get("nightly", "off") == "off":
            print("radar: printer.json has nightly off, nothing to collect")
            return 0
        # a night whose RADAR page already went out keeps the candidates it was written from
        if page_for(ROOT, day):
            print("radar: the RADAR page of %s is already printed or queued (%s), its candidates stay as they are" % (day, page_for(ROOT, day)))
            return 0
        index = collect(day, ROOT, token=os.environ.get("GITHUB_TOKEN"))
        return 0 if index["candidates"] else 1
    issue = json.loads(Path(args.file).read_text(encoding="utf-8"))
    errors, warnings = check(issue, ROOT, name=Path(args.file).name)
    for w in warnings:
        print("warning: " + w)
    for e in errors:
        print("error: " + e)
    print("radar: %s" % ("ok" if not errors else "%d problem(s)" % len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
