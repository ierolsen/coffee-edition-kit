#!/usr/bin/env python3
"""Reads every QR code on the page images given and prints what they say, as JSON: {image: [texts]}.

    python3 edition/qrdecode.py page-1.png page-2.png

test.mjs runs it on the Fresh Ink fixture's pages, printed at 300 dpi, so a code that prints but
does not scan is caught. Needs zxing-cpp and Pillow (pip install zxing-cpp pillow); without them
it exits with 2 and test.mjs skips the check.
"""
import json
import sys

try:
    import zxingcpp
    from PIL import Image
except ImportError:
    sys.exit(2)

out = {}
for path in sys.argv[1:]:
    with Image.open(path) as im:
        out[path] = [r.text for r in zxingcpp.read_barcodes(im.convert("L")) if r.format == zxingcpp.BarcodeFormat.QRCode]
print(json.dumps(out))
