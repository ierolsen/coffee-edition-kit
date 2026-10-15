"""Checks the Pico's clock arithmetic against Python's own calendar. Runs in CPython:

    python3 pico/test_clock.py

The Pico turns GitHub's Date header and the queue's print_at into Unix seconds with plain
arithmetic (no RTC, no port-dependent epoch); a slip here would print a paper at the wrong
hour, so every conversion is compared with calendar.timegm over fixed edge dates and a few
thousand random ones.
"""
import calendar
import datetime
import email.utils
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coffee_edition as ce  # noqa: E402

UTC = datetime.timezone.utc
EDGES = [(1970, 1, 1, 0, 0, 0), (2000, 1, 1, 0, 0, 0), (2000, 2, 29, 12, 0, 0), (2024, 2, 29, 23, 59, 59),
         (2026, 10, 3, 18, 23, 9), (2026, 12, 31, 23, 59, 59), (2027, 1, 1, 0, 0, 0), (2028, 2, 28, 3, 45, 0),
         (2028, 2, 29, 3, 45, 0), (2028, 3, 1, 3, 45, 0), (2099, 12, 31, 23, 59, 59), (2100, 2, 28, 0, 0, 0),
         (2100, 3, 1, 0, 0, 0)]


def check(parts):
    dt = datetime.datetime(*parts, tzinfo=UTC)
    want = calendar.timegm(dt.timetuple())
    http = email.utils.format_datetime(dt, usegmt=True)          # 'Sat, 03 Oct 2026 18:23:09 GMT'
    iso = dt.isoformat()                                         # '2026-10-03T18:23:09+00:00'
    got = (ce.http_date_to_unix(http), ce.iso_to_unix(iso), ce.iso_to_unix(iso.replace("+00:00", "Z")))
    assert got == (want, want, want), (parts, http, iso, got, want)


def main():
    for parts in EDGES:
        check(parts)
    rng = random.Random(2026)
    for _ in range(5000):
        dt = datetime.datetime(1970, 1, 1, tzinfo=UTC) + datetime.timedelta(seconds=rng.randrange(0, 7258118400))
        check((dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second))
    for bad in ("2026-10-04T06:45:00+03:00", "2026-10-04T06:45:00", "garbage"):
        try:
            ce.iso_to_unix(bad)
        except (ValueError, IndexError):
            continue
        raise AssertionError("accepted a non-UTC or broken time: %r" % bad)
    at = calendar.timegm((2026, 10, 4, 3, 45, 0))
    assert ce.utc_hhmm(at) == "03:45", ce.utc_hhmm(at)
    assert ce.utc_hhmm(calendar.timegm((2026, 10, 3, 23, 59, 0))) == "23:59"
    print("clock ok: %d edge dates, 5000 random dates, non-UTC refused, log times in UTC" % len(EDGES))
    check_schedule()


def check_schedule():
    """Which jobs print now: none scheduled, past and future print_at, and an unknown clock."""
    ce.time.ticks_ms = lambda: 0                      # CPython has no ticks; freeze them
    ce.time.ticks_diff = lambda a, b: a - b
    ce.log = lambda *a: None
    edition = ce.CoffeeEdition.__new__(ce.CoffeeEdition)
    jobs = [{"id": "plain"}, {"id": "past", "print_at": "2000-01-01T00:00:00+00:00"},
            {"id": "soon", "print_at": "2026-10-04T03:45:00+00:00", "print_local": "4 Oct 2026 06:45 Europe/Helsinki"},
            {"id": "later", "print_at": "2099-12-31T00:00:00Z"}]
    ce._clock[:] = [None, 0]
    due, nxt = edition._split_due(jobs)
    assert [j["id"] for j in due] == ["plain"] and nxt is None, ("unknown clock must hold scheduled jobs", due, nxt)
    ce._clock[:] = [calendar.timegm((2026, 10, 4, 3, 40, 0)), 0]   # 03:40 UTC
    due, nxt = edition._split_due(jobs)
    assert [j["id"] for j in due] == ["plain", "past"], due
    assert nxt == calendar.timegm((2026, 10, 4, 3, 45, 0)), nxt     # wake at 03:45 UTC for "soon"
    ce._clock[:] = [calendar.timegm((2026, 10, 4, 3, 45, 0)), 0]   # exactly then
    due, _ = edition._split_due(jobs)
    assert [j["id"] for j in due] == ["plain", "past", "soon"], due
    # an unreadable print_at next to a job still ahead: the broken one prints, the poll goes on
    ce._clock[:] = [calendar.timegm((2026, 10, 4, 3, 40, 0)), 0]
    lines = []
    ce.log = lambda *a: lines.append(" ".join(str(x) for x in a))
    due, nxt = edition._split_due([{"id": "broken", "print_at": "tomorrow"}] + jobs[2:])
    assert [j["id"] for j in due] == ["broken"] and nxt == calendar.timegm((2026, 10, 4, 3, 45, 0)), (due, nxt)
    assert any("next at 03:45 UTC, 4 Oct 2026 06:45 Europe/Helsinki (in 5 min)" in line for line in lines), lines
    print("schedule ok: unknown clock holds, past prints, future waits, due at the exact second, a broken time never stops the poll")


if __name__ == "__main__":
    main()
