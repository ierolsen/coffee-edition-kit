"""Checks the Pico's printer search without a network. Runs in CPython:

    python3 pico/test_scan.py

A printer that sleeps, or comes back at a new address, must still be found: the cached address
first, then a quick pass over the subnet, then a patient pass that waits longer at each address.
Both passes start next to the printer's last address and move outward. Here the network is a
dictionary: each "host" answers only when the caller waits long enough.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coffee_edition as ce  # noqa: E402


class Cfg:
    PRINTER_MATCH = "LaserJet"
    SCAN_FAST_MS = 150
    SCAN_PATIENT_MS = 1500


class FakePrinter:
    model = "Example LaserJet 1000"

    def __init__(self, host):
        self.host = host


def finder(network, cached=None, own="10.0.0.10"):
    """network: {host: ms it needs to answer}. Returns (edition, list of (host, wait) port tries)."""
    tries = []

    def port_open(host, port, wait_ms):
        tries.append((host, wait_ms))
        return host in network and network[host] <= wait_ms

    ce._port_open = port_open
    ce.log = lambda *a: None
    e = ce.CoffeeEdition.__new__(ce.CoffeeEdition)
    e.cfg, e.port, e.match, e.own_ip, e.feed = Cfg, 631, "hp laserjet", own, lambda: None
    e.state = {"printed": [], "done": [], "printer": cached}
    e._save_state = lambda: None
    e._probe = lambda host: FakePrinter(host) if host in network else None
    return e, tries


def found(e):
    p = e.find_printer()
    return p.host if p else None


def main():
    # the printer kept its address: one probe, no scan
    e, tries = finder({"10.0.0.11": 1}, cached="10.0.0.11")
    assert found(e) == "10.0.0.11" and tries == [], tries

    # it moved next door and is awake: the quick pass finds it on its second try
    e, tries = finder({"10.0.0.12": 20}, cached="10.0.0.11")
    assert found(e) == "10.0.0.12", tries
    assert tries == [("10.0.0.11", 150), ("10.0.0.12", 150)], tries
    assert e.state["printer"] == "10.0.0.12", "the new address is remembered"

    # it moved to .40 and is asleep (answers in 900 ms): the quick pass misses, the patient one finds it
    e, tries = finder({"10.0.0.40": 900}, cached="10.0.0.11")
    assert found(e) == "10.0.0.40", tries[-3:]
    quick = [h for h, w in tries if w == 150]
    patient = [h for h, w in tries if w == 1500]
    assert len(quick) == 253 and "10.0.0.10" not in quick, ("one quick pass, our own address skipped", len(quick))
    assert patient[:3] == ["10.0.0.11", "10.0.0.12", "10.0.0.13"] and patient[-1] == "10.0.0.40", (patient[:4], patient[-1])

    # no printer anywhere: both passes run once and give up
    e, tries = finder({}, cached="10.0.0.11")
    assert found(e) is None and len(tries) == 2 * 253, len(tries)

    # first start, nothing cached: the search starts next to the Pico itself
    e, tries = finder({"10.0.0.9": 1})
    assert found(e) == "10.0.0.9" and [h for h, _ in tries] == ["10.0.0.11", "10.0.0.9"], tries
    print("scan ok: cached address first, quick then patient pass, outward from the last address, own address skipped")


if __name__ == "__main__":
    main()
