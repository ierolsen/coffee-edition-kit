# coffee-edition: runs automatically when the Pico powers on.
# Polls GitHub every POLL_SECONDS and prints new jobs. LED:
#   slow blink while joining Wi-Fi, flicker while working,
#   short blip every 10 s while idle, 5 fast blinks after an error,
#   3 long blinks every 10 s: config.py or .env is not filled in yet (nothing else runs).

import time
import gc
import sys
import machine
import config
from coffee_edition import CoffeeEdition, config_problems, wifi_connect, log

led = machine.Pin("LED", machine.Pin.OUT)


def blink(n=1, on=0.08, off=0.12):
    for _ in range(n):
        led.on()
        time.sleep(on)
        led.off()
        time.sleep(off)


def not_set_up(problems):
    """Settings are missing: say what, then blink 3 long until someone fixes them and resets."""
    for p in problems:
        log("setup:", p)
    while True:
        blink(3, 0.6, 0.4)
        time.sleep(10)


def main():
    problems = config_problems(config)
    if problems:
        not_set_up(problems)
    ce = CoffeeEdition(config, feed=led.toggle)
    errors = 0
    while True:
        try:
            ce.own_ip = wifi_connect(config, tick=led.toggle)
            led.on()
            ce.run_once()
            errors = 0
        except Exception as e:
            errors += 1
            log("error (%d in a row):" % errors)
            sys.print_exception(e)
            blink(5)
            if errors >= 10:
                log("too many errors in a row, restarting")
                time.sleep(2)
                machine.reset()
        led.off()
        gc.collect()
        # Sleep until the next poll, or less when a scheduled job is due sooner (then the
        # poll fetches a fresh queue and clock right at that moment).
        wait = getattr(config, "POLL_SECONDS", 300)
        if ce.wait_s is not None:
            wait = max(1, min(wait, ce.wait_s))
        steps, rest = divmod(wait, 10)
        for _ in range(steps):
            blink(1, 0.02, 0)
            time.sleep(10)
        if rest:
            time.sleep(rest)


main()
