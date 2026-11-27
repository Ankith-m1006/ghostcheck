"""Synthetic monitor for the deployed check API (issue #57). Run by .github/workflows/synthetic-monitor.yml.

    python monitor/synthetic_check.py https://ghostcheck-api-demo.vercel.app [--checks monitor/checks.json] [--report out.md]

Each check calls GET /api/check?command=... on the live deployment, which asks the live PyPI registry, and
asserts the verdict, exit code, package count, findings and the no-store header. A transport error or a 5xx is
retried once (one blip is not an outage); a wrong answer is never retried. Exit 1 if any check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

DEFAULT_CHECKS = Path(__file__).resolve().parent / "checks.json"
TIMEOUT_S = 40


@dataclass
class Result:
    name: str
    command: str
    ok: bool = False
    status: int | None = None
    seconds: float = 0.0
    problems: list[str] = field(default_factory=list)
    body: dict | None = None


def http_fetch(base_url: str, command: str):
    import requests

    resp = requests.get(f"{base_url.rstrip('/')}/api/check?{urlencode({'command': command})}", timeout=TIMEOUT_S,
                        headers={"User-Agent": "ghostcheck-synthetic-monitor"})
    return resp.status_code, {k.lower(): v for k, v in resp.headers.items()}, resp.text


def _matches(finding: dict, matcher: dict) -> bool:
    for key, want in matcher.items():
        if key == "message_contains":
            if want not in str(finding.get("message", "")):
                return False
        elif finding.get(key) != want:
            return False
    return True


def assert_response(status: int, headers: dict, text: str, expect: dict) -> tuple[list[str], dict | None]:
    headers = {k.lower(): v for k, v in headers.items()}
    if status != 200:
        return [f"HTTP {status}, expected 200"], None
    problems = []
    if not headers.get("content-type", "").startswith("application/json"):
        problems.append(f"content-type is {headers.get('content-type')!r}, expected application/json")
    if "no-store" not in headers.get("cache-control", ""):
        problems.append(f"cache-control is {headers.get('cache-control')!r}, expected no-store (a cached answer hides outages)")
    try:
        body = json.loads(text)
    except ValueError:
        return problems + ["body is not JSON"], None
    if not isinstance(body, dict):
        return problems + ["body is not a JSON object"], None
    for key in ("verdict", "exit_code", "checked", "deployment"):
        if key in expect and body.get(key) != expect[key]:
            problems.append(f"{key} is {body.get(key)!r}, expected {expect[key]!r}")
    findings = body.get("findings")
    if not isinstance(findings, list):
        problems.append("findings is not a list")
        findings = []
    if expect.get("findings_empty") and findings:
        problems.append(f"expected no findings, got {[(f.get('severity'), f.get('rule')) for f in findings]}")
    any_of = expect.get("finding_any_of")
    if any_of and not any(_matches(f, m) for f in findings for m in any_of):
        problems.append(f"no finding matches any of {any_of}")
    return problems, body


def run(base_url: str, checks: list[dict], fetch=None, retry_wait: float = 20.0) -> list[Result]:
    fetch = fetch or http_fetch
    results = []
    for check in checks:
        r = Result(check.get("name", check["command"]), check["command"])
        for attempt in range(2):
            start = time.monotonic()
            try:
                status, headers, text = fetch(base_url, check["command"])
            except Exception as exc:  # transport error: retry once
                r.problems = [f"request failed: {type(exc).__name__}: {exc}"]
                r.status = None
            else:
                r.status = status
                r.problems, r.body = assert_response(status, headers, text, check["expect"])
            r.seconds = round(time.monotonic() - start, 2)
            transient = r.status is None or r.status >= 500
            if not r.problems or not transient or attempt == 1:
                break
            time.sleep(retry_wait)
        r.ok = not r.problems
        results.append(r)
    return results


def report(base_url: str, results: list[Result]) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    overall = "PASS" if all(r.ok for r in results) else "FAIL"
    lines = [f"## Synthetic monitor: {overall}", "", f"Target: {base_url} (nonproduction demo)  ", f"Time: {when}", ""]
    for r in results:
        lines.append(f"- {'PASS' if r.ok else 'FAIL'} `{r.command}` ({r.name}): HTTP {r.status}, {r.seconds}s")
        if r.body is not None:
            lines.append(f"  - verdict={r.body.get('verdict')!r} exit_code={r.body.get('exit_code')!r} "
                         f"checked={r.body.get('checked')!r} findings="
                         f"{[(f.get('severity'), f.get('rule')) for f in r.body.get('findings') or [] if isinstance(f, dict)]}")
        lines += [f"  - problem: {p}" for p in r.problems]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base_url")
    ap.add_argument("--checks", default=str(DEFAULT_CHECKS))
    ap.add_argument("--report", help="also write the markdown report here")
    args = ap.parse_args(argv)
    checks = json.loads(Path(args.checks).read_text("utf-8"))
    results = run(args.base_url, checks, fetch=http_fetch)
    text = report(args.base_url, results)
    print(text)
    if args.report:
        Path(args.report).write_text(text, "utf-8")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
