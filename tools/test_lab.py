#!/usr/bin/env python3
"""coffee-edition test lab: a fake printer and a fake GitHub on your computer.

Lets the Pico run its whole job without a real printer (pico/selftest.py drives it):
  - fake GitHub  on port 8633: serves tools/lab/queue/... like the GitHub API
  - fake printer on port 8631: speaks IPP like an AirPrint printer and saves
    every page it receives to tools/received/ (and opens it on macOS)

Usage:  python3 tools/test_lab.py [--pdf] [--pwg] [--no-open]
  --pdf      the fake printer also accepts PDF (default: JPEG and Apple raster only,
             like many cheap inkjets)
  --pwg      the fake printer also accepts PWG raster, like many cheap lasers
The computer and the Pico must be on the same Wi-Fi, and the firewall must let ports 8631
and 8633 in. Stop with Ctrl+C. Standard library only; macOS, Linux and Windows.
"""

import argparse
import json
import itertools
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
LAB_ROOT = os.path.join(HERE, "lab")
RECEIVED = os.path.join(HERE, "received")
MODEL = "coffee-edition test printer"
PRINTER_PORT = 8631
GITHUB_PORT = 8633
EXT = {"image/jpeg": "jpg", "application/pdf": "pdf", "image/urf": "urf",
       "image/pwg-raster": "pwg", "text/plain": "txt"}

ARGS = None
JOBS = {}
JOB_IDS = itertools.count(1)
VERSION = [0x0101]
LOCK = threading.Lock()


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ------------------------------------------------------------------ IPP ---

def attr(tag, name, value):
    values = value if isinstance(value, (list, tuple)) else [value]
    out = b""
    for i, v in enumerate(values):
        n = name.encode() if i == 0 else b""
        if isinstance(v, bool):
            v = b"\x01" if v else b"\x00"
        elif isinstance(v, int):
            v = struct.pack(">i", v)
        elif not isinstance(v, bytes):
            v = str(v).encode()
        out += bytes([tag]) + struct.pack(">H", len(n)) + n + struct.pack(">H", len(v)) + v
    return out


def parse_request(data):
    version, op, req_id = struct.unpack(">HHI", data[:8])
    VERSION[0] = version
    attrs, name, i = {}, None, 8
    while i < len(data):
        tag = data[i]
        i += 1
        if tag == 0x03:
            break
        if tag < 0x10:
            continue
        nl = struct.unpack(">H", data[i:i + 2])[0]
        i += 2
        if nl:
            name = data[i:i + nl].decode()
        i += nl
        vl = struct.unpack(">H", data[i:i + 2])[0]
        i += 2
        raw = data[i:i + vl]
        i += vl
        if tag in (0x21, 0x23) and vl == 4:
            val = struct.unpack(">i", raw)[0]
        elif tag >= 0x40:
            val = raw.decode(errors="replace")
        else:
            val = raw
        attrs.setdefault(name, []).append(val)
    return op, req_id, attrs, data[i:]


def response(status, req_id, printer_attrs=b"", job_attrs=b""):
    out = struct.pack(">HHI", VERSION[0], status, req_id) + b"\x01"
    out += attr(0x47, "attributes-charset", "utf-8")
    out += attr(0x48, "attributes-natural-language", "en")
    if printer_attrs:
        out += b"\x04" + printer_attrs
    if job_attrs:
        out += b"\x02" + job_attrs
    return out + b"\x03"


