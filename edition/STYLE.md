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
