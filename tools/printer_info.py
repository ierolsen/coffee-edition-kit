#!/usr/bin/env python3
"""What your printer accepts, and the printer.json settings that follow from it.

Asks the printer over IPP (the protocol AirPrint printers speak, port 631) with the same code the
Pico uses, and prints its model, the document formats it takes, the raster resolutions and the
paper sizes. Then it suggests "formats" and "pwg_dpi" for printer.json and a PRINTER_MATCH for
pico/config.py. It only reads; it never prints anything.

    python3 tools/printer_info.py 10.0.0.50          the printer's address
    python3 tools/printer_info.py printer.local          or its network name
    python3 tools/printer_info.py HOST --port 631 --path /ipp/print

Find the address in the printer's menu or network page, on your router, or with
`dns-sd -B _ipp._tcp` (macOS) / `avahi-browse -rt _ipp._tcp` (Linux). Standard library only.
"""
import argparse
import os
import struct
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pico"))
import coffee_edition as ce  # noqa: E402

WANTED = ["printer-make-and-model", "printer-state", "printer-state-reasons", "document-format-supported",
          "pwg-raster-document-resolution-supported", "pwg-raster-document-type-supported",
          "urf-supported", "media-supported", "media-default", "sides-supported", "printer-uuid"]
# What prepare.py can make, best first; the Pico picks the first one the printer also takes.
MAKES = ["application/pdf", "image/pwg-raster", "image/jpeg"]


def resolution(raw):
    """An IPP resolution value: x, y and units (3 = dots per inch)."""
    if isinstance(raw, (bytes, bytearray)) and len(raw) == 9:
        x, y, units = struct.unpack(">iiB", raw)
        return "%dx%d%s" % (x, y, "dpi" if units == 3 else "dpcm")
    return repr(raw)


def ask(host, port, paths):
    """Get-Printer-Attributes over plain HTTP, built and parsed by the Pico's own IPP code."""
    last = None
    for path in paths:
        body = ce.ipp_request(0x000B, "ipp://%s:%d%s" % (host, port, path), op_attrs=[(0x44, "requested-attributes", WANTED)])
        req = urllib.request.Request("http://%s:%d%s" % (host, port, path), data=body, headers={"Content-Type": "application/ipp"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                status, attrs = ce.ipp_parse(r.read(1 << 20))
        except Exception as e:
            last = e
            continue
        if status <= 0xFF:
            return path, attrs
        last = OSError("Get-Printer-Attributes failed 0x%04x" % status)
    raise SystemExit("no answer from %s:%d (%s). Is the printer on and on this network?" % (host, port, last))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=631)
    ap.add_argument("--path", help="the printer's IPP path (default: try /ipp/print, /ipp/printer, /ipp)")
    a = ap.parse_args()
    path, attrs = ask(a.host, a.port, [a.path] if a.path else list(ce.PRINTER_PATHS))
    one = lambda k: (attrs.get(k) or [""])[0]  # noqa: E731
    formats = attrs.get("document-format-supported", [])
    resolutions = [resolution(r) for r in attrs.get("pwg-raster-document-resolution-supported", [])]
    media = attrs.get("media-supported", [])
    states = {3: "idle", 4: "printing", 5: "stopped"}

    print("printer          %s" % one("printer-make-and-model"))
    print("address          ipp://%s:%d%s" % (a.host, a.port, path))
    print("state            %s (%s)" % (states.get(one("printer-state"), one("printer-state")), ", ".join(attrs.get("printer-state-reasons", [])) or "none"))
    print("formats          %s" % ", ".join(formats))
    if resolutions:
        print("PWG resolutions  %s" % ", ".join(resolutions))
    if attrs.get("pwg-raster-document-type-supported"):
        print("PWG types        %s" % ", ".join(attrs["pwg-raster-document-type-supported"]))
    if attrs.get("urf-supported"):
        print("URF              %s" % ", ".join(attrs["urf-supported"]))
    print("paper            %s%s" % (", ".join(media[:8]), " ..." if len(media) > 8 else ""))

    usable = [f for f in MAKES if f in formats]
    print()
    if not usable:
        print("This printer takes none of the formats Coffee Edition makes (PDF, PWG raster, JPEG).")
        if "image/urf" in formats:
            print("It takes Apple raster (URF) only; that is on the roadmap, not in this version.")
        return 1
    dpi = 300
    if "image/pwg-raster" in usable:
        dpis = sorted({int(r.split("x")[0]) for r in resolutions if r.endswith("dpi")})
        if dpis and 300 not in dpis:
            dpi = dpis[0]
        if "sgray_8" not in attrs.get("pwg-raster-document-type-supported", ["sgray_8"]):
            print("warning: the printer does not list sgray_8 among its PWG types; PWG pages may be refused.")
    if not any(m.startswith("iso_a4") for m in media):
        print("warning: the printer does not list A4 paper; Coffee Edition prints A4 only for now.")
    print("printer.json:")
    print('  "formats": [%s],' % ", ".join('"%s"' % f for f in usable))
    if "image/pwg-raster" in usable:
        print('  "pwg_dpi": %d,' % dpi)
    words = [w for w in one("printer-make-and-model").split() if len(w) > 2]
    if words:
        print("pico/config.py:")
        print('  PRINTER_MATCH = "%s"' % " ".join(words[:2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
