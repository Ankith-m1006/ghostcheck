#!/usr/bin/env bash
# Fetch step of the synthetic monitor (issue #57): one GET /api/check per check in the checks file, saved as
# <i>.status ("<http code> <seconds>"), <i>.headers and <i>.body in the output folder for synthetic_check.py.
# curl retries a timeout or a transient 5xx once (one blip is not an outage); a 200 with a wrong answer is never
# retried. Each attempt is capped at 40 s.
set -uo pipefail
target="${1:?target URL}"; checks="${2:?checks file}"; out="${3:?output folder}"
mkdir -p "$out"
i=0
while IFS= read -r command; do
  if ! curl -sS -G "${target%/}/api/check" --data-urlencode "command=$command" \
      -A "ghostcheck-synthetic-monitor" --max-time 40 --retry 1 --retry-delay 20 --retry-connrefused \
      -D "$out/$i.headers" -o "$out/$i.body" -w '%{http_code} %{time_total}' > "$out/$i.status"; then
    echo "000 0" > "$out/$i.status"
  fi
  i=$((i + 1))
done < <(python -c 'import json, sys; [print(c["command"]) for c in json.load(open(sys.argv[1], encoding="utf-8"))]' "$checks")
