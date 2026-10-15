"""Checks the Pico's settings check without a Pico. Runs in CPython:

    python3 pico/test_config.py

A copy of the kit starts with placeholders in config.py and no .env. The Pico must then refuse
to start (and blink three long) instead of polling a repository called OWNER/REPO, and say
exactly which setting is missing, without ever printing a secret.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coffee_edition as ce  # noqa: E402


class Cfg:
    def __init__(self, **kw):
        self.GITHUB_REPO = "someone/coffee-edition"
        self.WIFI_COUNTRY = "GB"
        self.WIFI_SSID = "home"
        self.WIFI_PASSWORD = "not-a-real-password"
        self.GITHUB_TOKEN = "github_pat_example"
        self.__dict__.update(kw)


def main():
    assert ce.config_problems(Cfg()) == [], ce.config_problems(Cfg())
    cases = [
        ({"GITHUB_REPO": "OWNER/REPO"}, "GITHUB_REPO"),
        ({"GITHUB_REPO": "coffee-edition"}, "GITHUB_REPO"),
        ({"GITHUB_REPO": "a/b/c"}, "GITHUB_REPO"),
        ({"WIFI_COUNTRY": "XX"}, "WIFI_COUNTRY"),
        ({"WIFI_COUNTRY": "gb"}, "WIFI_COUNTRY"),
        ({"WIFI_COUNTRY": "GBR"}, "WIFI_COUNTRY"),
        ({"WIFI_SSID": ""}, "WIFI_SSID"),
        ({"WIFI_PASSWORD": ""}, "WIFI_PASSWORD"),
        ({"GITHUB_TOKEN": ""}, "GITHUB_TOKEN"),
    ]
    for change, key in cases:
        problems = ce.config_problems(Cfg(**change))
        assert len(problems) == 1 and key in problems[0], (change, problems)
    fresh = ce.config_problems(Cfg(GITHUB_REPO="OWNER/REPO", WIFI_COUNTRY="XX", WIFI_SSID="", WIFI_PASSWORD="", GITHUB_TOKEN=""))
    assert len(fresh) == 5, fresh
    secret = Cfg(WIFI_PASSWORD="hunter2-secret", GITHUB_TOKEN="github_pat_secret", GITHUB_REPO="OWNER/REPO")
    said = " ".join(ce.config_problems(secret))
    assert "hunter2" not in said and "github_pat_secret" not in said, said
    print("config ok: placeholders and empty secrets are named, %d cases, no secret in the messages" % (len(cases) + 2))


if __name__ == "__main__":
    main()
