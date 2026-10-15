# Printers: what yours accepts, and the settings that follow

Coffee Edition prints through **IPP**, the protocol behind AirPrint and Mopria, on port 631. Almost every network printer sold in the last decade speaks it. What differs is the **document format** a printer accepts. GitHub Actions prepares the formats you list in `printer.json`, and the Pico sends the first one your printer takes, preferring PDF, then PWG raster, then JPEG.

## 1. Find the printer on your network

- The printer's own menu or network report usually shows its address.
- Your router's list of connected devices shows it too.
- From a computer on the same Wi-Fi:

```bash
dns-sd -B _ipp._tcp                     # macOS: lists IPP printers; Ctrl-C to stop
dns-sd -L "Printer Name" _ipp._tcp      # macOS: its host name and port
avahi-browse -rt _ipp._tcp              # Linux (avahi-utils): names, addresses and ports
```

## 2. Ask it what it accepts

```bash
python3 tools/printer_info.py 10.0.0.50        # or its name, like printer.local
```

It uses the Pico's own IPP code, only reads, and ends with the lines to put in `printer.json` and `pico/config.py`:

```
printer          Example LaserJet 1000
formats          application/octet-stream, image/urf, image/pwg-raster, application/PCLm
PWG resolutions  600x600dpi
paper            iso_a4_210x297mm, na_letter_8.5x11in, ...

printer.json:
  "formats": ["image/pwg-raster"],
  "pwg_dpi": 600,
pico/config.py:
  PRINTER_MATCH = "Example LaserJet"
```

On macOS and Linux with CUPS installed, `ipptool -tv ipp://10.0.0.50/ipp/print get-printer-attributes.test` prints the full list as well.

## 3. Choose the formats

| The printer lists | `printer.json` | Notes |
|---|---|---|
| `application/pdf` | `"formats": ["application/pdf"]` | The best case: small files, sharp text, the printer does the rest. |
| `image/pwg-raster` but no PDF | `"formats": ["image/pwg-raster"]` and `"pwg_dpi"` from its resolution list | Typical for cheap lasers. Pages are rendered in the cloud at that resolution, in 8-bit gray. 300 is plenty for text; use 600 if the printer lists only 600. |
| `image/jpeg` only | `"formats": ["image/jpeg"]` | Some inkjets. One JPEG per page at `jpeg_dpi` (300). |
| `image/urf` only | not supported yet | Apple raster is on the roadmap. |

Listing several formats works too (the kit's default lists PDF, PWG and JPEG, so it fits most printers out of the box), but each extra format costs build time and queue space. Once you know your printer, keep only the one it uses.

Other settings in `printer.json`:

| Key | Default | Meaning |
|---|---|---|
| `pwg_dpi` | `300` | Resolution of PWG pages. |
| `jpeg_dpi`, `jpeg_quality` | `300`, `85` | JPEG pages. |
| `grayscale` | `false` | JPEG pages in gray. PWG pages are always gray. |
| `keep_days` | `3` | Jobs older than this leave the queue. |
| `timezone` | `"UTC"` | The IANA time zone of your print times, like `Europe/London` or `America/New_York`. Daylight saving time is handled. |
| `edition_print_time` | `"07:30"` | When the morning issue prints, in that time zone. |
| `nightly` | `"off"` | `off`: the routine writes nothing. `dry-run`: issues are built and archived as PDFs, never printed. `live`: printed. |

## 4. A test print without the Pico

To check a format before involving the Pico, print a file straight from your computer with `ipptool`, which guesses the format from the file name:

```bash
python3 scripts/pwg.py some.pdf test.pwg --dpi 300        # make a PWG raster file from a PDF
ipptool -tv -f test.pwg ipp://10.0.0.50/ipp/print print-job.test
```

A `successful-ok` status and a sheet of paper mean the printer takes that format at that resolution.

## 5. Printer settings that matter

- **Sleep is fine, power-off is not.** A sleeping printer wakes for network jobs, and the Pico waits for it. A printer that switches itself fully off after some idle time ("auto off", "shut down after") does not; set that to never.
- **Paper:** A4. Coffee Edition lays out A4 pages; Letter is on the roadmap.
- **Address:** the Pico finds the printer again when its address changes, so a fixed address is optional. If you reserve one on your router, you can also set `PRINTER_HOST` in `pico/config.py` to skip the search.
- **Same network:** the Pico and the printer must be on the same Wi-Fi network. Guest networks usually keep devices apart.
