# Notes

Every Markdown file in this folder is a note, and every note becomes one issue of your Coffee Edition. The nightly routine takes the first note that has not printed yet, writes it up as a two-page newspaper and sends it to your printer. Each note prints once.

This README is not a note, and neither is any file or folder whose name starts with `_` or `.`, so `_drafts/` and `_template.md` are safe places for unfinished work.

## A note

```markdown
---
title: Raven, the harness of harnesses
source: https://arxiv.org/abs/2609.33439
license: CC BY 4.0
---

# Raven

Your own summary of the paper: what it does, how, what the numbers say,
what you would use it for. The more of your own thinking is in the note,
the better the issue.

![the planning graph](raven-graph.png)
```

The frontmatter (the block between the two `---` lines) is optional. Every key is optional too:

| Key | What it does |
|---|---|
| `title` | What the note is about. Without it, the first `# ` heading, then the file name. |
| `order` | A number; lower prints first. |
| `print_on` | `YYYY-MM-DD`. The note waits until that morning and then goes before everything else. Good for a talk you want to read the morning before it. |
| `skip` | `true` leaves the note out. |
| `source` | Where the facts come from. The issue prints it at the foot of the front page. |
| `license` | The source's license, when it asks for credit (`CC BY 4.0`). The writer credits it. |

## Order

1. Notes whose `print_on` has come, earliest first.
2. Then by `order`, lowest first. Notes without `order` come after those with one.
3. Then by path in natural order: `2-intro.md` before `10-outro.md`.

`python3 scripts/notes.py` lists your notes in print order, with any problems it finds. `python3 scripts/next_issue.py plan` shows which note prints on which morning.

## Pictures

Put the picture file next to the note and show it with `![what it shows](figure.png)` or `![[figure.png]]`. The issue can print only these pictures, and only when:

- the file is committed (the cloud routine and GitHub Actions see committed files only);
- it is PNG, JPEG or WebP;
- it is at most 1.5 MB; about 2000 pixels wide is plenty;
- it is light: a dark slide prints as a block of toner on a laser printer, and the build refuses it.

Web links to pictures are not printed. Download the picture and commit it.

## What makes a good note

The writer turns your note into an article. It does not browse the web, so put in everything it needs: the key idea, how it works, the numbers that matter with where they come from, and your own view on when you would use it. The example `002-raven.md` shows the shape.
