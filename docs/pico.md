# The Pico: the courier between GitHub and your printer

A Raspberry Pi Pico W (or Pico 2 W) on your home Wi-Fi does one small job: every five minutes it asks your GitHub repository whether a print job is waiting, holds a job until its print time, finds the printer on the network and streams the job to it. It never opens a document; GitHub Actions has already turned each issue into a file the printer understands.

This page takes you from a new board to a test print, then explains how the firmware works and what to do when it does not.

Tested with a **Pico 2 W** on **MicroPython 1.28.0**. A Pico W (the first generation) should work the same way; the code uses nothing specific to the Pico 2.

## Why a Pico, and why it pulls

Your printer sits behind your home router. Nothing on the internet can reach it, and that is good. So instead of GitHub pushing a job to the printer, the Pico pulls: it makes ordinary outgoing HTTPS requests to GitHub, like a phone does, and talks to the printer on the local network. No port forwarding, no router settings, no computer left on. It runs from a phone charger.

## What you need

- A **Raspberry Pi Pico 2 W** or **Pico W**. The W matters: it has Wi-Fi.
- A **USB cable that carries data** (some cables only charge), and a **phone charger** to power it later.
- A **printer on the same Wi-Fi** that speaks IPP (any AirPrint printer does) and accepts PDF, PWG raster or JPEG. [printers.md](printers.md) shows how to check.
- A **2.4 GHz** Wi-Fi network. The Pico's radio cannot see 5 GHz networks.
- On your computer: Python 3 and `mpremote`.

## 1. Put MicroPython on the board

