# How a Coffee Edition issue is written

Every morning the reader takes one issue off the printer and reads it with a coffee and a pen. Each issue is one note from `notes/`, written up the way a good newspaper writes up one story: the big picture, how it works, the numbers, the traps and how to use it, together. A summary, but not a shallow one.

The format (fields, blocks, inline markup) is in [README.md](README.md); the sample issue is [fixtures/raven.edition.json](fixtures/raven.edition.json). This file says what to write. Edit it: it is the voice of your paper.

## 0. About the reader

Edit this section to describe yourself; the nightly writer reads it every night.

- An engineer who wants to keep up with AI without drowning in it.
- Reads English comfortably. Knows Python. Not a mathematician: formulas need every symbol explained.
- Wants things they can use at work: what it is, when to reach for it, what goes wrong.
- Prefers short paragraphs and concrete examples to long explanations.

## 1. Source discipline

- Use only the note `next_issue.py pick` names (`note.abs_path`), and the pictures it lists (`note.images`).
- Add no number, quote, date or claim that is not in the note. Use the note's numbers as they are. Keep its nuances: corrections, "the slide says this, the paper says that", numbers it marks as its own estimate.
- When the note summarises a paper, check every claim against the note's tables. A paper's own summary sentence can contradict its table; the table wins.
- When the note has a `source`, put it in `sources`. When it has a `license` that asks for credit (CC BY), add a second source line that names the license and says the text is adapted, like the sample issue.

## 2. The skeleton

| field | what goes in |
|---|---|
| `version`, `issue`, `date`, `print_time`, `note` | the values from `pick`, exactly. `commit_issue.sh` refuses any difference. |
| `edition` | `"MORNING EDITION"` |
| `short_title` | the running head of later pages: the topic's short name ("Raven", "LoRA") |
| `kicker` | in capitals: `TODAY'S PAPER · <VENUE YEAR>` for a paper, `TODAY'S NOTE · <TOPIC>` otherwise |
| `byline` | for a paper "Madaan et al. · arXiv 2303.17651"; for a talk the speaker; for your own note, your name or the topic |
| `headline` | the idea, not the topic; at most about 70 characters |
| `standfirst` | one or two sentences: what the reader learns today |
| `sources` | the note's `source`, and the license line when it needs one; otherwise an empty list |
| `front` | the article (below) |
| `results` | only when the note has a numeric comparison worth a table: the main table and the analysis. Otherwise leave the field out. |
| `takeaway` | one sentence that carries the whole issue, worth remembering |

The article opens each section with a `label` block, typed in capitals:

1. `IN SHORT`: two or three sentences. The first names the subject naturally (the paper with its first author and year, or the topic) and the one problem it solves.
2. `WHY IT MATTERS`: two to four sentences. What you would get wrong without this.
3. Topic sections: three to five, titled by you. The mechanism, examples, numbers, traps and limits go here.
4. `HOW TO USE IT`: three to five `bullets`, for real work.

No questions, no quiz, no "test yourself". No slogan, page count or reading time in the masthead. No emoji.

## 3. Length and pages

- Aim for **two pages**: about 1200 to 1400 words. The front page holds about 700, each later page about 850. A long note may take three pages; more than four is refused.
- Do not drop what matters to make it fit, and do not pad or repeat. In a long note, pick the three to five most important points and give each its concrete example.
- When the last page is less than a quarter full, the build warns: tighten a few sentences or add one more useful detail from the note.

## 4. Writing: short, anchored, concrete

- One idea per paragraph. Split long sentences; about 25 words at most.
- Concrete first, general second: give the example, then the rule.
- Define a concept once, then always call it by the same name.
- No walls of text: after about four plain paragraphs, add a list, a table, steps or a diagram.
- Paragraphs of three or four sentences. One or two **bold anchors** each, so a skim catches the point.
- Lists of three to six items, one idea each.
- Every topic section has at least one concrete example from the note: its numbers, cases or code.
- Short flow chains are fine (`retrieve → rerank → generate`) when each step is defined in the text.

## 5. Language

1. **No em-dash and no en-dash** (the long dashes, Unicode U+2014 and U+2013). Use a comma, a colon, brackets or "to" ("68 to 82"). The build refuses both.
2. **Define every term the first time it appears** (what it is and what it does, half a sentence is enough). Metrics (EM, F1, BLEU, pass@k, accuracy) are terms too: say what they measure and whether higher or lower is better. Every number says what it counts.
3. Authors as "et al.".
4. Write numbers plainly: "100,000", not `10^5`.
5. Paper cannot be clicked: no URLs in the text. Addresses go in `sources`, which print at the foot of the front page.

