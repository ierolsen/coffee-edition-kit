---
title: Welcome to your Coffee Edition
---

# Welcome to your Coffee Edition

This is the first note in your `notes/` folder, so it becomes your first issue. Write it up as a short, friendly front page that tells the reader how their new morning paper works. There is no paper or experiment behind it, so leave the results page out: no `results` part, only the front page and the takeaway.

## What happened overnight

While the reader slept, a Claude routine woke up in the cloud a few hours before the print time. It asked `scripts/next_issue.py` which note comes next, read that note, wrote the issue as a small JSON file and pushed it to the reader's private GitHub repository. GitHub Actions laid the issue out in a headless Chrome with the fonts that ship in the repository, checked every page and every character, turned the pages into a format the printer accepts, and put the job on a branch called `queue`. A Raspberry Pi Pico W on the home Wi-Fi checks that branch every five minutes. It held the job until the print time and then sent it straight to the printer. No computer at home had to be on.

## How to feed it

- Every Markdown file in `notes/` is a note. One note becomes one issue, in order: `print_on` dates first, then `order` numbers, then file names in natural order (`2-...` before `10-...`).
- Put a picture next to a note and show it with `![what it shows](figure.png)`; the issue may print it. Commit the picture, keep it under 1.5 MB.
- Give the note a `source:` line when it summarises someone else's work; the issue prints it at the foot of the page.
- `skip: true` leaves a note out; a file name starting with `_` does the same for drafts.
- When the folder runs dry, the routine prints nothing and says so. Add notes whenever you like.

## How to change it

Everything a reader would want to change lives in `printer.json`: the time zone (`timezone`, for example `Europe/London`), the print time (`edition_print_time`), and whether the nightly run is off, a dry run that only archives a PDF, or live. The words around the article, like the nameplate and the weekday names, live in `edition/labels.json`, so the paper can speak another language. How the issue is written lives in `edition/STYLE.md`.

## Why paper

A printed page is finished. It does not refresh, it has no feed under it, and it is still on the table when the coffee is ready. The point of the paper is one idea a day, read slowly, with a pen nearby.

## The takeaway for this issue

Tell the reader that the paper writes itself from their own notes: whatever they put in `notes/` tonight can be on the table tomorrow morning.