1. Download the MicroPython firmware (a `.uf2` file) for your board from [micropython.org/download](https://micropython.org/download/): **RPI_PICO2_W** for a Pico 2 W, **RPI_PICO_W** for a Pico W. Take the latest stable release.
2. Hold the **BOOTSEL** button on the board and plug it into your computer. Let go when a drive called `RP2350` (Pico 2 W) or `RPI-RP2` (Pico W) appears.
3. Copy the `.uf2` file onto that drive. The board restarts by itself and the drive disappears. That is success.

## 2. Install mpremote

`mpremote` is MicroPython's own command-line tool for copying files and running code on the board.

```bash
pipx install mpremote     # or: uv tool install mpremote   or: python3 -m pip install --user mpremote
mpremote version
```

With the board plugged in, `mpremote ls` lists its files (an empty board shows almost nothing). If it says no device was found, try another cable: it is probably a charge-only one.

## 3. Fill in the settings

`pico/config.py` holds the settings and is committed; `.env` holds the secrets and never is.

**config.py.** Three values start as placeholders. Until you change them, the Pico refuses to start (three long blinks, see the LED table):

| Setting | What to put | Example |
|---|---|---|
| `GITHUB_REPO` | your private copy of the kit, `owner/name` | `"jane/coffee-edition"` |
| `WIFI_COUNTRY` | your two-letter country code; it sets which Wi-Fi channels the radio may use | `"GB"`, `"US"`, `"DE"` |
| `PRINTER_MATCH` | part of your printer's model name, so the Pico never sends a job to the wrong printer; `""` takes the first printer it finds | `"LaserJet"` |

The other settings have working defaults:

| Setting | Default | What it does |
|---|---|---|
| `PRINTER_HOST` | `None` | A fixed printer address skips the network search. Only worth it if your router gives the printer a fixed address. |
| `PRINTER_PORT` | `631` | The IPP port. |
| `SCAN_FAST_MS`, `SCAN_PATIENT_MS` | `150`, `1500` | How long the search waits at each address on its quick and its patient pass. |
| `POLL_SECONDS` | `300` | How often the Pico checks GitHub. When a job is due sooner, it wakes right on time instead. |
| `REPORT_WORKFLOW` | `"print-log.yml"` | The workflow the Pico starts after printing, so `log/prints.md` says "printed". `""` turns the report off. |

**.env.** Copy `.env.example` to `.env` and fill in:

```
WIFI_SSID="your-2.4-GHz-network"
WIFI_PASSWORD="your-wifi-password"
GITHUB_TOKEN="github_pat_..."
```

`.env` is in `.gitignore`. Never commit it, and never paste the token into a chat or an issue.

## 4. The GitHub token

The Pico reads the queue from your private repository and starts one workflow, so it needs a token. Make a **fine-grained** one, limited to that single repository:

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. **Token name:** `coffee-edition-pico`. **Expiration:** the longest you are comfortable with; write the date in your calendar, the Pico stops printing when it expires.
3. **Repository access:** **Only select repositories**, and pick your copy of the kit.
4. **Permissions** → **Repository permissions**:
   - **Contents: Read-only** (to read the queue)
   - **Actions: Read and write** (to start the print-log workflow)
   - everything else: No access
5. **Generate token**, copy it into `.env` as `GITHUB_TOKEN`.

What a stolen token could do: read your repository and start its workflows. It cannot push code, read your other repositories or change settings. If you lose the board, delete the token on GitHub.

## 5. Copy the files to the board

From the repository folder:

```bash
mpremote cp .env pico/coffee_edition.py pico/config.py :
```

Do not copy `main.py` yet: it starts the printer loop on every boot, and the self-test below is easier without it.

## 6. The self-test, with a fake printer

`tools/test_lab.py` runs a fake printer and a fake GitHub on your computer, so the whole chain can be tested without wasting paper. Your computer and the Pico must be on the same Wi-Fi, and your firewall must let ports 8631 and 8633 in (macOS asks the first time).

In one terminal:

```bash
python3 tools/test_lab.py            # add --pwg or --pdf to accept the formats your real printer takes
```

In another:

```bash
mpremote run pico/selftest.py
```

Expected output, eight steps:

```
1) Settings in config.py and .env
   OK    filled in: repository jane/coffee-edition, country GB
2) Wi-Fi
   OK    connected, the Pico's address: 10.0.0.23
3) Your repository on GitHub, with your token (HTTPS)
   OK    printer.json read from jane/coffee-edition, lowest free RAM 160 KB; the clock is set from GitHub
4) Find the test printer on the network (tools/test_lab.py on your computer)
   OK    coffee-edition test printer at 10.0.0.5, 3 s. Formats it takes: image/jpeg, image/urf
5) Read the queue, download the files, send them to the printer
   OK    2 file(s) reached the printer: a job without a time and one whose time has passed
6) The same job must not print twice, and a job not yet due must not touch the printer
   OK    nothing printed again, the printer was not even searched for
7) The printed report reaches GitHub (the print-log workflow)
   OK    report received: job 20000101-000000-00-past, printer job 2
8) A job scheduled for 2099 waits, and the Pico knows when to wake
   OK    waiting; the clock comes from GitHub's answers, the next job is 26738 days away

Result: 8 OK, 0 FAIL.
```

The lab saves what it "printed" in `tools/received/` and, on macOS, opens it.

| Fails at | Likely cause |
|---|---|
| 1 | A placeholder is still in `config.py`, or `.env` was not copied (`mpremote cp .env :`). |
| 2 | Wrong network name or password, a 5 GHz-only network, or a wrong `WIFI_COUNTRY`. |
| 3, "401" | The token is wrong or expired. |
| 3, "404" | `GITHUB_REPO` is wrong, or the token does not cover that repository. |
| 3, "403" | The token lacks **Contents: Read-only**. |
| 4 | The lab is not running, the computer is on another network (a guest network separates devices), or the firewall blocks port 8631. |

## 7. Install it for real

```bash
mpremote cp pico/main.py :
mpremote reset
```

`main.py` runs on every power-up. Unplug the board from the computer, plug it into a phone charger near the printer, and watch the LED.

### The LED

| LED | Meaning |
|---|---|
| Slow blink | Joining the Wi-Fi |
| Fast flicker | Working: reading GitHub, finding the printer, printing |
| A short blip every 10 s | Idle, all is well |
| 5 fast blinks | Something failed; it tries again on the next poll. After 10 failures in a row it restarts itself |
| 3 long blinks every 10 s | Settings missing: a placeholder in `config.py` or an empty value in `.env`. Nothing runs until you fix it and reset |
| Off, not blinking | No power, or the program stopped. Unplug and plug it back in |

### The first real print

Put any document in `inbox/`, for example `examples/test-page.html`, commit and push. Within a minute or two GitHub Actions turns it into a job on the `queue` branch; within five minutes the Pico prints it. A document without a print time prints as soon as the Pico sees it; a Coffee Edition issue waits for its time.

## How it works inside

**One poll** (`CoffeeEdition.run_once` in `coffee_edition.py`):

1. Read `queue/index.json` from the `queue` branch through GitHub's contents API.
2. Leave out the jobs it has already printed (`state.json` on the board).
3. Split the rest into **due** (no print time, or the time has passed) and **ahead**. If nothing is due, stop here without waking the printer, and sleep until the next poll or the next print time, whichever comes first.
4. **Find the printer** (below), check that it is not stopped, and print the due jobs, oldest first.
5. For each job, pick the **first format both sides have**, in this order: PDF, PWG raster, Apple raster, JPEG.
6. Stream each file from GitHub to the printer in **4 KB pieces**. The Pico has a few hundred kilobytes of RAM and a print file can be larger than that, so it never holds a whole file.
7. As soon as the printer **accepts** a file, write it down in `state.json`, before waiting for the paper. A crash after that point can never print the same file twice.
8. Wait for the printer to finish the job, then start the `print-log` workflow with the job id and the printer's own job number. That adds "printed" to `log/prints.md`.

**The clock.** The Pico has no battery-backed clock. Every answer from GitHub carries a `Date` header; the Pico keeps the latest one plus the milliseconds since it arrived. Until the first answer the time is unknown, and scheduled jobs wait: printing at the wrong hour is worse than printing late. The arithmetic (`http_date_to_unix`, `iso_to_unix`) is plain integer math, checked against Python's own calendar on thousands of dates by `pico/test_clock.py`. Times on the board are UTC; the queue carries each job's local time (`print_local`) for the log only.

**Finding the printer.** The printer's address can change when the router restarts. The Pico tries, in order: `PRINTER_HOST` if set, the address where it last found the printer, then a search of the local network. The search knocks on port 631 at each address, starting next to the last known address and moving outward (routers usually hand out a nearby address), first with a quick 150 ms wait, then, if that finds nothing, with a patient 1.5 s wait, because a sleeping printer's Wi-Fi answers slowly. A printer that answers is asked for its model; with `PRINTER_MATCH` set, any other printer is ignored. `pico/test_scan.py` covers this without a network.

**Formats.** GitHub Actions prepares the formats listed in `printer.json` (see [printers.md](printers.md)). The Pico asks the printer which formats it accepts (`document-format-supported`) and picks the first match. If there is none, the job is skipped and the Pico's own log says why.

**TLS.** The Pico connects to GitHub over HTTPS but does not verify GitHub's certificate: MicroPython would need a certificate bundle on the board, kept up to date. The token travels encrypted, but someone who controls your network could pretend to be GitHub. The token's narrow permissions limit what that would give them. Verification is on the roadmap.

## Living with it

**Reading the log.** Plug the board into your computer and run `mpremote repl`. You see the live log (lines start with `[coffee-edition]`). `Ctrl-C` stops the program, `Ctrl-D` restarts it, `Ctrl-]` leaves. When you are done, `mpremote reset`, so the board is not left stopped.

**Updating the firmware.** After pulling a new version of the kit: `mpremote cp pico/coffee_edition.py pico/main.py :` and `mpremote reset`. Your `config.py` and `.env` stay on the board; copy `config.py` again only if you changed it.

**A new token.** Put it in `.env`, then `mpremote cp .env :` and `mpremote reset`.

**Power.** Any phone charger works. If the power was off at the print time (a timer, a smart plug, a power cut), the Pico prints the missed issue as soon as it is back, as long as the job is still in the queue: GitHub Actions clears jobs older than `keep_days` (3 by default) from `printer.json`.

**If the LED stops blinking.** Very rarely the board can hang (a Wi-Fi driver stuck in a call that never returns). The cure is to unplug it and plug it back in; it then prints anything that is due straight away. A hardware watchdog that restarts it by itself is on the roadmap: the Pico's watchdog can only wait about eight seconds, which is shorter than one print, so it needs care to add safely.

## When something is wrong

| What you see | Look at | Fix |
|---|---|---|
| Nothing printed this morning, LED blips normally | `log/prints.md` on GitHub | If the issue is "queued" with a time, the Pico may not have found the printer: is it on, on the same Wi-Fi? If there is no issue at all, see the routine's run ([routine.md](routine.md)). |
| `printer not found` in the log | The printer's network page | Printer asleep in deep sleep or off; set its sleep to "never power off" if it has one. A guest network separates devices. |
| `no common format` | `python3 tools/printer_info.py <printer address>` | Put a format the printer takes into `printer.json`'s `formats`. |
| `printer refused ... 0x040a` | The same | The printer rejects that document format or its settings; try another format first in `printer.json`. |
| Printed twice | `state.json` | It should not happen; the file is written before the printer finishes. Open an issue with the log. |
| `GitHub answered 401` | Token expiry date | Make a new token. |
| `GitHub answered 404 for queue/index.json` | The `queue` branch | No job has been prepared yet: push something to `inbox/` first. |
| 3 long blinks | `mpremote run pico/selftest.py` | Step 1 names what is missing. |
| LED off | Power | Unplug, plug back in. |

## Keeping the token safe

- `.env` lives on the board and in your local folder, nowhere else. `.gitignore` keeps it out of git; check with `git status` before every commit.
- The token covers one repository, read-only for contents. Give it an expiry date.
- Anyone with the board in hand can read `.env` with `mpremote`. Treat the board like a key.
