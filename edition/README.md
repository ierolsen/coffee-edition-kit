# The issue format and the build

A newspaper template that prints one article on A4. The layout is fixed; each morning only the content file changes. When text does not fit, a new page opens. No line is ever cut, and a clipped PDF is never printed.

```
inbox/<date>.edition.json  ->  build.mjs (lays out in Chrome, checks)  ->  PDF  ->  queue  ->  Pico
```

What to write is in [STYLE.md](STYLE.md). This file is the format and the checks.

## How it works

- **Fixed page types.** The front page (nameplate, headline, the start of the article), the results page (a full-width table and the analysis) and continuation pages (a thin running head and three columns). The takeaway band always sits at the foot of the last page.
- **Pagination.** Blocks fill three columns in order. A block that does not fit moves whole to a new continuation page. If the front part overflows, its continuation page comes before the results page; if the results part overflows, it goes at the end. A label travels with the block under it, a caption with the block above it. Page numbers are written once pagination is done.
- **Type never shrinks below 12 px.** When less than a quarter page spills onto a last page, only the leading tightens (14.5, 14.25, 14 px). If it still spills, the page prints and the report warns.
- **Fonts ship in the repository** (`fonts/`, SIL Open Font License), never from the internet: every machine gets the same widths and the same line breaks. Text is Newsreader, labels IBM Plex Mono, the nameplate Grenze Gotisch. Gloock carries the arrows Newsreader lacks; `‖` is drawn with lines. Nothing falls back to a system font.
- **Labels.** The words printed around the article (the nameplate, weekday and month names, "ISSUE 001 · PRINTED 07:30", "Continued on page 2", the caption leads "What it shows:" and "What it does:") come from [labels.json](labels.json). Copy it, translate it, and pass it with `--labels`, or edit it in place. `fixtures/labels-tr.json` is a Turkish example. Every `{placeholder}` must stay.

## Checks

`build.mjs` writes no PDF and exits 1 when any of these fails:

