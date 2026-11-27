"""Synthetic monitor assertions for the deployed check API (issue #57). Run by .github/workflows/synthetic-monitor-run.yml.

    bash monitor/fetch.sh https://ghostcheck-api-demo.vercel.app monitor/checks.json responses/
    python monitor/synthetic_check.py --target https://ghostcheck-api-demo.vercel.app --responses responses/ [--report out.md]

fetch.sh (curl) calls GET /api/check?command=... on the live deployment, which asks the live PyPI registry, and
saves <i>.status, <i>.headers and <i>.body per check; curl retries a timeout or a 5xx once. This file only reads
those files, so no Python outside registry.py reaches the network (AGENTS.md rule 4). It asserts the verdict, exit
code, package count, findings, the JSON content type and the no-store header. Exit 1 if any check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CHECKS = Path(__file__).resolve().parent / "checks.json"


@dataclass
class Result:
    name: str
    command: str
    ok: bool = False
    status: int | None = None
    seconds: float | None = None
    problems: list[str] = field(default_factory=list)
    body: dict | None = None


def _read(path: Path) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:  # keep curl's CRLF as written
            return f.read()
    except OSError:
        return None


def _last_header_block(raw: str) -> dict[str, str]:
    """curl -D keeps every response it saw (redirects, retried attempts); only the final one counts."""
    blocks = [b for b in raw.replace("\r", "").split("\n\n") if b.strip().startswith("HTTP/")]
    headers = {}
    for line in (blocks[-1].splitlines()[1:] if blocks else []):
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def load_response(folder: Path, i: int):
    """(status or None, seconds or None, headers, body text) for check number i, as fetch.sh saved it."""
    status_line = (_read(folder / f"{i}.status") or "").split()
    try:
        status = int(status_line[0]) if status_line else None
    except ValueError:
        status = None
    try:
        seconds = round(float(status_line[1]), 2) if len(status_line) > 1 else None
    except ValueError:
        seconds = None
    if status == 0:  # curl writes 000 when no response arrived
        status = None
    return status, seconds, _last_header_block(_read(folder / f"{i}.headers") or ""), _read(folder / f"{i}.body") or ""


def _matches(finding: dict, matcher: dict) -> bool:
    for key, want in matcher.items():
        if key == "message_contains":
            if want not in str(finding.get("message", "")):
                return False
        elif finding.get(key) != want:
            return False
    return True


def assert_response(status: int | None, headers: dict, text: str, expect: dict) -> tuple[list[str], dict | None]:
    if status is None:
        return ["no response (connection failed or timed out after one retry)"], None
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
    bad = [f for f in findings if not isinstance(f, dict)]
    if bad:
        problems.append(f"{len(bad)} finding(s) are not an object: {bad[:3]!r}")
    findings = [f for f in findings if isinstance(f, dict)]
    if expect.get("findings_empty") and (findings or bad):
        problems.append(f"expected no findings, got {[(f.get('severity'), f.get('rule')) for f in findings]}")
    any_of = expect.get("finding_any_of")
    if any_of and not any(_matches(f, m) for f in findings for m in any_of):
        problems.append(f"no finding matches any of {any_of}")
    return problems, body


def run(checks: list[dict], folder: Path) -> list[Result]:
    results = []
    for i, check in enumerate(checks):
        r = Result(check.get("name", check["command"]), check["command"])
        r.status, r.seconds, headers, text = load_response(Path(folder), i)
        r.problems, r.body = assert_response(r.status, headers, text, check["expect"])
        r.ok = not r.problems
        results.append(r)
    return results


def report(target: str, results: list[Result]) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    overall = "PASS" if results and all(r.ok for r in results) else "FAIL"
    lines = [f"## Synthetic monitor: {overall}", "", f"Target: {target} (nonproduction demo)  ", f"Time: {when}", ""]
    for r in results:
        lines.append(f"- {'PASS' if r.ok else 'FAIL'} `{r.command}` ({r.name}): HTTP {r.status}, {r.seconds}s")
        if r.body is not None:
            findings = r.body.get("findings") if isinstance(r.body.get("findings"), list) else []
            lines.append(f"  - verdict={r.body.get('verdict')!r} exit_code={r.body.get('exit_code')!r} "
                         f"checked={r.body.get('checked')!r} findings="
                         f"{[(f.get('severity'), f.get('rule')) for f in findings if isinstance(f, dict)]}")
        lines += [f"  - problem: {p}" for p in r.problems]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True, help="the deployment fetch.sh called (for the report)")
    ap.add_argument("--responses", required=True, help="folder fetch.sh wrote")
    ap.add_argument("--checks", default=str(DEFAULT_CHECKS))
    ap.add_argument("--report", help="also write the markdown report here")
    args = ap.parse_args(argv)
    checks = json.loads(Path(args.checks).read_text("utf-8"))
    results = run(checks, Path(args.responses))
    text = report(args.target, results)
    print(text)
    if args.report:
        Path(args.report).write_text(text, "utf-8")
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
