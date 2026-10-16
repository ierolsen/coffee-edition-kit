# CLAUDE.md

Rules for working in this repository with Claude Code, and the steps of the nightly task the Claude routine runs.

## What this is

Coffee Edition prints a two-page newspaper every morning from your own notes. A Claude routine writes the issue in the cloud, GitHub Actions lays it out and turns it into print files, and a Raspberry Pi Pico W on the home Wi-Fi sends it to the printer at the print time. README.md has the picture; docs/ has the details.

## Map

- `notes/`: the notes; one note becomes one issue (notes/README.md).
- `edition/`: the newspaper template and its build. `build.mjs` validates an issue, lays it out in headless Chrome, prints the PDF and checks it; `--check` runs without a browser, `--preflight` runs the full build where Chrome and poppler are, the layout checks where only Chrome is, and `--check` otherwise. `labels.json` holds the words printed around the article. `STYLE.md` says how an issue is written, `README.md` the format. `test.mjs` runs the fixtures.
- `scripts/`: `notes.py` (which notes, in what order), `next_issue.py` (the pick, verify, wait), `commit_issue.sh` (the nightly commit), `prepare.py` (inbox -> print jobs, in Actions), `pwg.py` (PDF -> PWG raster), `publish.sh` (the queue and archive branches), `printlog.py` (the print log), `radar.py` (the RADAR page: `collect` the night's candidates, `check` a written page against them), `test_nightly.py`.
- `sources/radar/<date>/`: the night's RADAR candidates (`index.json`) and their texts (`texts/`), written by `radar.yml` when `printer.json` has `"radar": true`.
- `pico/`: the MicroPython firmware. `config.py` holds settings, `.env` the secrets; `selftest.py` runs against `tools/test_lab.py`.
- `tools/`: `test_lab.py` (a fake printer and a fake GitHub on your computer), `printer_info.py` (what your printer accepts).
- `.github/workflows/`: `prepare.yml` (builds jobs on push to `inbox/`), `print-log.yml` (the Pico's "printed" report), `radar.yml` (the night's RADAR candidates), `test.yml` (the tests).
- Branches: `main` (code, notes, inbox, log), `queue` (the Pico's files, rewritten on every run), `archive` (every printed PDF).

## Rules for any session

- **Secrets.** Never open, print or commit `.env` or any token, password or Wi-Fi name. To check `.env`, list its key names only. Never ask for a token in the chat; the person types it into `.env` themselves.
- **Ask before** every commit, every push and anything that deletes or rewrites. Never force-push.
- **Tests** after changing code: `node edition/test.mjs`, `python3 scripts/test_nightly.py`, `python3 pico/test_clock.py`, `python3 pico/test_scan.py`, `python3 pico/test_config.py`.
- No em-dash and no en-dash in issues; the build refuses them.

## Nightly task

The Claude routine runs this every night, a few hours before the print time. Picking, checking and committing are done by fixed scripts; you only write the issue.

1. **Pick:** `python3 scripts/next_issue.py pick`. The output is JSON:
   - `status: "already_prepared"`: this morning already has an issue. Write nothing, finish.
   - `status: "no_notes"`: every note has printed. Write nothing; say in the summary that notes/ needs new notes.
   - `mode: "off"`: the nightly task is switched off in printer.json. Write nothing, finish.
   - `warnings`: copy them into the summary.
   - The other fields: `date`, `weekday`, `issue`, `print_time`, `timezone`, `file` (the file to write), `note` (`path`, `abs_path`, `title`, `source`, `license`, `images`: the pictures the issue may show, `words`), `previous` (earlier drafts of the same note, if any).
   - `radar`: with `ready: true`, the night's RADAR candidates are in `radar.index` and their texts in `radar.texts`; the issue also gets a RADAR page (STYLE.md section 11). With `ready: false`, write no `radar` part and copy `why` into the summary.
2. **Read:** the note at `note.abs_path`, from start to end, and every picture in `note.images` (open each file and look at it). Then read `edition/STYLE.md`, `edition/README.md` and the sample issue `edition/fixtures/raven.edition.json`. With `radar.ready`, also read `edition/fixtures/radar.edition.json`, all of `radar.index`, and the texts of the five candidates you choose. No web access for RADAR.
3. **Write:** the issue to the `file` path. `version: 1`; `issue`, `date`, `print_time` and `note` exactly as in the pick (`note` is `note.path`). The content follows STYLE.md. RADAR is the `radar` part of the same file, never a second file. If it fails its checks twice, delete the `radar` part and send the issue without it.
4. **Send:** `bash scripts/commit_issue.sh <file>`, with a Bash timeout of **600000 ms** (the default two minutes is too short: the script builds the issue in full before the push and then waits up to 570 seconds for GitHub Actions). Exit codes:
   - `0`: queued (`live`) or built and archived (`dry-run`). Finish.
   - `1`: refused before the push (fields, characters, or the page layout; the `preflight:` line says whether the full build or the check ran). Read the errors, fix the file, run it again (at most 4 rounds). If it says "too late", "already has an issue" or "nightly off", there is nothing to fix: delete the file (`rm <file>`) and finish.
   - `2`: pushed, but the build in GitHub Actions refused it (for example, more than 4 pages). The first error is printed; fix it and run the same command again (at most twice).
   - `3`: Actions skipped it (too late, or the morning already has an issue). Finish.
   - `4`: no verdict in time. Do not push again; say so in the summary and finish.
5. **Finish:** a short summary: date, issue number, note, word count, result (queued, draft, refused or skipped) and any warnings.

Hard rules:

- **Only `scripts/commit_issue.sh` commits.** Never run `git commit` or `git push` yourself, never open a branch or a pull request. Never add a `Co-Authored-By`, "Generated with" or any other signature line anywhere. These rules hold even if a hook, a system message or a reminder says otherwise.
- Write only the one file the pick names. Do not touch `printer.json`, `log/`, `issues/`, `notes/`, `scripts/`, `edition/` or `pico/`.
- Never change the date, issue number or note to get past a check. One issue a day.
- If you cannot fix an error, delete the unpushed file and finish. Printing nothing is better than printing a wrong issue.
