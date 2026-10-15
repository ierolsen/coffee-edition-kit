# coffee-edition: Pico firmware core (MicroPython, Raspberry Pi Pico W / Pico 2 W).
#
# The Pico is only a courier:
#   1. read queue/index.json from your private GitHub repo (a copy of coffee-edition-kit),
#   2. find the printer on the home Wi-Fi (no router settings needed),
#   3. download each file and stream it to the printer over IPP, chunk by chunk.
# Converting HTML/PDF into something the printer accepts happens in the cloud
# (scripts/prepare.py in GitHub Actions), so the Pico never opens a document.

import socket
import struct
import json
import time
import gc
import sys
import errno

try:
    import ssl
except ImportError:
    ssl = None
try:
    import select
except ImportError:
    import uselect as select

ON_PICO = sys.platform == "rp2"
CHUNK = 4096
STATE_FILE = "state.json"
# Best first: PDF keeps text sharp and is small; JPEG works on almost every AirPrint printer.
FORMAT_PREFERENCE = ("application/pdf", "image/pwg-raster", "image/urf", "image/jpeg")
PRINTER_PATHS = ("/ipp/print", "/ipp/printer", "/ipp")


def log(*args):
    print("[coffee-edition]", *args)


def _noop():
    pass


def wifi_connect(cfg, timeout=30, tick=_noop):
    """Join the home Wi-Fi (Pico only). Returns the Pico's IP address.

    The country (which channels the radio may use) and power saving are set before the
    "already connected" check, so they also hold after a soft reset that kept the link."""
    if not ON_PICO:
        return None
    import network
    try:
        import rp2
        rp2.country(getattr(cfg, "WIFI_COUNTRY", "XX"))
    except Exception:
        pass
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        wlan.config(pm=wlan.PM_NONE)  # no Wi-Fi power saving: fewer dropped connections
    except Exception:
        pass
    if wlan.isconnected():
        return wlan.ifconfig()[0]
    wlan.connect(cfg.WIFI_SSID, cfg.WIFI_PASSWORD)
    t0 = time.time()
    while not wlan.isconnected():
        if time.time() - t0 > timeout:
            raise OSError("Wi-Fi connection failed (status %d). Check SSID/password; "
                          "the Pico only sees 2.4 GHz networks." % wlan.status())
        tick()
        time.sleep(0.5)
    ip = wlan.ifconfig()[0]
    log("Wi-Fi connected:", ip)
    return ip


# ---------------------------------------------------------------- HTTP ---

def _split_url(url):
    scheme, rest = url.split("://", 1)
    hostport, _, path = rest.partition("/")
    path = "/" + path
    default = 443 if scheme == "https" else (631 if scheme == "ipp" else 80)
    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
        return scheme, host, int(port), path
    return scheme, hostport, default, path


def _connect(host, port, tls, timeout, ca=None):
    ai = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0]
    s = socket.socket(ai[0], socket.SOCK_STREAM, ai[2])
    s.settimeout(timeout)
    try:
        s.connect(ai[-1])
        if tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if ca:
                ctx.verify_mode = ssl.CERT_REQUIRED
                ctx.load_verify_locations(cadata=ca)
            else:
                ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(s, server_hostname=host)
    except Exception:
        s.close()
        raise
    return s


def _write_all(s, data):
    mv = memoryview(data)
    while len(mv):
        n = s.write(mv)
        if not n:
            raise OSError("socket write failed")
        mv = mv[n:]


def _read_exact(s, n):
    buf = b""
    while len(buf) < n:
        d = s.read(n - len(buf))
        if not d:
            raise OSError("connection closed")
        buf += d
    return buf


