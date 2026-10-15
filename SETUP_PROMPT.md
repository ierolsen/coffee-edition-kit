# Set it up with Claude Code

Open Claude Code in your copy of the repository (`cd coffee-edition && claude`) and paste everything between the two lines below. Claude walks you through the setup one step at a time, runs the checks, and stops before anything you should do yourself.

---

Help me set up Coffee Edition in this repository, step by step. Read README.md, CLAUDE.md, docs/pico.md, docs/printers.md and docs/routine.md first.

Rules for this whole session:
- Never open, print, copy or commit `.env`, a token, a Wi-Fi password or the Wi-Fi name. To check `.env`, show only its key names and whether each value is empty. Never ask me to paste a token or a password into this chat: I type secrets into `.env` myself.
- Ask me before every commit, every push, and anything that deletes or overwrites a file. Show me the diff first. Never force-push.
- Explain each step in a sentence or two before doing it, and wait for me when a step needs my hands (a cable, a button, a web page).
- If something fails, show me the exact error and what you think it means before trying a fix.

Steps:

1. **About me.** Ask me, in one message: my country (for the Wi-Fi channels), my time zone, the time I want the paper printed, my printer's model, and whether I already have a Pico W or Pico 2 W.
2. **Tools.** Check what is installed: Python 3.9+, Node 22+, Chrome or Chromium, poppler (`pdfinfo`, `pdftotext`, `pdftoppm`), git, and `mpremote`. Tell me how to install anything missing on my system, and wait.
3. **Tests.** Run `node edition/test.mjs`, `python3 scripts/test_nightly.py` and the three `pico/test_*.py`. Then build the sample issue with `node edition/build.mjs edition/fixtures/raven.edition.json --pdf edition/out/raven.pdf --png edition/out` and show me the page images.
4. **Settings.** Set `timezone` and `edition_print_time` in `printer.json` from my answers, and `"nightly": "dry-run"`. Show me the diff.
5. **Printer.** Help me find my printer's address (docs/printers.md), then run `python3 tools/printer_info.py <address>` and set `formats` and `pwg_dpi` in `printer.json`, and `PRINTER_MATCH`, `WIFI_COUNTRY` and `GITHUB_REPO` in `pico/config.py`. Show me the diff.
6. **Commit.** Ask me, then commit these settings and push, so GitHub Actions can use them.
7. **Token.** Walk me through making the fine-grained token on GitHub (docs/pico.md, "The GitHub token"): this repository only, Contents read-only, Actions read and write. I click through it myself.
8. **.env.** Copy `.env.example` to `.env` for me, then tell me to open it in my editor and fill in the three values. When I say done, check only that the keys are there and not empty.
9. **MicroPython.** Guide me through putting MicroPython on the Pico (docs/pico.md, step 1), then check that `mpremote ls` sees it.
10. **Self-test.** Copy `.env`, `pico/coffee_edition.py` and `pico/config.py` to the board. Start `python3 tools/test_lab.py` (with `--pwg` or `--pdf` if my printer takes that) in the background, then run `mpremote run pico/selftest.py` and go through the result with me. All 8 steps should say OK.
11. **First real print.** Copy `pico/main.py` to the board and reset it. Ask me, then put `examples/test-page.html` into `inbox/`, commit and push. Watch the `prepare` run with `gh run watch` if `gh` is installed, and tell me when the queue has the job. The page should come out within five minutes.
12. **The nightly writer.** Walk me through creating the Claude routine (docs/routine.md): the prompt from `routine/nightly-prompt.md`, this repository, the Default environment, a daily time about three hours before my print time and a few minutes past the hour, no connectors. Then **Run now**, and after it finishes, check `log/prints.md` and the `archive` branch with me.
13. **Live.** After I have seen a good draft, ask me, then set `"nightly": "live"` in `printer.json`, commit and push. Remind me to add my own notes to `notes/` (notes/README.md).

At the end, give me a short list of what is set up, what my print time and routine time are, and the date my token expires.

---

If you prefer to do it by hand, the same steps are in [README.md](README.md#set-it-up).
