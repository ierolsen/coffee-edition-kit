# Contributing

Thank you for wanting to improve Coffee Edition. Issues and pull requests are welcome.

- **Bugs:** open an issue with what you did, what you expected, and what happened. For the Pico, include its log (`mpremote repl`), with your Wi-Fi name, addresses and token removed.
- **Printers:** a report that a printer works (model, formats from `tools/printer_info.py`, `printer.json`) helps others; open an issue titled "Works with ...".
- **Code:** keep changes small and focused. Run the tests before opening a pull request:

```bash
node edition/test.mjs
python3 scripts/test_nightly.py
python3 pico/test_clock.py && python3 pico/test_scan.py && python3 pico/test_config.py
```

- **Style:** plain standard-library Python and Node, no new dependencies without a good reason; MicroPython code must run on a Pico W's memory. No em-dashes or en-dashes in issue text.
- **Secrets:** never include a token, a Wi-Fi password or a real `.env` in an issue, a commit or a screenshot.
