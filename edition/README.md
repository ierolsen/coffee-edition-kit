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
- The layout: every line and box inside its own column, everything inside the page, at most 4 pages (the RADAR page comes on top). Every RADAR card inside its cell; with `--preflight`, a line free in every cell. A card that does not fit is named with the lines to cut.
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

### RADAR

An optional page at the back of the issue: five new AI methods from the night before (what to write
is in [STYLE.md](STYLE.md), section 11). It prints when `printer.json` has `"radar": true`. The
`radar` part sits in the issue file; a file can also hold a RADAR page alone (no `front`, only
`version`, `issue`, `date`, `print_time` and `radar`).

```json
"radar": {
  "date": "2026-10-17",
  "scanned": {"hf": 150, "arxiv": 403, "github": 8, "blogs": 10},
  "headline": "100× faster video answers, an open agent that runs code, better reasoning without training",
  "items": [
    {"id": "arxiv:2610.18615", "area": "VIDEO", "signal": "HF 344 upvotes", "name": "VideoJev",
     "what": "...", "how": "...", "when": "...",
     "number": {"value": "100×+", "says": "...", "quote": "the source's sentence, word for word"},
     "code": "github.com/MCG-NJU/VideoJev", "source": "Nanjing University MCG · arXiv 2610.18615"}
  ],
  "also": [{"id": "arxiv:2610.18773", "title": "Jeva: System One Models from First Principles", "text": "..."}]
}
```

- `items` holds exactly 5 cards; each `id` is a candidate in that night's
  `sources/radar/<date>/index.json` (`arxiv:<id>`, `github:<owner>/<repo>`, `blog:<lab>:<slug>`).
  `area` is in capitals; `code` has no `https://`. `number.quote` does not print; `scripts/radar.py
  check` reads it.
- `also` holds up to 6 lines; `title` is the candidate's title as is, the page prints the part before
  the colon.
- The page lays out as two rows of three cells (five cards and the list) and never runs onto a second
  page. It comes after the closing band and does not count against the four pages. Its head and footer
  come from the `radar_*` labels in `labels.json`.
- Sample: `fixtures/radar.edition.json`.

### Inline markup

`**bold**`, `*italic*`, `` `mono` ``, `!!accent colour!!`, `x_{sub}`, `x^{sup}`. A backslash prints the next character as is: `n\*(n+1)`.
