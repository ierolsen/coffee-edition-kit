#!/usr/bin/env bash
# Nightly Coffee Edition: checks the issue the routine wrote, commits it to inbox/ on main and
# waits for prepare's verdict on exactly that version of the file.
#
#   bash scripts/commit_issue.sh inbox/YYYY-MM-DD.edition.json
#
# Nothing is committed when:
# - printer.json has nightly "off";
# - the issue is not exactly the pick for its date (note, issue number, print time, file name),
#   shows a picture that is not one of its note's, is more than 30 minutes past its print time,
#   or is dated beyond the next morning (scripts/next_issue.py verify);
# - the issue fails `node edition/build.mjs --preflight`: the full build in Chrome (fields,
#   characters, pages, the PDF) where the machine has Chrome and poppler, the browserless
#   --check where it has not (without Node the same checks run in prepare after the push);
# - the file holds something that looks like a token or a key.
#
# The commit is made as the repository's git user (git config user.name and user.email), or as
# COFFEE_GIT_NAME / COFFEE_GIT_EMAIL when set; with neither, as "Coffee Edition". Hooks are off,
# so nothing can add a line to the message, and author, committer and message are checked
# before the push. The message is fixed: chore(issue): <date> issue <NNN>.
#
# Exit codes: 0 queued (nightly "live") or drafted (nightly "dry-run"); 1 refused, nothing
# pushed; 2 prepare rejected it: fix the file and run this again; 3 prepare skipped it (late,
# or the date already has an issue); 4 no verdict in time.
#
# The whole run fits one cloud Bash call (10 minutes at most): WAIT_SECONDS (default 570) is
# counted from the start, and the wait for prepare gets what is left, a minute at least.
set -euo pipefail
start=$(date +%s)

cd "$(dirname "$0")/.."
file="${1:?usage: bash scripts/commit_issue.sh inbox/<date>.edition.json}"
case "$file" in
  inbox/*.edition.json) ;;
  *) echo "not an issue in inbox/: $file"; exit 1 ;;
esac
[ -f "$file" ] || { echo "no such file: $file"; exit 1; }

mode=$(python3 -c 'import json; print(json.load(open("printer.json")).get("nightly", "off"))')
if [ "$mode" = "off" ]; then
  echo "printer.json has nightly off: nothing committed"
  exit 1
fi

name="${COFFEE_GIT_NAME:-$(git config user.name || true)}"
email="${COFFEE_GIT_EMAIL:-$(git config user.email || true)}"
if [ -z "$name" ] || [ -z "$email" ]; then
  name="Coffee Edition" email="coffee-edition@users.noreply.github.com"
fi
export GIT_AUTHOR_NAME="$name" GIT_AUTHOR_EMAIL="$email"
export GIT_COMMITTER_NAME="$name" GIT_COMMITTER_EMAIL="$email"
git_() { git -c core.hooksPath=/dev/null -c commit.gpgsign=false "$@"; }

# the newest log and inbox decide the pick
git_ pull --rebase --autostash --quiet origin main

python3 scripts/next_issue.py verify "$file"
if command -v node >/dev/null 2>&1; then
  node edition/build.mjs "$file" --preflight
else
  echo "node not found: the field, glyph and page checks run in prepare after the push"
fi
if grep -qE 'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY' "$file"; then
  echo "the issue holds something that looks like a token or a key: nothing committed"
  exit 1
fi

read -r day number note < <(python3 -c '
import json, sys
i = json.load(open(sys.argv[1]))
print(i["date"], "%03d" % i["issue"], i["note"])' "$file")

git_ add -- "$file"
if git_ diff --cached --quiet >/dev/null 2>&1; then  # --quiet still prints a new file's header
  echo "this version of the issue is already committed"
else
  git_ commit --quiet --no-verify -m "chore(issue): ${day} issue ${number}" -m "Note: ${note}"
fi

who="$(git log -1 --format='%an <%ae> | %cn <%ce>')"
if [ "$who" != "$name <$email> | $name <$email>" ]; then
  echo "the commit identity is not the expected one ($who): nothing pushed"
  exit 1
fi
if git log -1 --format='%B' | grep -qiE '^[a-z-]+-by:|generated with'; then
  echo "the commit message carries a signature line: nothing pushed"
  exit 1
fi

for attempt in 1 2 3; do
  if git_ push --quiet origin HEAD:main; then
    break
  fi
  if [ "$attempt" = 3 ]; then
    echo "push failed three times: nothing reached main"
    exit 1
  fi
  git_ pull --rebase --quiet origin main  # a workflow committed the log in between
done
echo "pushed: $(git log -1 --format='%h %s')"

left=$(( ${WAIT_SECONDS:-570} - ($(date +%s) - start) ))
[ "$left" -ge 60 ] || left=60
python3 scripts/next_issue.py wait "$file" --timeout "$left"
