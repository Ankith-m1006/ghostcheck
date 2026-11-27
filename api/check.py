"""Read-only HTTP check for the Day 20 synthetic monitor (issue #57). A NONPRODUCTION DEMO deployment on Vercel.

    GET /api/check?command=pip+install+requestss

Returns the same JSON verdict as the MCP tool `check_install` (a parity test keeps them equal), plus
"deployment": "nonproduction-demo". It only reads PyPI and npm: no cache is read or written, nothing is stored,
and no secret is needed. A package that cannot be checked inside the time budget is "unverified" (fail closed,
AGENTS.md rule 1), never "ok".
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghostcheck import __version__  # noqa: E402
from ghostcheck.parsers import PYPI, normalize_pypi, parse_npm_command, parse_pip_command, unread_install_sources  # noqa: E402
from ghostcheck.registry import Fetcher, Registry, _requests_fetcher  # noqa: E402
from ghostcheck.rules import INFO, MEDIUM, UNVERIFIED, Finding, check_dependency, exit_code  # noqa: E402

MAX_COMMAND_CHARS = 2_000   # one install line, not a whole log
MAX_PACKAGES = 10           # each package is at least one registry request
TIME_BUDGET_S = 20.0        # + one REQUEST_TIMEOUT_S stays under maxDuration (30 s) in vercel.json
REQUEST_TIMEOUT_S = 5.0
VERDICTS = {0: "ok", 1: "block", 3: "unverified"}
HEADERS = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}


class BudgetRegistry(Registry):
    """Registry with no cache file, no retries and a hard deadline: a serverless call cannot sleep through backoff."""

    def __init__(self, budget_s: float, fetcher: Fetcher):
        super().__init__(cache_path=None, offline=False, fetcher=fetcher, min_interval=0)
        self.deadline = time.monotonic() + budget_s

    def _fetch(self, url: str, method: str = "GET", headers: dict | None = None, retries: int = 4):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("time budget spent")
        return super()._fetch(url, method, headers, retries=0)

    def save(self) -> None:  # read-only deployment: never persist anything
        return None


def _error(status: int, message: str, extra: dict | None = None):
    return status, {**HEADERS, **(extra or {})}, json.dumps({"error": message})


def respond(method: str, path: str, fetcher: Fetcher | None = None, budget_s: float = TIME_BUDGET_S):
    """(status, headers, json body) for one request. Pure, so tests drive it without a socket."""
    if method != "GET":
        return _error(405, "only GET is supported", {"Allow": "GET"})
    params = parse_qs(urlsplit(path).query, keep_blank_values=True)
    values = params.get("command", [])
    if len(values) != 1 or not values[0].strip():
        return _error(400, "pass exactly one non-empty command, e.g. ?command=pip+install+requests")
    command = values[0]
    if len(command) > MAX_COMMAND_CHARS:
        return _error(413, f"command is longer than {MAX_COMMAND_CHARS} characters; send one install at a time")

    deps = parse_pip_command(command, source="command") + parse_npm_command(command, source="command")
    seen: set[tuple[str, str]] = set()
    unique = []
    for d in deps:  # one check per registry identity (AGENTS.md rule 7)
        key = (d.ecosystem, normalize_pypi(d.name) if d.ecosystem == PYPI else d.name)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    if len(unique) > MAX_PACKAGES:
        return _error(400, f"at most {MAX_PACKAGES} packages per request; this command has {len(unique)}")

    findings = [Finding(INFO, UNVERIFIED, src, "", f"install source not read: '{src}'; check it with the ghostcheck CLI", "command")
                for src in unread_install_sources(command)]
    if not unique and not findings:
        result = {"verdict": "no-install-found", "exit_code": 0, "checked": 0, "findings": []}
    else:
        registry = BudgetRegistry(budget_s, fetcher or _requests_fetcher(timeout=REQUEST_TIMEOUT_S))
        for dep in unique:
            findings += check_dependency(dep, registry)[0]
        code = exit_code(findings)
        verdict = VERDICTS[code]
        if verdict == "ok" and any(f.severity == MEDIUM for f in findings):
            verdict = "review"
        result = {"verdict": verdict, "exit_code": code, "checked": len(unique), "findings": [asdict(f) for f in findings]}
    result["deployment"] = "nonproduction-demo"
    result["ghostcheck_version"] = __version__
    return 200, dict(HEADERS), json.dumps(result)


class handler(BaseHTTPRequestHandler):  # Vercel's Python runtime looks for this name
    def _send(self, method: str) -> None:
        status, headers, body = respond(method, self.path)
        data = body.encode("utf-8")
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if method != "HEAD":  # HEAD carries headers only
            self.wfile.write(data)

    def __getattr__(self, name: str):
        # BaseHTTPRequestHandler dispatches to do_<METHOD>; route every method (HEAD, OPTIONS, TRACE, ...) through
        # respond(), so anything but GET gets a JSON 405 instead of the base class's HTML 501 (Qodo on #58).
        if name.startswith("do_") and name[3:]:
            return lambda: self._send(name[3:])
        raise AttributeError(name)
