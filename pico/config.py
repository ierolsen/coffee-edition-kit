# coffee-edition settings for the Pico. This file holds no secrets and is committed to git.
# Secrets (Wi-Fi name and password, GitHub token) live in .env, which is copied
# to the Pico next to this file and never committed. See .env.example and docs/pico.md.
#
# Fill in the three values marked FILL IN. Until they are set, the Pico does nothing and
# its LED gives three long blinks every 10 seconds; `mpremote run pico/selftest.py` says
# what is missing.


def _load_env(path=".env"):
    """Read KEY=value lines from .env (MicroPython has no os.environ or dotenv)."""
    try:
        f = open(path)
    except OSError:
        return {}  # main.py and selftest.py say what is missing (config_problems)
    env = {}
    with f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            env[key.strip()] = value
    return env


_env = _load_env()

# --- Wi-Fi (the Pico only sees 2.4 GHz networks) ---
WIFI_SSID = _env.get("WIFI_SSID", "")
WIFI_PASSWORD = _env.get("WIFI_PASSWORD", "")
WIFI_COUNTRY = "XX"   # FILL IN: your two-letter country code ("GB", "US", "DE"); sets the allowed Wi-Fi channels

# --- GitHub queue ---
GITHUB_REPO = "OWNER/REPO"   # FILL IN: your private copy of the kit, like "your-name/coffee-edition"
GITHUB_BRANCH = "queue"   # the print files live on the queue branch, rewritten by Actions
GITHUB_TOKEN = _env.get("GITHUB_TOKEN", "")   # fine-grained token: this repo only, Contents read-only, Actions read and write
REPORT_WORKFLOW = "print-log.yml"   # after printing, start this workflow on main so log/prints.md says so; "" = off

# --- Printer ---
PRINTER_MATCH = ""        # part of the printer's model name, like "LaserJet"; "" = the first printer found
PRINTER_HOST = None       # optional fixed address of the printer, like "10.0.0.50"; None = search the network
PRINTER_PORT = 631
SCAN_FAST_MS = 150        # network search: first pass, wait per address
SCAN_PATIENT_MS = 1500    # second pass when the first finds nothing (a sleeping printer answers slowly)

# --- Timing ---
POLL_SECONDS = 300        # how often to check for new jobs
