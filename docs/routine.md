# The nightly writer: a Claude routine

Every night, a few hours before the print time, a Claude routine opens your repository in the cloud, picks the next note, writes the issue and pushes it. Your computer can be off. This page sets it up.

Routines are a Claude Code feature for Pro, Max, Team and Enterprise plans, in research preview at the time of writing. The official guide is [code.claude.com/docs/en/routines](https://code.claude.com/docs/en/routines); this page only covers what Coffee Edition needs.

## Before you start

- Your copy of the kit is on GitHub (private), with `notes/` holding at least one note.
- `printer.json` has your `timezone` and `edition_print_time`, and `"nightly": "dry-run"` for the first nights.
- Claude has access to your GitHub account (the routine form asks for it if not).

## Create the routine (web)

1. Open [claude.ai/code/routines](https://claude.ai/code/routines) and click **New routine**.
2. **Name:** `Coffee Edition`.
3. **Prompt:** paste the whole of [routine/nightly-prompt.md](../routine/nightly-prompt.md). It is short on purpose: the real steps live in `CLAUDE.md` in your repository, so you can improve them with a commit instead of editing the routine.
4. **Model:** pick the strongest model you have; the issue is the whole point.
5. **Repositories:** add your copy of the kit, and nothing else.
6. **Environment:** **Default** is fine. Its **Trusted** network allows GitHub, npm and PyPI, which is all the nightly task uses. It does not allow arbitrary websites, so the writer works from your note, not from the web.
7. **Trigger:** **Schedule**, **Daily**, at a time about three hours before your print time and a few minutes past the hour (for a 07:30 print, **04:15**). Times are entered in your local time zone. A run set exactly on the hour can start several minutes late.
8. **Connectors:** remove all of them. The nightly task needs none, and a routine can use every included connector without asking.
9. Click **Create**.

The same can be done from Claude Code's CLI with `/schedule` (also `/routines`): describe the routine and Claude asks for the rest. `/schedule list`, `/schedule update` and `/schedule run` manage it later.

### Why a few hours early

The routine writes, then `commit_issue.sh` builds the issue in full, pushes it and waits for GitHub Actions to queue it: about five to ten minutes on a good night. When a check refuses the issue, the writer fixes it and tries again. Three hours leave room for that, and for a run that starts late. An issue that would print more than 30 minutes after its time is refused before the push, and GitHub Actions drops anything an hour late, so a very late night prints nothing rather than printing at lunch.

### Pushing to main

Claude normally pushes its work to a branch named `claude/...`. The prompt tells it to commit only through `scripts/commit_issue.sh`, which pushes the issue to `main`, where the `prepare` workflow picks it up. If you protect `main` with a GitHub rule that your own access cannot bypass, that push fails; leave `main` open to your own pushes, or point the workflow at another branch.

## Try it: Run now

1. Open the routine and click **Run now**.
2. Watch the run: it is a normal Claude Code session. It should pick `notes/001-welcome.md`, write `inbox/<date>.edition.json`, run `commit_issue.sh` and finish with a summary like "issue 001, draft, 1180 words".
3. On GitHub, the **Actions** tab shows a green `prepare` run, `log/prints.md` shows the issue as `draft · not printed`, and the `archive` branch has its PDF. Open it: that is tomorrow's paper.

A green status in the routine's run list only means the session started and ended without an infrastructure error. It does not mean an issue was made. Read the run, or `log/prints.md`.

## Going live

After a night or two of good drafts, set `"nightly": "live"` in `printer.json` and push. From then on each issue goes to the queue, and the Pico prints it at the print time.

Dry-run nights do not use up your notes: the first live night still prints issue 001 from the first note.

## When it goes wrong

| What you see | Why | What to do |
|---|---|---|
| Summary says "already prepared" | That morning already has an issue (from an earlier run, or one waiting in `inbox/`) | Nothing. One issue a day. |
| Summary says "no unprinted note is ready" | Every note has printed, or the next one has a `print_on` date ahead | Add notes to `notes/`. |
| `commit_issue.sh` exit 1, "nightly off" | `printer.json` has `"nightly": "off"` | Set `dry-run` or `live`. |
| Exit 1 after several rounds | The writer could not make the issue pass the checks | Read the errors in the run; usually a too-long issue or an unsupported character (edition/STYLE.md section 9). |
| Exit 2 | GitHub Actions refused the layout | The writer fixes and retries by itself; if it gave up, the reason is in `log/prints.md`. |
| Exit 4, "no verdict" | Actions did not answer in about nine minutes | Check the **Actions** tab: Actions may be off for the repository, or queued behind other runs. |
| `403 host_not_allowed` in the run | The writer tried to reach a website the Trusted network does not allow | Nothing to fix; the note is the only source. |
| No runs at all | The routine is paused, your GitHub connection expired, or you hit your usage limit | Reconnect GitHub within 72 hours and the routine resumes by itself; after that it turns off and needs turning on again. |
| Runs at the wrong hour after a clock change | The form saves your local time as a fixed UTC schedule | Check the time after daylight saving starts or ends and adjust it. The print time itself follows `printer.json`'s `timezone`. |

## Changing it later

- **Print time:** `edition_print_time` in `printer.json`, then move the routine's time to keep about three hours of margin.
- **Voice:** `edition/STYLE.md`, section 0 describes the reader.
- **Steps:** the "Nightly task" section of `CLAUDE.md`.
- **Pause:** the switch at the top of the routine's page, or `"nightly": "off"`.