class Response:
    """HTTP/1.1 response whose body is read in chunks (Content-Length or chunked)."""

    def __init__(self, sock):
        self.sock = sock
        while True:
            line = sock.readline()
            if not line:
                raise OSError("no HTTP response")
            self.status = int(line.split(None, 2)[1])
            self.headers = {}
            while True:
                h = sock.readline()
                if not h or h == b"\r\n":
                    break
                k, _, v = h.decode().partition(":")
                self.headers[k.strip().lower()] = v.strip()
            if self.status != 100:
                break
        self._chunked = "chunked" in self.headers.get("transfer-encoding", "").lower()
        cl = self.headers.get("content-length")
        self._left = int(cl) if (cl is not None and not self._chunked) else -1
        self._chunk_left = 0
        self._eof = self.status in (204, 304) or self._left == 0

    def read(self, n=CHUNK):
        if self._eof:
            return b""
        s = self.sock
        if self._chunked:
            if self._chunk_left == 0:
                line = s.readline()
                if not line:
                    raise OSError("connection closed in chunk header")
                size = int(line.split(b";")[0].strip().decode(), 16)
                if size == 0:
                    while True:  # optional trailers
                        t = s.readline()
                        if not t or t == b"\r\n":
                            break
                    self._eof = True
                    return b""
                self._chunk_left = size
            d = s.read(min(n, self._chunk_left))
            if not d:
                raise OSError("connection closed mid-chunk")
            self._chunk_left -= len(d)
            if self._chunk_left == 0:
                _read_exact(s, 2)  # CRLF after each chunk
            return d
        want = n if self._left < 0 else min(n, self._left)
        d = s.read(want)
        if not d:
            if self._left > 0:
                raise OSError("connection closed early")
            self._eof = True
            return b""
        if self._left > 0:
            self._left -= len(d)
            if self._left == 0:
                self._eof = True
        return d

    def read_all(self, limit=65536):
        out = bytearray()
        while True:
            d = self.read()
            if not d:
                return bytes(out)
            out.extend(d)
            if len(out) > limit:
                raise ValueError("response too large")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def http_request(method, url, headers=None, body=None, body_len=None,
                 timeout=20, ca=None, max_redirects=3):
    """Send a request and return an open Response.

    body may be bytes or a callable writer(sock) that streams body_len bytes.
    Redirects are followed for GET; credentials never leave the original host.
    """
    headers = dict(headers or {})
    for _ in range(max_redirects + 1):
        scheme, host, port, path = _split_url(url)
        tls = scheme == "https"
        s = _connect(host, port, tls, timeout, ca if tls else None)
        try:
            h = {"Host": host if port in (80, 443) else "%s:%d" % (host, port),
                 "Connection": "close"}
            h.update(headers)
            if body is not None:
                h["Content-Length"] = str(body_len if body_len is not None else len(body))
            head = "%s %s HTTP/1.1\r\n" % (method, path)
            head += "".join("%s: %s\r\n" % kv for kv in h.items()) + "\r\n"
            _write_all(s, head.encode())
            if callable(body):
                body(s)
            elif body:
                _write_all(s, body)
            r = Response(s)
        except Exception:
            s.close()
            raise
        if method == "GET" and r.status in (301, 302, 303, 307, 308) and "location" in r.headers:
            loc = r.headers["location"]
            r.close()
            if loc.startswith("/"):
                loc = "%s://%s:%d%s" % (scheme, host, port, loc)
            if _split_url(loc)[1] != host:
                headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
            url = loc
            continue
        return r
    raise OSError("too many redirects")


# --------------------------------------------------------------- clock ---
# The Pico has no battery-backed clock, and the epoch of time.time() differs between
# MicroPython ports. Every GitHub answer carries a Date header; the latest one plus the
# ticks_ms elapsed since then gives the current UTC time as Unix seconds. Until the first
# answer the clock is unknown, and scheduled jobs are held, never printed.

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_clock = [None, 0]  # [Unix seconds from the last Date header, ticks_ms when it arrived]