- The file: required fields, known block types, labels typed in capitals (in the labels' language, so Turkish `i` becomes `İ`), code lines of at most 30 characters, no em-dash or en-dash.
- The labels file: every key, 7 weekdays (Sunday first), 12 months, every placeholder kept.
- The fonts: all of them loaded, and every character present in one of the vendored fonts.
- The layout: every line and box inside its own column, everything inside the page, at most 4 pages (Fresh Ink comes on top, at most 4 more). Every Fresh Ink story inside its column and every chart's labels clear of each other; with `--preflight`, a line free on the Fresh Ink front page, and on every Fresh Ink page once it reaches four. A story that does not fit is named.
- The printed PDF itself: the same page count as the layout, and on every page the same number of characters as the layout (a clipped line would go missing here).

A part over about 800 words gets a warning: it usually means an extra page. The picture checks are under the block table below.

## Commands

```bash
node edition/build.mjs file.edition.json --pdf out.pdf --png edition/out   # build, with preview PNGs
node edition/build.mjs file.edition.json --draft --png edition/out         # look at it even when checks fail (never print it)
node edition/build.mjs file.edition.json --check                           # without a browser: fields and fonts
node edition/build.mjs file.edition.json --preflight                       # the full build where Chrome is, --check otherwise
node edition/build.mjs file.edition.json --labels my-labels.json           # another language's labels
node edition/test.mjs                                                      # the fixtures
```

`--check` is for a machine without Chrome. It runs the file checks and the font check; it reads each field's font from `edition.css` and the inline markup from `edition.js`, so it refuses what the browser would (`test.mjs` compares the two). It does not know the pages; the real build in GitHub Actions does.

`--preflight` is what `scripts/commit_issue.sh` runs before the nightly push. Where the machine has Chrome and poppler it runs the full build (no PDF kept), so an issue that runs past four pages or overflows a column is refused before the push. The cloud routine's machine has Playwright's Chromium in `/opt/pw-browsers`, and `findChrome()` looks there too. With Chrome but without poppler it runs the layout checks only (pages, columns, diagram labels, glyphs, which is where nearly every refusal comes from) and leaves the PDF checks to GitHub Actions. Without Chrome, or when Chrome does not start, the fonts do not load or the build takes over 120 seconds, it falls back to `--check`. The summary line says which one ran: the machine failing does not stop an issue, the issue failing does. `COFFEE_NO_CHROME=1` and `COFFEE_NO_POPPLER=1` act as if those were missing.

Needs Node 22+, Chrome or Chromium (`CHROME` picks one), and poppler (`pdfinfo`, `pdftotext`, `pdftoppm`).

To print an issue by hand, put the file in `inbox/` and push. `scripts/prepare.py` runs it through this build; when a check fails, no job is queued, the file stays in `inbox/` and the workflow goes red.

## The issue file

The example is [fixtures/raven.edition.json](fixtures/raven.edition.json).

```json
{
  "version": 1,
  "issue": 2,
  "date": "2026-10-17",
  "print_time": "07:30",
  "edition": "MORNING EDITION",
  "note": "notes/002-raven.md",
  "short_title": "Raven",
  "kicker": "TODAY'S PAPER · TECHNICAL REPORT",
  "byline": "EverMind AI · arXiv 2609.33439",
  "headline": "One agent that plans the work of all the others",
  "standfirst": "One or two sentences: what the reader learns today.",
  "sources": [{ "text": "arxiv.org/abs/2609.33439", "url": "https://arxiv.org/abs/2609.33439" }],
  "front": [ ...blocks... ],
  "results": { "headline": "...", "label": "RESULTS · MAOB, FIGURE 13", "table": { ... }, "caption": "...", "blocks": [ ... ] },
  "takeaway": "The one sentence to remember."
}
```

`print_time` (HH:MM in the `timezone` of `printer.json`) is when the issue prints on its date; without it, `edition_print_time` from `printer.json` applies. The masthead prints it as "ISSUE 002 · PRINTED 07:30". The queued job carries the same moment as `print_at` (UTC), and the Pico waits for it. An issue whose time has passed prints at once.

A nightly issue also carries `note`: the note it was written from, by its path in the repository (`notes/002-raven.md`). Such an issue prints only while `printer.json` has `"nightly": "live"`, and it is dropped when its print time passed more than an hour ago or its date already has an issue.

`results` is optional; without it the front page's text carries on onto continuation pages.

### Blocks

| type | fields | notes |
|---|---|---|
| `label` | `text` | section label, typed in capitals |
| `p` | `text`, optional `lead`, `lead_accent` | `lead`: a speaker name in mono at the start ("User") |
| `caption` | `text` | "What it shows:" is added in front (under code, "What it does:"); goes under every picture, table, diagram and code block |
| `steps` | `items`: `{text, symbol, accent, symbol_plain}` | numbered boxed steps; `symbol` prints in italic |
| `formulas` | `label`, `items`: `{name, formula, says}`, `symbols` | "In words:" and "Symbols:" are added; explain every symbol |
| `code` | `lines`, optional `wide` | at most 30 characters a line, indent with spaces; `"wide": true` spans the page and takes 88 |
| `table` | `columns`: `{label, align}`, `rows` | one-line cells; shorten names that do not fit a column |
| `bullets` | `items` | a list with square markers |
| `image` | `src`, optional `wide` | a picture next to the note, by its path in the repository (`notes/002-raven/figure-1.png`). Full width by default, `"wide": false` for a column |
| `diagram` | `mermaid`, optional `wide` | mermaid source, drawn during the build and printed as a 600 dpi picture. Column width by default, `"wide": true` for full width |
| `bars` | `rows`: `[label, number]`, `max`, `prefix`, `suffix`, `decimals`, `accent` | a horizontal bar chart; `accent` lists the rows to highlight (from 0) |

`image`, `diagram`, `bars` and `code` must be followed right away by a `caption` block. An issue carries at most 4 pictures (images and diagrams). A wide block spans all three columns: the text before it is balanced above it, the text after it continues below.

Picture checks: the file must exist inside the repository under `notes/`, be at most 1.5 MB and not be dark (a mean gray below 120 of 255 is refused, below 170 warned: the paper is black and white). A picture that prints below 150 dpi gets a warning. A diagram's labels must stay at least 9 px at the width they print; draw a wide flow top to bottom (`flowchart TD`) or make it `"wide": true`. Diagram text is checked for missing characters too.

The results table (`results.table`) is a `table` with extras:

- a cell can be `[before, after]`: it prints as `36.4 → **63.6**`;
- `chart: {column, label, min, max, ticks}` draws that column's before and after as a dumbbell;
- `delta: {column, label}`: after minus before;
- `decimals` (default 1), and `tone: "muted"` on a column.

### Fresh Ink

Optional pages at the back of the issue: new AI methods, models and tools from the night before, 5 to
17 cards on one to four pages, laid out like a newspaper (what to write is in [STYLE.md](STYLE.md),
section 11). It prints when `printer.json` has `"radar": true`. The `radar` part sits in the issue
file; a file can also hold Fresh Ink alone (no `front`, only `version`, `issue`, `date`,
`print_time` and `radar`). Alone, its front page opens with the full masthead (the ears, the
nameplate, the edition bar); after an article it opens under a running head. A reprint by hand (no
`note`) keeps its own date in the masthead and prints on `print_date` (YYYY-MM-DD), at that day's
print time.

```json
"radar": {
  "date": "2026-10-22",
  "scanned": {"hf": 150, "arxiv": 614, "github": 8, "blogs": 10, "trending": 26, "models": 8, "hn": 86, "letters": 25},
  "headline": "The night in one line",
  "items": [
    {"id": "arxiv:2610.25736", "area": "ROBOTICS", "signal": "111 HF upvotes", "name": "CEL",
     "headline": "96 Robots Learn From Each Other",
     "what": "...", "how": "...", "when": "...",
     "number": {"value": "79.2 → 98.3", "says": "...", "quote": "the source's sentence, word for word"},
     "source": "Yu et al. · arXiv 2610.25736", "link": "https://arxiv.org/abs/2610.25736",
     "chart": {"kind": "line", "title": "...", "what": "...", "table": "Table 11e, Yu et al.",
               "x": {"values": [1, 4, 8, 16, 32, 64, 96], "log": true, "title": "..."},
               "y": {"min": 0, "max": 100, "ticks": [0, 25, 50, 75, 100]}, "decimals": 1,
               "series": [{"name": "...", "points": [[4, 50.83], [96, 98.33]]}],
               "refs": [{"y": 79.17, "label": "start, 79.2%"}]}},
    {"id": "arxiv:2610.26203", "brief": true, "...": "..."}
  ],
  "also": [{"id": "arxiv:2610.22471", "title": "the candidate's title as is", "text": "..."}]
}
```

- `items` holds 5 to 17 cards; each `id` is a candidate in that night's
  `sources/radar/<date>/index.json` (`arxiv:<id>`, `github:<owner>/<repo>`, `model:<owner>/<name>`,
  `blog:<lab>:<slug>`, `web:<site>:<path>`). `area` is in capitals; `code` has no `https://`.
  `number.quote` does not print; `scripts/radar.py check` reads it.
- **Order.** The cards print in the writer's order. The first is the lead: its `headline` is the
  front page's H1 and its `what` the deck below it; the second stands next to it. Cards with
  `brief: true` (at most 4) go to IN BRIEF on the front page. The rest flow into two columns on the
  next pages, each card going to the column with more room (a later, shorter card may fill a gap
  first); a card is never split. The list (`also`, up to 6 lines) and the "How this paper is made"
  box close the last page. More than 4 pages is refused, with what to do.
- **A card.** The fields above, plus `headline` (the story's headline; without it the `name`
  prints), `link` (the address the QR code opens, with `https://`; without it, it comes from `code`
  or from an arXiv, GitHub or model id; a blog or web card must have it), and optional `brief` and
  `chart`.
- **Charts (`chart`).** Redrawn from the source's own table; `scripts/radar.py check` looks up every
  value and every number in its words in the source's text or tables. Common fields: `kind`, `title`
  (above the chart), `what` (the "What it shows" line below), `table` (the "Data:" line), optional
  `decimals` (0 to 3, how many decimals the values print with) and `unit` (printed after a value,
  "%" or " ms"). Three kinds:
  - `bars`: `rows`, 2 to 10 rows of `[label, number]`; optional `labels` (the value texts to print,
    like "≈1.55 s"; the bar length comes from `rows`), `sub` (a second line under each label, like
    the hardware), `accent` (the rows to print solid), `side` (`{label, values}`: one more column on
    the right) and `max`.
  - `groups`: `series`, the names of 2 or 3 series; `rows`, 2 to 8 rows of `[label, one number per
    series]`. The last series prints solid, the middle one hatched, the first outlined. With short
    series names the values stand in columns on the right; with long ones a legend goes on top and
    each value at the end of its bar.
  - `line`: `x` (`{labels: [...]}`, evenly spaced names, or `{values: [...], log: true}`, numbers;
    optional `title`), `y` (`{min, max, ticks}`), `series`, 1 to 3 lines (`{name, points: [[x, y],
    [x, y, "label"]]}`; the first line is bold), optional `refs` (`[{y, label}]`, dashed lines).
    Each line's last point is labelled with its value (or its own label), to the right, left, above
    or below, wherever it touches nothing.

  The page draws each chart at its story's width; when labels overlap, run out of the box or leave
  the bars too little room, the chart is refused with the reason. A value must be as the source
  writes it; its unit may change by a power of ten (1550 for the source's "1.55 s", 87 for "0.87").
- **Words.** The masthead ears, the edition bar, the flag, IN BRIEF, INSIDE, "Data:", how the paper
  is made and the source names come from the `fi_*` and `radar_*` labels in `labels.json`; the
  `scanned` numbers fill them in.
- **Samples:** `fixtures/fresh-ink.edition.json` (22 October 2026: 16 cards, 9 charts, 4 briefs,
  four pages) and `fixtures/radar.edition.json` (17 October 2026, five cards in the older format: no
  headlines or charts; it still prints as Fresh Ink).
- The QR codes are drawn with `vendor/qrcode.js` (qrcode-generator 1.4.4, MIT). `test.mjs` reads the
  printed pages at 300 dpi and checks that each code gives its own card's address (`qrdecode.py`,
  with zxing-cpp and Pillow: `pip install zxing-cpp pillow`; `QR_PYTHON` names the Python to use).
  Without them that one check is skipped.

### Inline markup

`**bold**`, `*italic*`, `` `mono` ``, `!!accent colour!!`, `x_{sub}`, `x^{sup}`. A backslash prints the next character as is: `n\*(n+1)`.
