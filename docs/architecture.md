# Architecture

Four pieces, each doing one thing, joined by files in one git repository.

```
notes/  ->  Claude routine  ->  inbox/<date>.edition.json  ->  GitHub Actions  ->  queue branch  ->  Pico  ->  printer
 (you)      (cloud, nightly)        (main branch)               (lay out, check,     (print files)     (home Wi-Fi)
                                                                 convert, log)
```

1. **The writer** is a Claude routine. At night it asks `scripts/next_issue.py pick` for the next note, writes the issue as JSON, and hands it to `scripts/commit_issue.sh`, which checks it, builds it in full, commits it to `inbox/` on `main` and waits for the verdict.
2. **The press** is GitHub Actions. `prepare.yml` runs on every push to `inbox/`: `scripts/prepare.py` lays each issue out in headless Chrome (`edition/build.mjs`), checks the PDF, converts it to the formats the printer takes, and `scripts/publish.sh` publishes the result.
3. **The courier** is the Pico. It reads the queue, holds each job until its print time and streams it to the printer over IPP, then reports back through `print-log.yml`.
4. **The record** is `log/prints.jsonl` on `main`, rendered as `log/prints.md`.
5. **RADAR** (optional, `"radar": true`): `radar.yml` collects the night's candidates before the writer runs (`scripts/radar.py collect`, into `sources/radar/<date>/`), the writer adds a `radar` part to the issue, and `scripts/radar.py check` ties every card back to its candidate.

## Branches

| Branch | Holds | Written by |
|---|---|---|
| `main` | code, notes, `inbox/`, `issues/` (every nightly issue, by date), `log/` | you, the routine (`commit_issue.sh`), the workflows (`github-actions[bot]`) |
| `queue` | `queue/index.json` and the print files of the current jobs | `publish.sh`, rewritten as a single commit on every run, so old print files never pile up in history |
| `archive` | every built PDF, `archive/YYYY/MM/<job>.pdf` | `publish.sh`, only ever added to |

## The queue

`queue/index.json` on the `queue` branch:

```json
{
  "version": 1,
  "jobs": [
    {
      "id": "20261017-041533-00-2026-10-17",
      "name": "2026-10-17.edition.json",
      "title": "One agent that plans the work of all the others",
      "pages": 2,
      "created": "2026-10-17T04:15:33+00:00",
      "print_at": "2026-10-17T07:30:00+00:00",
      "print_local": "17 Oct 2026 07:30 Europe/London",
      "formats": {
        "image/pwg-raster": [{ "path": "queue/20261017-041533-00-2026-10-17/doc.pwg", "size": 412345 }]
      }
    }
  ]
}
```

`print_at` is UTC; the Pico compares it with the time in GitHub's `Date` header. A job without `print_at` prints as soon as the Pico sees it. Jobs older than `keep_days` are removed on the next run, including the daily scheduled one.

## The print log

`log/prints.jsonl`, one JSON object per line, only ever appended:

| Event | Added by | When |
|---|---|---|
| `queued` | prepare | a job entered the queue (title, topic, pages, `print_at`, and for nightly issues `note`, `issue`, `date`; for a RADAR page the ids of its cards, `radar`, and of its list, `radar_also`, so a work never comes back) |
| `drafted` | prepare | a nightly issue was built and archived but not queued (`nightly` is `dry-run`) |
| `rejected` | prepare | the build refused an issue; the first error is kept, the file stays in `inbox/` |
| `skipped` | prepare | a nightly issue arrived too late, or its date already had an issue; the file is removed |
| `printed`, `failed` | print-log | the Pico's report, with the printer's own job number |

Events about an inbox file carry its git blob id, so `next_issue.py wait` can find the verdict on exactly the version it pushed.

## Guards

A paper must never print at a wrong hour, twice in a morning, or broken. Each guard sits where it can be enforced:

| Guard | Where |
|---|---|
| The issue is exactly the pick for its date: note, number, print time, file name, only the note's pictures | `next_issue.py verify`, before the push |
| Fields, blocks, characters; with Chrome, the pages too, and the PDF where poppler is installed | `build.mjs --preflight`, before the push |
| RADAR: every card is one of the night's candidates and never printed before; every number and quote stands in its source | `radar.py check` through `next_issue.py verify`, before the push |
| Nothing that looks like a token or a key | `commit_issue.sh`, before the push |
| The commit carries no extra lines, and the expected author | `commit_issue.sh` |
| The real layout and the PDF itself: page count, every character on every page | `build.mjs` in `prepare`, after the push |
| Not more than an hour late; one issue per date | `prepare.py` |
| Printed only in `live` mode | `prepare.py` |
| Never printed twice | the Pico's `state.json`, written as soon as the printer accepts a file |
| Never printed before its time, never when the time is unknown | the Pico's clock from GitHub's `Date` header |

## Exit codes of commit_issue.sh

| Code | Meaning | The writer's next step |
|---|---|---|
| 0 | queued (`live`) or drafted (`dry-run`) | finish |
| 1 | refused before the push | fix and retry, or delete the file when it is too late or the date is taken |
| 2 | pushed, refused by the build in Actions | fix and retry |
| 3 | pushed, skipped by Actions (late, or the date is taken) | finish |
| 4 | no verdict in time | finish, report |

## Time

- The routine runs at a fixed time you choose, a few hours before the print time.
- `printer.json`'s `timezone` and `edition_print_time` decide the print moment; `zoneinfo` handles daylight saving time.
- The issue's date is the next morning whose print time is still ahead.
- `commit_issue.sh` must fit in one cloud Bash call of ten minutes: build, push and wait share a budget of 570 seconds (`WAIT_SECONDS`).
- The Pico works in UTC only; `print_local` is for its log.

## Security model

- **Your repository is private.** It holds your notes and your print log. Make your copy from the template as private.
- **The Pico's token** reads one repository and starts its workflows, nothing more; it lives in `.env`, never in git.
- **The routine** pushes through your own GitHub connection, and only `commit_issue.sh` commits. It can reach GitHub and package registries, not the open web (the Default environment's Trusted network).
- **The workflows** write with the repository's own `GITHUB_TOKEN` (`permissions: contents: write`) as `github-actions[bot]`.
- **The public template** skips both printing workflows (`if: github.repository != ...`), so it never builds a queue.
- **TLS:** the Pico encrypts its connection to GitHub but does not verify GitHub's certificate yet (see the roadmap).

## Roadmap

- Letter paper (today A4 only: `edition.css`, `prepare.py`, `pwg.py`).
- Apple raster (URF) output, for printers that take nothing else.
- Certificate verification on the Pico.
- A supervised hardware watchdog on the Pico.
- More block types and a second template.
