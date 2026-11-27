#!/usr/bin/env bash
# Alert route for a failed synthetic-monitor run (issue #57): open an issue, or comment on the open one with the
# same title, so one outage is one issue. Needs GH_TOKEN with issues: write, plus TITLE, REPORT, RUN_URL, EVENT, SHA.
set -euo pipefail
label="monitor-alert"
gh label create "$label" --color B60205 --description "Opened by a failed synthetic monitor run" 2>/dev/null || true

body="$(mktemp)"
{
  echo "The synthetic monitor failed."
  echo
  echo "- Run: $RUN_URL"
  echo "- Trigger: $EVENT"
  echo "- Commit: $SHA"
  echo "- Time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo
  echo "$REPORT"
  echo
  echo "First response: README.md, section \"Deployed demo and synthetic monitor\"."
} > "$body"

num="$(gh issue list --state open --label "$label" --limit 100 --json number,title \
  --jq 'map(select(.title == env.TITLE)) | .[0].number // empty')"
if [ -n "$num" ]; then
  gh issue comment "$num" --body-file "$body"
  echo "Updated alert issue #$num"
else
  gh issue create --title "$TITLE" --label "$label" --body-file "$body"
fi
