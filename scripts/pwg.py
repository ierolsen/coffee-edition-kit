#!/usr/bin/env python3
"""Turn a PDF into PWG raster (8-bit gray), the raster format IPP Everywhere printers take.

Many cheap laser printers accept only raster documents (image/pwg-raster, image/urf,
application/PCLm), not PDF or JPEG; the HP LaserJet M109-M112 series, which this was tested on,
is one. This renders each page with pdftoppm and writes it in
PWG 5102.4 framing: the "RaS2" sync word, then per page a 1796-byte header followed by the
bitmap, each line as a repeat count plus PackBits-style runs of pixels.

Pages are rendered without anti-aliasing by default: a laser printer can only place or skip a
dot, so grey edge pixels would be halftoned into fuzz, and hard edges also make the file about
half the size. --antialias turns smoothing back on.

Usage:  python3 scripts/pwg.py in.pdf out.pwg [--dpi 600] [--first N] [--last N] [--antialias]
Needs:  pdftoppm (poppler-utils).
"""
import argparse
import re
import struct
import subprocess
import tempfile
from pathlib import Path

SYNC = b"RaS2"
RUNS = re.compile(rb"(.)\1*", re.S)
A4 = "iso_a4_210x297mm"


def page_header(width, height, dpi, total):
    """PWG 5102.4 page header for one 8-bit sGray page (same layout as a CUPS raster v2 header)."""
    h = bytearray(1796)

    def text(off, s):
        b = s.encode("ascii")
        h[off:off + len(b)] = b

    def u32(off, v):
        struct.pack_into(">I", h, off, v)

    text(0, "PwgRaster")
    u32(276, dpi)                                   # HWResolution x
    u32(280, dpi)                                   # HWResolution y
    u32(340, 1)                                     # NumCopies
    u32(352, round(width * 72 / dpi))               # PageSize in points
    u32(356, round(height * 72 / dpi))
    u32(372, width)                                 # Width in pixels
    u32(376, height)                                # Height in pixels
    u32(384, 8)                                     # BitsPerColor
    u32(388, 8)                                     # BitsPerPixel
    u32(392, width)                                 # BytesPerLine
    u32(396, 0)                                     # ColorOrder: chunky
    u32(400, 18)                                    # ColorSpace: sGray
    u32(420, 1)                                     # NumColors
    u32(452, total)                                 # TotalPageCount
    struct.pack_into(">i", h, 456, 1)               # CrossFeedTransform
    struct.pack_into(">i", h, 460, 1)               # FeedTransform
    u32(472, width)                                 # ImageBoxRight
    u32(476, height)                                # ImageBoxBottom
    u32(480, 0xFFFFFF)                              # AlternatePrimary: white
    text(1732, A4)                                  # PageSizeName
    return bytes(h)


def encode_line(line):
    """One line as runs: n in 0..127 repeats the next pixel n+1 times, n in 129..255 copies 257-n pixels."""
    out = bytearray()
    lit = bytearray()

    def flush():
        while lit:
            chunk = lit[:128]
            del lit[:128]
            out.append(0 if len(chunk) == 1 else 257 - len(chunk))
            out.extend(chunk)

    for m in RUNS.finditer(line):
        run = m.end() - m.start()
        if run == 1:
            lit.extend(m.group(1))
            continue
        flush()
        px = line[m.start()]
        while run:
            n = min(run, 128)
            out.append(n - 1)
            out.append(px)
            run -= n
    flush()
    return out


def encode_page(pixels, width, height):
    """Bitmap of one page: each line starts with how many times it repeats (identical lines merge)."""
    mv = memoryview(pixels)
    out = bytearray()
    y = 0
    while y < height:
        line = mv[y * width:(y + 1) * width]
        repeat = 1
        while repeat < 256 and y + repeat < height and mv[(y + repeat) * width:(y + repeat + 1) * width] == line:
            repeat += 1
        out.append(repeat - 1)
        out.extend(encode_line(line))
        y += repeat
    return out


def read_pgm(path):
    data = path.read_bytes()
    m = re.match(rb"P5\s+(?:#[^\n]*\n\s*)*(\d+)\s+(\d+)\s+(\d+)\s", data)
    if not m or int(m.group(3)) != 255:
        raise ValueError("unexpected PGM from pdftoppm: %s" % path)
    width, height = int(m.group(1)), int(m.group(2))
    return width, height, data[m.end():m.end() + width * height]


def pdf_to_pwg(pdf, dst, dpi=600, first=None, last=None, antialias=False):
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["pdftoppm", "-gray", "-r", str(dpi)]
        if not antialias:
            cmd += ["-aa", "no", "-aaVector", "no"]
        if first:
            cmd += ["-f", str(first)]
        if last:
            cmd += ["-l", str(last)]
        subprocess.run(cmd + [str(pdf), str(Path(tmp) / "p")], check=True, timeout=300,
                       stderr=subprocess.DEVNULL)
        pages = sorted(Path(tmp).glob("p-*.pgm"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
        if not pages:
            raise RuntimeError("pdftoppm produced no pages for %s" % pdf)
        with open(dst, "wb") as out:
            out.write(SYNC)
            for page in pages:
                width, height, pixels = read_pgm(page)
                out.write(page_header(width, height, dpi, len(pages)))
                out.write(encode_page(pixels, width, height))
    return len(pages)


def main():
    ap = argparse.ArgumentParser(description="Convert a PDF to 8-bit gray PWG raster.")
    ap.add_argument("pdf")
    ap.add_argument("out")
    ap.add_argument("--dpi", type=int, default=600)
    ap.add_argument("--first", type=int)
    ap.add_argument("--last", type=int)
    ap.add_argument("--antialias", action="store_true", help="smooth edges (larger file, softer on laser)")
    a = ap.parse_args()
    n = pdf_to_pwg(a.pdf, a.out, a.dpi, a.first, a.last, a.antialias)
    print("%s: %d page(s), %d bytes at %d dpi" % (a.out, n, Path(a.out).stat().st_size, a.dpi))


if __name__ == "__main__":
    main()