## 6. Formulas

A formula nobody explains says nothing. If you include one, explain it fully; if you cannot, leave it out and say the idea in words.

- Formulas go only in a `formulas` block: each has `name` (what it is), `formula` (with inline markup: `QK^{T}`, `d_{k}`) and `says` (what it says in plain words, ideally with a small worked number).
- `symbols` explains **every symbol** of the formula: letters, subscripts, operators, functions. Assume nothing: `^{T}` is the transpose (rows become columns), `√` the square root, `∑` a sum.
- At most two or three formulas per issue. If one good sentence says the same, prefer the sentence.

## 7. Code

- If the note has code, the issue has **at least one** `code` block; if not, none. At most two blocks, at most 12 lines each.
- **At most 30 characters a line**: a column is narrow. Break a long call one argument per line, indent with spaces, mark skipped parts with `# ...`. The build refuses longer lines. Code that cannot be broken readably can be `"wide": true` (88 characters, full page width).
- Take the code **from the note**, never invent it.
- Right under the block comes a `caption` ("What it does:" is printed in front of it); the build refuses code without one. In two to four sentences tell someone who does not read code what it does, its input and output, and which line matters.
- For each named parameter in the code (`temperature=0`, `k=4`), one bullet: what it does, the value it got and why, and when you would change it, if the note says so. Do not invent explanations the note does not give.

## 8. Tables, steps and pictures

- Every `table`, `steps`, `formulas`, `image`, `diagram` and `bars` block gets a `caption` ("What it shows:" is printed in front): what it shows, how to read it (boxes, arrows, axes, rows), the numbers that matter and the one conclusion.
- Table cells are one line: shorten names ("Code Opt."), put units in the column name ("SCORE, %").
- **Diagram (`diagram`)**: if the note has a mermaid diagram, the issue should have one. Copy it and simplify it for a column: top to bottom (`flowchart TD`), at most three or four words a box, at most eight boxes; `<br/>` breaks a label in two. Use `"wide": true` for a flow that must run left to right. You may draw your own diagram when it really makes the idea easier.
- **Picture (`image`)**: use only the note's pictures (`note.images` in the pick), by their `src`. Open the file and look at it, then write the caption from what you see. Do not choose a dark picture: the paper is black and white, and the build refuses one that is too dark.
- **Bar chart (`bars`)**: to compare a result across a few numbers. Units with `prefix` or `suffix`, the most important row with `accent`; colour carries no meaning on paper.
- At most four pictures (images and diagrams). A picture never replaces the text: the article must read without it. Never write "as the figure shows"; refer to a picture by what it is.

## 9. Characters

The fonts are in the repository; a character none of them has makes the build refuse the issue. Known so far:

- **No Greek letters** except `π`. Use a Latin letter and explain it in `symbols` (`T` for temperature, `lr` for learning rate), or spell it ("theta").
- Available: `→ ← ↔ ↑ ↓ ≈ ≤ ≥ ≠ × ÷ · ± √ ∑ ∏ ∞ ∂ ∫ ² ³ ½ π`. `‖` is drawn with lines.
- Missing: `∈ ∇ ⇒ ≡ ∝ ⊕ ⊗ ∀ ∃ ℝ ⌈ ⌉ ⌊ ⌋ ✗ ►` and the check mark in running text.
- For subscripts and superscripts use the markup, not Unicode characters: `x_{0}`, `n^{2}`.
- Diagram labels print with the same fonts and follow the same rules.

## 10. Before you commit