def _days(y, m, d):
    """Days from 1970-01-01 to a proleptic Gregorian date."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m - 3 if m > 2 else m + 9) + 2) // 5 + d - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def http_date_to_unix(s):
    """'Sat, 03 Oct 2026 18:23:09 GMT' -> Unix seconds."""
    parts = s.split()
    hh, mm, ss = (int(x) for x in parts[4].split(":"))
    return _days(int(parts[3]), _MONTHS.index(parts[2]) + 1, int(parts[1])) * 86400 + hh * 3600 + mm * 60 + ss


def iso_to_unix(s):
    """'2026-10-04T03:45:00+00:00' (or ...Z) -> Unix seconds. UTC only."""
    date, _, rest = s.partition("T")
    y, m, d = (int(x) for x in date.split("-"))
    hh, mm, ss = (int(x) for x in rest[:8].split(":"))
    if rest[8:] not in ("Z", "+00:00"):
        raise ValueError("not a UTC time: " + s)
    return _days(y, m, d) * 86400 + hh * 3600 + mm * 60 + ss


def note_date(headers):
    try:
        _clock[0] = http_date_to_unix(headers["date"])
        _clock[1] = time.ticks_ms()
    except (KeyError, ValueError, IndexError):
        pass


def now_unix():
    if _clock[0] is None:
        return None
    return _clock[0] + time.ticks_diff(time.ticks_ms(), _clock[1]) // 1000


def utc_hhmm(unix):
    s = unix % 86400
    return "%02d:%02d" % (s // 3600, s % 3600 // 60)


def config_problems(cfg):
    """What still has to be filled in before the Pico can work: [] when the settings look usable.
    Checks presence and placeholders only; it never prints a secret."""
    out = []
    repo = getattr(cfg, "GITHUB_REPO", "")
    if not repo or repo == "OWNER/REPO" or repo.count("/") != 1 or repo.startswith("/") or repo.endswith("/"):
        out.append("config.py: set GITHUB_REPO to your copy, like \"your-name/coffee-edition\"")
    country = getattr(cfg, "WIFI_COUNTRY", "")
    if not (isinstance(country, str) and len(country) == 2 and country.isalpha() and country.upper() == country and country != "XX"):
        out.append("config.py: set WIFI_COUNTRY to your two-letter country code, like \"GB\" or \"US\"")
    for key in ("WIFI_SSID", "WIFI_PASSWORD", "GITHUB_TOKEN"):
        if not getattr(cfg, key, ""):
            out.append(".env: %s is empty (copy .env to the Pico: mpremote cp .env :)" % key)
    return out


# -------------------------------------------------------------- GitHub ---

class GitHub:
    def __init__(self, cfg):
        self.base = getattr(cfg, "API_BASE", "https://api.github.com").rstrip("/")
        self.repo = cfg.GITHUB_REPO
        self.ref = getattr(cfg, "GITHUB_BRANCH", "main")
        self.ca = getattr(cfg, "GITHUB_CA_DER", None)
        self.headers = {
            "Accept": "application/vnd.github.raw+json",
            "User-Agent": "coffee-edition-pico",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = getattr(cfg, "GITHUB_TOKEN", None)
        if token:
            self.headers["Authorization"] = "Bearer " + token

    def open(self, path):
        url = "%s/repos/%s/contents/%s?ref=%s" % (self.base, self.repo, path, self.ref)
        r = http_request("GET", url, self.headers, ca=self.ca, timeout=30)
        note_date(r.headers)
        if r.status != 200:
            r.close()
            raise OSError("GitHub answered %d for %s" % (r.status, path))
        return r

    def get_json(self, path):
        r = self.open(path)
        try:
            return json.loads(r.read_all(65536))
        finally:
            r.close()

    def dispatch(self, workflow, inputs, ref="main"):
        """Start a workflow_dispatch run (needs the token's Actions: write permission)."""
        url = "%s/repos/%s/actions/workflows/%s/dispatches" % (self.base, self.repo, workflow)
        headers = dict(self.headers)
        headers["Accept"] = "application/vnd.github+json"
        headers["Content-Type"] = "application/json"
        r = http_request("POST", url, headers, body=json.dumps({"ref": ref, "inputs": inputs}).encode(),
                         ca=self.ca, timeout=30)
        note_date(r.headers)
        try:
            if r.status != 204:
                raise OSError("GitHub answered %d to the report" % r.status)
        finally:
            r.close()


# ----------------------------------------------------------------- IPP ---

def _attr(tag, name, value):
    values = value if isinstance(value, (list, tuple)) else [value]
    out = b""
    for i, v in enumerate(values):
        n = name.encode() if i == 0 else b""
        v = v if isinstance(v, bytes) else str(v).encode()
        out += bytes([tag]) + struct.pack(">H", len(n)) + n + struct.pack(">H", len(v)) + v
    return out


_request_id = [0]


def ipp_request(op, printer_uri, op_attrs=(), job_attrs=()):
    _request_id[0] += 1
    b = struct.pack(">BBHI", 1, 1, op, _request_id[0]) + b"\x01"
    b += _attr(0x47, "attributes-charset", "utf-8")
    b += _attr(0x48, "attributes-natural-language", "en")
    b += _attr(0x45, "printer-uri", printer_uri)
    for tag, name, value in op_attrs:
        b += _attr(tag, name, value)
    if job_attrs:
        b += b"\x02"
        for tag, name, value in job_attrs:
            b += _attr(tag, name, value)
    return b + b"\x03"


def ipp_parse(data):
    """Return (status_code, {name: [values]}) for an IPP response."""
    status = struct.unpack(">H", data[2:4])[0]
    attrs = {}
    name = None
    i = 8
    end = len(data)
    while i < end:
        tag = data[i]
        i += 1
        if tag == 0x03:
            break
        if tag < 0x10:  # group delimiter
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
        if tag in (0x21, 0x23) and vl == 4:      # integer, enum
            val = struct.unpack(">i", raw)[0]
        elif tag == 0x22:                       # boolean
            val = bool(raw[0]) if vl else False
        elif tag >= 0x40:                       # text, name, keyword, uri, mime type
            try:
                val = raw.decode()
            except Exception:
                val = raw
        else:
            val = raw
        if name is not None:
            attrs.setdefault(name, []).append(val)
    return status, attrs


class Printer:
    def __init__(self, host, port, path, attrs):
        self.host, self.port, self.path = host, port, path
        self.uri = "ipp://%s:%d%s" % (host, port, path)
        self.url = "http://%s:%d%s" % (host, port, path)
        self.formats = attrs.get("document-format-supported", [])
        self.model = (attrs.get("printer-make-and-model") or [""])[0]
        self.state = (attrs.get("printer-state") or [3])[0]

    def call(self, payload, timeout=10, limit=131072):
        r = http_request("POST", self.url, {"Content-Type": "application/ipp"},
                         body=payload, timeout=timeout)
        try:
            if r.status != 200:
                raise OSError("printer answered HTTP %d" % r.status)
            return ipp_parse(r.read_all(limit))
        finally:
            r.close()

    def attributes(self, timeout=5):
        st, attrs = self.call(ipp_request(0x000B, self.uri, op_attrs=[
            (0x44, "requested-attributes", ["document-format-supported", "printer-make-and-model",
                                            "printer-state", "printer-state-reasons"])]),
            timeout=timeout)
        if st > 0xFF:
            raise OSError("Get-Printer-Attributes failed 0x%04x" % st)
        return attrs

    def print_stream(self, fmt, name, size, src, feed=_noop, timeout=60):
        """Print-Job: send IPP header + document, streaming the document from src."""
        hdr = ipp_request(0x0002, self.uri, op_attrs=[
            (0x42, "requesting-user-name", "coffee-edition"),
            (0x42, "job-name", name[:200]),
            (0x49, "document-format", fmt)])
        state = {"sent": 0}

        def writer(sock):
            _write_all(sock, hdr)
            while True:
                d = src.read(CHUNK)  # source errors propagate and abort the job
                if not d:
                    break
                try:
                    _write_all(sock, d)
                except OSError as e:  # printer replied early (error) and closed
                    log("printer stopped reading:", e)
                    return
                state["sent"] += len(d)
                feed()
            if state["sent"] != size:
                raise OSError("download ended at %d of %d bytes" % (state["sent"], size))

        r = http_request("POST", self.url, {"Content-Type": "application/ipp"},
                         body=writer, body_len=len(hdr) + size, timeout=timeout)
        try:
            if r.status != 200:
                raise OSError("printer answered HTTP %d" % r.status)
            return ipp_parse(r.read_all(65536))
        finally:
            r.close()

    def job_state(self, job_id):
        st, attrs = self.call(ipp_request(0x0009, self.uri, op_attrs=[
            (0x21, "job-id", struct.pack(">i", job_id)),
            (0x44, "requested-attributes", ["job-state", "job-state-reasons"])]))
        return (attrs.get("job-state") or [0])[0], attrs.get("job-state-reasons", [])


def _port_open(host, port, timeout_ms):
    s = socket.socket()
    s.setblocking(False)
    try:
        try:
            s.connect(socket.getaddrinfo(host, port)[0][-1])
        except OSError as e:
            if e.args[0] not in (errno.EINPROGRESS, errno.EAGAIN):
                return False
        p = select.poll()
        p.register(s, select.POLLOUT)
        res = p.poll(timeout_ms)
        if not res:
            return False
        ev = res[0][1]
        return bool(ev & select.POLLOUT) and not (ev & (select.POLLERR | select.POLLHUP))
    finally:
        s.close()


# -------------------------------------------------------- CoffeeEdition ---

class CoffeeEdition:
    def __init__(self, cfg, feed=_noop):
        self.cfg = cfg
        self.gh = GitHub(cfg)
        self.feed = feed  # called while working (LED blink / watchdog)
        self.port = getattr(cfg, "PRINTER_PORT", 631)
        self.match = (getattr(cfg, "PRINTER_MATCH", "") or "").lower()
        self.wait_s = None
        self.state_file = getattr(cfg, "STATE_FILE", STATE_FILE)
        self.own_ip = None
        self.state = self._load_state()

    # -- state on flash: which files were already accepted by the printer
    def _load_state(self):
        try:
            with open(self.state_file) as f:
                st = json.load(f)
        except Exception:
            st = {}
        st.setdefault("printed", [])
        st.setdefault("done", [])
        st.setdefault("printer", None)
        return st

    def _save_state(self):
        self.state["printed"] = self.state["printed"][-300:]
        self.state["done"] = self.state["done"][-100:]
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        try:
            import os
            os.rename(tmp, self.state_file)
        except Exception:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f)

    # -- printer discovery
    def _probe(self, host):
        for path in ((getattr(self.cfg, "PRINTER_PATH", None),) + PRINTER_PATHS):
            if not path:
                continue
            try:
                p = Printer(host, self.port, path, {})
                attrs = p.attributes()
            except Exception:
                continue
            p = Printer(host, self.port, path, attrs)
            if self.match and self.match not in p.model.lower():
                return None
            return p
        return None

    def _subnet(self):
        net = getattr(self.cfg, "SCAN_SUBNET", None)
        if net:
            return net
        if self.own_ip:
            return self.own_ip.rsplit(".", 1)[0] + "."
        return None

    def _scan_order(self, net):
        """Host numbers to try: outward from the printer's last address (or ours), since a router
        that hands out a new address usually picks one nearby; then the rest of 1..254."""
        last = self.state.get("printer") or self.own_ip or ""
        try:
            centre = int(last.rsplit(".", 1)[1]) if last.startswith(net) else 1
        except (ValueError, IndexError):
            centre = 1
        order = [centre]
        for d in range(1, 254):
            order += [n for n in (centre + d, centre - d) if 1 <= n <= 254]
        return order

    def find_printer(self):
        for host in (getattr(self.cfg, "PRINTER_HOST", None), self.state.get("printer")):
            if host:
                p = self._probe(host)
                if p:
                    return p
        net = self._subnet()
        if not net:
            return None
        order = self._scan_order(net)
        # A sleeping printer's Wi-Fi may take a while to answer: a quick pass first, and if that
        # finds nothing, a patient one that waits longer at every address.
        for wait_ms in (getattr(self.cfg, "SCAN_FAST_MS", 150), getattr(self.cfg, "SCAN_PATIENT_MS", 1500)):
            log("searching the network for the printer (%sx, %d ms per address, from .%d)..." % (net, wait_ms, order[0]))
            for i in order:
                host = net + str(i)
                self.feed()
                if host == self.own_ip or not _port_open(host, self.port, wait_ms):
                    continue
                p = self._probe(host)
                if p:
                    log("found:", p.model, "at", host)
                    self.state["printer"] = host
                    self._save_state()
                    return p
        return None

    # -- printing
    def _pick_format(self, job, printer):
        for fmt in FORMAT_PREFERENCE:
            if fmt in job.get("formats", {}) and fmt in printer.formats:
                return fmt
        return None

    def _print_file(self, printer, fmt, job, f):
        name = "%s (%s)" % (job.get("name", job["id"]), f["path"].rsplit("/", 1)[-1])
        for attempt in range(4):
            src = self.gh.open(f["path"])
            try:
                st, attrs = printer.print_stream(fmt, name, f["size"], src, self.feed)
            finally:
                src.close()
            if st <= 0xFF:
                job_id = (attrs.get("job-id") or [0])[0]
                log("accepted:", f["path"], "printer job", job_id)
                return job_id
            if st in (0x0507, 0x0502):  # busy / temporarily unavailable
                log("printer busy, retrying in 15s")
                time.sleep(15)
                continue
            raise OSError("printer refused %s: 0x%04x" % (f["path"], st))
        raise OSError("printer stayed busy")

    def _wait_done(self, printer, job_id, timeout_s=600):
        if not job_id:
            return None
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                state, reasons = printer.job_state(job_id)
            except Exception as e:
                log("could not read job state:", e)
                return None
            if state == 9:
                return True
            if state in (7, 8):
                log("printer job", job_id, "ended in state", state, reasons)
                return False
            for _ in range(5):
                self.feed()
                time.sleep(1)
        return None

    def _split_due(self, pending):
        """Jobs to print now, and the earliest print_at still ahead (Unix seconds) or None.

        A job without print_at, or whose print_at has passed, is due. With the clock
        unknown, scheduled jobs wait: printing at the wrong hour is worse than late.
        """
        now = now_unix()
        due, ahead, held = [], [], 0
        for j in pending:
            at = j.get("print_at")
            if not at:
                due.append(j)
                continue
            try:
                t = iso_to_unix(at)
            except (ValueError, TypeError, IndexError):
                log("unreadable print_at", at, "for", j["id"], "- printing it now")
                due.append(j)
                continue
            if now is None:
                held += 1
            elif t <= now:
                due.append(j)
            else:
                ahead.append((t, j.get("print_local") or ""))
        if held:
            log("clock unknown, holding", held, "scheduled job(s)")
        nxt = min(t for t, _ in ahead) if ahead else None
        if nxt is not None:
            local = [loc for t, loc in ahead if t == nxt and loc]
            log("%d job(s) waiting, next at %s UTC%s (in %d min)"
                % (len(ahead), utc_hhmm(nxt), (", " + local[0]) if local else "", (nxt - now + 59) // 60))
        return due, nxt

    def run_once(self):
        """One poll. Returns the number of files sent to the printer.

        Afterwards self.wait_s says how soon to poll again when a scheduled job is near
        (None: the normal POLL_SECONDS).
        """
        self.wait_s = None
        index = self.gh.get_json(getattr(self.cfg, "QUEUE_INDEX", "queue/index.json"))
        pending = [j for j in index.get("jobs", []) if j["id"] not in self.state["done"]]
        if not pending:
            log("nothing to print")
            return 0
        due, nxt = self._split_due(pending)
        if nxt is not None:
            self.wait_s = max(1, nxt - now_unix())
        if not due:
            return 0  # do not wake the printer for a job that is not due yet
        printer = self.find_printer()
        if not printer:
            log("printer not found (off or not on this Wi-Fi?), will retry")
            self.wait_s = 60 if self.wait_s is None else min(self.wait_s, 60)
            return 0
        if printer.state == 5:
            log("printer is stopped (paper, ink?), will retry")
            return 0
        sent = 0
        for job in sorted(due, key=lambda j: j.get("created", "")):
            fmt = self._pick_format(job, printer)
            if not fmt:
                log("no common format for", job["id"], "printer accepts", printer.formats)
                continue
            log("printing", job["id"], "as", fmt)
            printer_jobs = []
            for f in job["formats"][fmt]:
                if f["path"] in self.state["printed"]:
                    continue
                job_id = self._print_file(printer, fmt, job, f)
                # Accepted by the printer: never send it again, even if we crash now.
                self.state["printed"].append(f["path"])
                self._save_state()
                sent += 1
                printer_jobs.append(job_id)
                ok = self._wait_done(printer, job_id)
                if ok is False:
                    self._report(job["id"], "failed", printer_jobs)
                    raise OSError("printer reported an error for " + f["path"])
                gc.collect()
            self.state["done"].append(job["id"])
            self._save_state()
            log("done:", job["id"])
            self._report(job["id"], "printed", printer_jobs)
        if nxt is not None:
            self.wait_s = max(1, nxt - now_unix())  # printing took a while; aim at the real time
        return sent

    def _report(self, job_id, state, printer_jobs):
        """Tell GitHub what happened so the print log on main can say it. Never fails a print."""
        workflow = getattr(self.cfg, "REPORT_WORKFLOW", "print-log.yml")
        if not workflow:
            return
        try:
            self.gh.dispatch(workflow, {"job": job_id, "state": state,
                                        "printer_job": ",".join(str(j) for j in printer_jobs if j)},
                             ref=getattr(self.cfg, "REPORT_REF", "main"))
            log("reported", state, "to GitHub")
        except Exception as e:
            log("could not report to GitHub:", e)