def printer_attributes(host):
    uri = "ipp://%s:8631/ipp/print" % host
    return b"".join([
        attr(0x45, "printer-uri-supported", uri),
        attr(0x44, "uri-security-supported", "none"),
        attr(0x44, "uri-authentication-supported", "none"),
        attr(0x42, "printer-name", "coffee-edition-lab"),
        attr(0x41, "printer-info", "coffee-edition test lab"),
        attr(0x41, "printer-location", "test lab"),
        attr(0x45, "printer-more-info", "http://%s:8631/" % host),
        attr(0x41, "printer-make-and-model", MODEL),
        attr(0x23, "printer-state", 3),
        attr(0x44, "printer-state-reasons", "none"),
        attr(0x22, "printer-is-accepting-jobs", True),
        attr(0x49, "document-format-supported", ARGS.formats),
        attr(0x49, "document-format-default", "application/octet-stream"),
        attr(0x23, "operations-supported", [0x0002, 0x0004, 0x0009, 0x000A, 0x000B]),
        attr(0x44, "ipp-versions-supported", ["1.1", "2.0"]),
        attr(0x47, "charset-configured", "utf-8"),
        attr(0x47, "charset-supported", "utf-8"),
        attr(0x48, "natural-language-configured", "en"),
        attr(0x48, "generated-natural-language-supported", "en"),
        attr(0x44, "compression-supported", "none"),
        attr(0x44, "pdl-override-supported", "not-attempted"),
        attr(0x44, "media-default", "iso_a4_210x297mm"),
        attr(0x44, "media-supported", ["iso_a4_210x297mm", "na_letter_8.5x11in"]),
        attr(0x21, "printer-up-time", int(time.time())),
        attr(0x21, "queued-job-count", 0),
    ])


def job_attributes(host, job_id, state):
    return b"".join([
        attr(0x21, "job-id", job_id),
        attr(0x45, "job-uri", "ipp://%s:8631/jobs/%d" % (host, job_id)),
        attr(0x23, "job-state", state),
        attr(0x44, "job-state-reasons",
             "job-completed-successfully" if state == 9 else "none"),
    ])


