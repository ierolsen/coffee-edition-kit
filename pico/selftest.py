# coffee-edition self test for the Pico. Needs no real printer.
#
# On your computer, in the repository folder:
#   1) python3 tools/test_lab.py        (a fake printer and a fake GitHub, on your computer)
#   2) mpremote cp .env pico/coffee_edition.py pico/config.py : + run pico/selftest.py
#
# Steps: settings, Wi-Fi, your repository and token on the real GitHub, finding the test
# printer, printing a queued job, never printing twice, the "printed" report, and holding a
# job scheduled for later. It prints no secret.

import gc
import json
import os
import time
import config
import coffee_edition as ce

passed = [0]
failed = [0]


def step(n, title):
    print("\n%d) %s" % (n, title))


def ok(msg):
    passed[0] += 1
    print("   OK    " + msg)


def fail(msg):
    failed[0] += 1
    print("   FAIL  " + msg)


def free_kb():
    gc.collect()
    return gc.mem_free() // 1024


print("coffee-edition self test, free RAM: %d KB" % free_kb())

step(1, "Settings in config.py and .env")
problems = ce.config_problems(config)
if problems:
    for p in problems:
        fail(p)
    print("\nFill these in, copy the files again and rerun the test.")
    raise SystemExit
ok("filled in: repository %s, country %s" % (config.GITHUB_REPO, config.WIFI_COUNTRY))

step(2, "Wi-Fi")
try:
    ip = ce.wifi_connect(config)
    ok("connected, the Pico's address: %s" % ip)
except Exception as e:
    fail("Wi-Fi: %r" % e)
    raise SystemExit

step(3, "Your repository on GitHub, with your token (HTTPS)")
try:
    gc.collect()
    low = gc.mem_free()
    gh = ce.GitHub(config)
    url = "%s/repos/%s/contents/printer.json?ref=main" % (gh.base, gh.repo)
    r = ce.http_request("GET", url, gh.headers, ca=gh.ca, timeout=30)
    ce.note_date(r.headers)
    body = r.read_all(16384)
    low = min(low, gc.mem_free())
    r.close()
    if r.status == 200:
        ok("printer.json read from %s, lowest free RAM %d KB; the clock is set from GitHub" % (config.GITHUB_REPO, low // 1024))
    elif r.status == 401:
        fail("GitHub says the token is wrong or expired (401): make a new one, put it in .env, copy .env again")
    elif r.status == 404:
        fail("GitHub cannot see %s (404): check GITHUB_REPO, and that the token covers this repository" % config.GITHUB_REPO)
    elif r.status == 403:
        fail("GitHub refused (403): the token needs Contents read-only on this repository")
    else:
        fail("GitHub answered %d: %s" % (r.status, body[:120]))
except Exception as e:
    fail("HTTPS: %r" % e)


class Lab:
    GITHUB_REPO = "lab/coffee-edition"
    GITHUB_BRANCH = "main"
    GITHUB_TOKEN = "lab-token"
    PRINTER_MATCH = "coffee-edition test printer"
    PRINTER_PORT = 8631
    PRINTER_HOST = getattr(config, "LAB_HOST", None)
    SCAN_SUBNET = getattr(config, "SCAN_SUBNET", None)
    STATE_FILE = "state_test.json"
    API_BASE = "http://127.0.0.1:8633"  # replaced once the lab is found
    REPORT_WORKFLOW = "print-log.yml"
    REPORT_REF = "main"


lab = Lab()
try:
    os.remove(lab.STATE_FILE)
except OSError:
    pass

step(4, "Find the test printer on the network (tools/test_lab.py on your computer)")
t0 = time.time()
job = ce.CoffeeEdition(lab)
job.own_ip = ip
printer = job.find_printer()
if not printer:
    fail("not found. Is the lab running, is the computer on the same Wi-Fi, does its firewall let port 8631 in?")
    raise SystemExit
ok("%s at %s, %d s. Formats it takes: %s"
   % (printer.model, printer.host, time.time() - t0, ", ".join(printer.formats)))

step(5, "Read the queue, download the files, send them to the printer")
lab.API_BASE = "http://%s:8633" % printer.host
job.gh = ce.GitHub(lab)
try:
    sent = job.run_once()
    if sent >= 2 and "20000101-000000-00-past" in job.state["done"]:
        ok("%d file(s) reached the printer: a job without a time and one whose time has passed (see the page the lab opened)" % sent)
    else:
        fail("%d file(s) sent; was the past job printed: %s"
             % (sent, "20000101-000000-00-past" in job.state["done"]))
except Exception as e:
    fail("printing: %r" % e)

step(6, "The same job must not print twice, and a job not yet due must not touch the printer")
probes = [0]
_find = job.find_printer


def _counting_find():
    probes[0] += 1
    return _find()


job.find_printer = _counting_find
try:
    again = job.run_once()
    if again == 0 and probes[0] == 0:
        ok("nothing printed again, the printer was not even searched for")
    else:
        fail("%d file(s) sent again, the printer was searched %d time(s)" % (again, probes[0]))
except Exception as e:
    fail("%r" % e)

step(7, "The printed report reaches GitHub (the print-log workflow)")
try:
    r = ce.http_request("GET", lab.API_BASE + "/lab/dispatches", timeout=10)
    reports = json.loads(r.read_all(8192))
    r.close()
    done = [d for d in reports if d.get("workflow") == "print-log.yml" and d["inputs"].get("state") == "printed"]
    if done and done[-1]["inputs"].get("job") in job.state["done"] and done[-1].get("ref") == "main":
        ok("report received: job %s, printer job %s" % (done[-1]["inputs"]["job"], done[-1]["inputs"].get("printer_job")))
    else:
        fail("no report, or an incomplete one: %r" % reports[-1:])
except Exception as e:
    fail("report check: %r" % e)

step(8, "A job scheduled for 2099 waits, and the Pico knows when to wake")
if "20991231-000000-00-future" not in job.state["done"] and job.wait_s and job.wait_s > 86400 and ce.now_unix():
    ok("waiting; the clock comes from GitHub's answers, the next job is %d days away" % (job.wait_s // 86400))
else:
    fail("printed, or the wait is unknown: wait_s=%r, clock=%r" % (job.wait_s, ce.now_unix()))

print("\nResult: %d OK, %d FAIL. Free RAM: %d KB" % (passed[0], failed[0], free_kb()))