`bash scripts/commit_issue.sh <file>` runs two checks itself: `next_issue.py verify` (the fields match the pick, the time has not passed, only the note's pictures) and `node edition/build.mjs <file> --preflight` (fields, blocks, line lengths, dashes, missing characters; where Chrome is available the pages and the PDF too, so an issue over four pages is refused before the push). After the push, GitHub Actions lays the issue out again and checks the PDF; when it refuses, the first error is shown, and you fix the file and run the same command again.

Read it once yourself before that:

- Does the first sentence of `IN SHORT` say today's one idea, and does the takeaway turn it into a sentence worth remembering?
- Is every term, metric and abbreviation defined the first time it appears? Every symbol of every formula?
- Is every number in the note? Do the claims match the note's tables?
- Does every table, picture and code block have its caption?
- Is there at least one visual anchor (a diagram, table, steps or bars)?

## 11. Fresh Ink (RADAR)

When `printer.json` has `"radar": true`, every issue carries **Fresh Ink** at the back: new AI
methods, models and tools from the night before, 5 to 17 cards, laid out like a newspaper. It is for
skimming, and it never takes the place of the issue. The field in the file is still called `radar`,
and so are the scripts (`radar.py`, `radar.yml`).

**The pages.** The front page: the FRESH INK flag, the first card's headline (the H1) and its `what`
(the deck), the first two cards side by side, IN BRIEF (up to four short cards) and INSIDE (what the
next pages hold). The inner pages: the other cards in two columns, each card going to the column with
more room. The last page closes with the "Also worth a look" list and the "How this paper is made"
box. One to four pages; a longer one is refused. Every card ends with a QR code to its source.

- **Material.** `radar.yml` collects the candidates into `sources/radar/<date>/` an hour or more
  before you run:
  - **Papers:** Hugging Face Daily Papers (the last three days, by upvotes), Hugging Face Trending
    Papers (papers with code from the last 30 days, by GitHub stars), and arXiv's new submissions of
    the day (cs.CL, cs.LG, cs.AI; those that link their code).
  - **Models:** new open models trending on Hugging Face (created in the last 45 days), with their
    model cards (`model:<owner>/<name>`). Re-quantized uploads and models made to remove safety are
    left out.
  - **Repositories:** GitHub's trending AI repositories, with their READMEs.
  - **Lab blogs:** OpenAI, Google DeepMind, Google Research, Hugging Face, Anthropic, Meta AI,
    Microsoft Research, Apple Machine Learning Research, NVIDIA (AI posts only), Ai2 and Mistral AI;
    at most two posts per lab a night.
  - **Signals, which only nominate:** Hacker News stories about AI from the last two days (80 points
    or more) and four newsletters (Interconnects, Import AI, Simon Willison, Latent Space). What they
    link to becomes a candidate, or adds their signal to one (`hn_points`, `mentioned_in`); another
    page Hacker News points at becomes a `web:<site>:<path>` candidate with the page's text. A card's
    facts always come from the primary source, never from a newsletter's commentary.

  `index.json` lists each candidate with its id, title, address (`url`), authors, code link, signals
  and `abstract`. When `text` is set, the full text (paper, README, model card or page) is under
  `texts/`; when `tables` is set, so are all of the source's tables, appendix included. The text stops
  at the references and at 20000 characters, the tables do not: a chart's data comes from them. If
  the pick says `radar.ready: false`, write no Fresh Ink and say why in the summary.
- **Source discipline.** Read only `index.json` and `texts/`, never the web. Every number, name and
  claim on a card, and every value and word of a chart, stands in that candidate's abstract, text or
  tables. Hugging Face's own summaries (`ai_summary`) are never collected and never a source. A work
  that was on an earlier Fresh Ink page, as a card or in a list, never comes back: `collect` leaves
  it out.
- **Choosing.** Look through all of `index.json` first, then pick the night's best candidates that
  have a text: a new method, algorithm, model or tool (not company news, not a product
  announcement), measured with a number, with code or weights where possible. 12 to 16 cards on a
  strong night; on a thin night 5 is fine. Never pad with weak cards. Pick different ideas, not
  several takes on one. Upvotes, stars, Hacker News points and a newsletter mention are signals, not
  the decision.
- **Order.** Write the cards in order of importance. The first is the lead: the night's most
  striking result, with a chart if it can have one; its `headline` becomes the front page's H1 and
  its `what` the deck. The second is the front page's other story. With 11 cards or more, mark 3 or 4
  as `brief: true`: the ones told in the fewest words (a tool, a one-number result) go to IN BRIEF on
  the front page. At most 4 briefs; a brief has no chart.
- **A card.** `id` the candidate's; `area` one word in capitals (`AGENTS`, `TRAINING`, `VIDEO`,
  `REASONING`, `TOOL`); `signal` short ("344 HF upvotes", "1647 stars today", "arXiv, 16 Oct", "HN 929
  points", "in Import AI", "2651 HF likes"); `name` the method's own name; `headline` the story's
  newspaper headline: short (8 or 9 words at most), concrete, with a number where it can ("96 Robots
  Learn From Each Other", "A Playable World at 60 FPS on One Consumer GPU"); `what` one sentence, what
  it is; `how` one or two sentences, how it works, the parts the method names in bold; `when` one
  sentence, when it helps or whom; `number` the card's one big figure: `value` short ("+3.44 pts",
  "100×+", "2.7×"), `says` what it measures (which model, which benchmark, against what), `quote` the
  source's sentence that carries it, **word for word** (it does not print; the check reads it); `code`
  without `https://` (`github.com/owner/repo`); `source` the lab or the first author with "et al."
  and the arXiv number ("Yu et al. · arXiv 2610.20642"), "owner · GitHub trending" for a repository,
  "Google · Hugging Face" for a model, the site's name for a page Hacker News pointed at; `link` the
  address the QR code opens, with `https://`: the code repository when the code is open, else the
  candidate's `url` (for a paper, `https://arxiv.org/abs/<id>`). A blog or web card must have a
  `link`. For a model, `code` is the model page (`huggingface.co/<owner>/<name>`) and the numbers
  come from its model card.
- **Charts.** When the source has its own table that compares the method with others, shows it
  scaling (more robots, longer inputs, a bigger thinking budget) or an ablation, and the reader would
  get the result at a glance, give the card a `chart`; 4 to 9 charts a night is good. A chart is
  information, never decoration: no photos, logos or screenshots. The rules (the fields are in
  `edition/README.md`, Fresh Ink):
  - Copy the values from the table **as they are** (98.33, 92.50); a unit may change only by a power
    of ten (1550 ms for the source's "1.55 s"). `decimals` says how many decimals print.
  - The chart comes from the same setting as the card's `number` (which teacher, which benchmark).
    When you take part of a table, say so in the title or in `what` ("six of eleven models").
  - The kind: one value per item is `bars`; 2 or 3 settings per item is `groups` (the last series is
    the method itself and prints solid); a trend on an ordered axis is `line` (robots, length,
    thinking level; `log: true` for a wide range).
  - `title` says what is measured and its unit ("Phone packaging success, % of tries"); `what` (the
    "What it shows" line) gives the axes, the abbreviations and the result in plain words, and the
    caveats too (who measured it, an axis that does not start at zero, rivals' figures taken from
    another paper); `table` is the table and the authors the data comes from ("Table 11e, Yu et al.").
  - Keep labels short: a long label leaves no room for the bars, and the chart is refused. The page
    draws each chart at its own width and reports an error when labels overlap, run out of the box or
    touch a line.
- **Length.** With a chart, `what` + `how` at most 55 words, the chart's `what` at most 30, `when` at
  most 20. Without a chart, `what` + `how` at most 70 words. In a brief, `what` at most 15 words and
  `says` at most 12. When the pages do not fit, the error names the card or the page that overflows:
  shorten those cards, turn a card into a brief or drop a chart. The build before the push keeps a
  line free on the front page, and on every page once Fresh Ink reaches four, because the Linux build
  that prints can break a line differently.
- **The list.** `also` holds 4 or 5 more works: `title` the candidate's title as is (the page prints
  the part before the colon) and `text` one sentence.
- **Headline.** `headline` (of the `radar` part) ties the three strongest cards into one line; every
  number in it comes from the cards' sources. It becomes the H1 when the first card has no
  `headline`. Copy `scanned` from `index.json` as is; `date` is the issue's date.
- **Fresh Ink never costs an issue.** When a chart fails its checks and cannot be fixed, take out the
  chart; the card stays. When a card fails, take out the card (its work does not go into the list
  either). If fewer than 5 valid cards are left, delete the `radar` part and send the issue without
  it; say why in the summary.
- **The check.** `next_issue.py verify` (run by `commit_issue.sh`) also runs `scripts/radar.py
  check`: each id is one of the night's candidates and was never printed, every number on a card
  (headline included) is in its source, every value of a chart and every number in its words is in
  the source's text or tables, the quote stands there word for word and carries the callout number,
  the name, the code link and the QR `link` are the candidate's own, and the headline's and the
  list's numbers are in the sources too. To run it by hand: `python3 scripts/radar.py check <file>`.
- **Samples:** `edition/fixtures/fresh-ink.edition.json` (22 October 2026: 16 cards, 9 charts, 4
  briefs, four pages; a strong night looks like this) and `edition/fixtures/radar.edition.json` (17
  October 2026 in the older format: five cards, no headlines, briefs or charts; it still prints as
  Fresh Ink).