def handle_ipp(body, host, client):
    op, req_id, attrs, doc = parse_request(body)
    if op == 0x000B:  # Get-Printer-Attributes
        return response(0x0000, req_id, printer_attributes(host))
    if op == 0x0004:  # Validate-Job
        return response(0x0000, req_id)
    if op == 0x0002:  # Print-Job
        fmt = (attrs.get("document-format") or ["application/octet-stream"])[0]
        if fmt not in ARGS.formats and fmt != "application/octet-stream":
            log("REFUSED: format %s is not supported" % fmt)
            return response(0x040A, req_id)
        job_id = next(JOB_IDS)
        name = (attrs.get("job-name") or ["job"])[0]
        os.makedirs(RECEIVED, exist_ok=True)
        path = os.path.join(RECEIVED, "job-%d.%s" % (job_id, EXT.get(fmt, "bin")))
        with open(path, "wb") as f:
            f.write(doc)
        with LOCK:
            JOBS[job_id] = time.time()
        log("PRINTED (fake): '%s' %s, %d KB, from %s -> %s"
            % (name, fmt, len(doc) // 1024, client, os.path.relpath(path)))
        if ARGS.open and sys.platform == "darwin" and fmt in ("image/jpeg", "application/pdf"):
            subprocess.Popen(["open", path])
        return response(0x0000, req_id, job_attrs=job_attributes(host, job_id, 5))
    if op == 0x0009:  # Get-Job-Attributes
        job_id = (attrs.get("job-id") or [0])[0]
        with LOCK:
            t = JOBS.get(job_id)
        if t is None:
            return response(0x0406, req_id)  # client-error-not-found
        state = 9 if time.time() - t > 2 else 5
        return response(0x0000, req_id, job_attrs=job_attributes(host, job_id, state))
    if op == 0x000A:  # Get-Jobs
        return response(0x0000, req_id)
    return response(0x0501, req_id)  # operation not supported


# ----------------------------------------------------------- HTTP glue ---

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the console readable
        pass

    def _body(self):
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            out = b""
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip(), 16)
                if size == 0:
                    while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    return out
                out += self.rfile.read(size)
                self.rfile.read(2)
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PrinterHandler(Handler):
    def do_POST(self):
        body = self._body()
        host = self.headers.get("Host", "localhost").split(":")[0]
        try:
            out = handle_ipp(body, host, self.client_address[0])
        except Exception as e:  # malformed request
            log("IPP error: %r" % e)
            self._send(400, b"", "text/plain")
            return
        self._send(200, out, "application/ipp")


DISPATCHES = []  # workflow_dispatch calls the Pico made, newest last


class GitHubHandler(Handler):
    def do_POST(self):
        # The Pico's report after printing: POST .../actions/workflows/<file>/dispatches
        parts = urlparse(self.path).path.split("/")
        if len(parts) != 8 or parts[1] != "repos" or parts[4:6] != ["actions", "workflows"] or parts[7] != "dispatches":
            self._send(404, b'{"message":"Not Found"}', "application/json")
            return
        if not self.headers.get("Authorization"):
            self._send(401, b'{"message":"Requires authentication"}', "application/json")
            return
        try:
            body = json.loads(self._body() or b"{}")
        except ValueError:
            self._send(422, b'{"message":"Problems parsing JSON"}', "application/json")
            return
        DISPATCHES.append({"workflow": parts[6], "ref": body.get("ref"), "inputs": body.get("inputs", {})})
        log("GitHub (fake): %s started, ref %s, %s" % (parts[6], body.get("ref"), body.get("inputs")))
        self._send(204, b"", "application/json")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/lab/dispatches":  # for the self test to check the report arrived
            self._send(200, json.dumps(DISPATCHES).encode(), "application/json")
            return
        parts = url.path.split("/", 5)  # '', repos, owner, repo, contents, path
        if len(parts) < 6 or parts[1] != "repos" or parts[4] != "contents":
            self._send(404, b'{"message":"Not Found"}', "application/json")
            return
        if not self.headers.get("Authorization"):
            self._send(401, b'{"message":"Requires authentication"}', "application/json")
            return
        rel = os.path.normpath(unquote(parts[5]))
        path = os.path.join(LAB_ROOT, rel)
        if rel.startswith("..") or not os.path.isfile(path):
            self._send(404, b'{"message":"Not Found"}', "application/json")
            return
        with open(path, "rb") as f:
            data = f.read()
        log("GitHub (fake): %s downloaded (%d KB) -> %s"
            % (rel, len(data) // 1024, self.client_address[0]))
        if not ARGS.chunked:
            self._send(200, data, "application/octet-stream")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for i in range(0, len(data), 7000):  # odd chunk size on purpose
            part = data[i:i + 7000]
            self.wfile.write(b"%x\r\n" % len(part) + part + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")


def main():
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pdf", action="store_true", help="fake printer also accepts PDF")
    ap.add_argument("--pwg", action="store_true", help="fake printer also accepts PWG raster")
    ap.add_argument("--no-open", dest="open", action="store_false",
                    help="do not open received pages in Preview")
    ap.add_argument("--chunked", action="store_true",
                    help="fake GitHub answers with chunked transfer encoding")
    ARGS = ap.parse_args()
    ARGS.formats = ["application/octet-stream", "image/jpeg", "image/urf"]
    if ARGS.pdf:
        ARGS.formats.insert(1, "application/pdf")
    if ARGS.pwg:
        ARGS.formats.insert(1, "image/pwg-raster")

    try:
        servers = [ThreadingHTTPServer(("0.0.0.0", PRINTER_PORT), PrinterHandler),
                   ThreadingHTTPServer(("0.0.0.0", GITHUB_PORT), GitHubHandler)]
    except OSError as e:
        sys.exit("Port %d or %d is in use (%s). Close the program using it and try again."
                 % (PRINTER_PORT, GITHUB_PORT, e))
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()

    ip = lan_ip()
    print("coffee-edition test lab is running")
    print("  this computer   : %s" % ip)
    print("  fake printer    : ipp://%s:8631/ipp/print  (formats: %s)"
          % (ip, ", ".join(ARGS.formats[1:])))
    print("  fake GitHub     : http://%s:%d" % (ip, GITHUB_PORT))
    print("  received pages  : %s" % os.path.relpath(RECEIVED))
    print("Stop with Ctrl+C. Waiting for the Pico...\n", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
