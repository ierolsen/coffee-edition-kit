#!/usr/bin/env bash
# Publishes what prepare.py made, run from the main checkout in the prepare workflow.
#
#   scripts/publish.sh QUEUE_ROOT ARCHIVE_ROOT
#
# - queue branch: rewritten as a single commit holding only the current jobs, so old
#   print files fall out of history instead of piling up in the repo
# - archive branch: new PDFs are added on top of what is there; it is never rewritten
# - main: the inbox files that became jobs, the print log (log/) and the kept nightly issues (issues/)
# Commits are made with git plumbing on a separate index, so the main checkout's own
# index and working tree are untouched until the last step.
#
# GitHub can refuse a push for a moment on its side (on 15 Oct the archive push failed with
# "fatal error in commit_refs" after the queue was out, so the Pico printed an issue the log never
# heard of). Each push is tried three times. An archive that still fails is a warning: the log on
# main is what the nightly pick and the Pico's report rely on, so it is written anyway.
set -euo pipefail
queue_root=$(cd "$1" && pwd)
archive_root=$(cd "$2" && pwd)
repo=$(git rev-parse --absolute-git-dir)
stamp=$(date -u +%Y-%m-%dT%H:%MZ)
index=$(mktemp -u)

in_tree() { (cd "$1" && shift && GIT_INDEX_FILE="$index" git --git-dir="$repo" --work-tree=. "$@"); }

# push NAME GIT-PUSH-ARGS...: three tries, 5 and 10 s apart
push() {
  local name=$1 attempt
  shift
  for attempt in 1 2 3; do
    if git push "$@"; then return 0; fi
    if [ "$attempt" != 3 ]; then
      echo "$name: push failed (try $attempt of 3), trying again"
      sleep $((attempt * 5))
    fi
  done
  echo "$name: push failed three times"
  return 1
}

# queue: a fresh root commit with only the current jobs
rm -f "$index"
in_tree "$queue_root" add -A .
tree=$(GIT_INDEX_FILE="$index" git --git-dir="$repo" write-tree)
if [ "$tree" != "$(git rev-parse -q --verify 'origin/queue^{tree}' || true)" ]; then
  commit=$(git commit-tree "$tree" -m "queue: $stamp")
  push queue -f origin "$commit:refs/heads/queue" || exit 1
  echo "queue branch rewritten ($stamp)"
else
  echo "queue unchanged"
fi

# archive: new PDFs on top of the existing tree
if [ -n "$(find "$archive_root" -type f -name '*.pdf' -print -quit)" ]; then
  rm -f "$index"
  parent=()
  if git rev-parse -q --verify origin/archive >/dev/null; then
    GIT_INDEX_FILE="$index" git read-tree origin/archive
    parent=(-p origin/archive)
  fi
  in_tree "$archive_root" add --ignore-removal .
  tree=$(GIT_INDEX_FILE="$index" git --git-dir="$repo" write-tree)
  commit=$(git commit-tree "$tree" "${parent[@]}" -m "archive: $stamp")
  if push archive origin "$commit:refs/heads/archive"; then
    echo "archive branch updated"
  else
    echo "::warning::the archive branch was not updated this run; the queue and the print log still go out"
  fi
fi
rm -f "$index"

# main: consumed inbox files and the print log
git add -A inbox log
if [ -d issues ]; then git add -A issues; fi
if git diff --cached --quiet; then
  echo "main unchanged"
else
  git commit -q -m "log: queue update $stamp"
  for attempt in 1 2 3; do
    if git pull -q --rebase origin "${GITHUB_REF_NAME:-main}" && git push -q origin "HEAD:${GITHUB_REF_NAME:-main}"; then
      break
    fi
    git rebase --abort >/dev/null 2>&1 || true
    if [ "$attempt" = 3 ]; then
      echo "main: push failed three times"
      exit 1
    fi
    echo "main: push failed (try $attempt of 3), trying again"
    sleep $((attempt * 5))
  done
  echo "main updated"
fi
