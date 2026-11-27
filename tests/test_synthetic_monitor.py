"""Issue #57: the synthetic monitor's assertions. Offline: the live endpoint is replaced by a fake fetch."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor import synthetic_check as mon

CHECKS = json.loads((Path(__file__).resolve().parents[1] / "monitor" / "checks.json").read_text("utf-8"))

BLOCK = {"verdict": "block", "exit_code": 1, "checked": 1, "deployment": "nonproduction-demo", "findings": [
    {"severity": "HIGH", "rule": "not-found", "package": "requestss", "ecosystem": "pypi",
     "message": "does not exist on PyPI (PyPI 404); anyone could register it", "source": "command"},
    {"severity": "MEDIUM", "rule": "typosquat", "package": "requestss", "ecosystem": "pypi",
     "message": "1 edit away from the popular package 'requests'", "source": "command"}]}
OK = {"verdict": "ok", "exit_code": 0, "checked": 1, "findings": [], "deployment": "nonproduction-demo"}
GOOD_HEADERS = {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"}


def fake(responses):
    """responses: command -> (status, headers, body) or an Exception; records calls."""
    calls = []

    def fetch(url, command):
        calls.append(command)
        r = responses[command]
        if isinstance(r, Exception):
            raise r
        return r

    fetch.calls = calls
    return fetch


def healthy():
    return fake({"pip install requestss": (200, GOOD_HEADERS, json.dumps(BLOCK)),
                 "pip install requests": (200, GOOD_HEADERS, json.dumps(OK))})


def test_the_real_checks_cover_the_typo_and_the_real_package():
    assert {c["command"] for c in CHECKS} == {"pip install requestss", "pip install requests"}


def test_healthy_deployment_passes():
    results = mon.run("https://demo", CHECKS, fetch=healthy(), retry_wait=0)
    assert all(r.ok for r in results), [r.problems for r in results]


def test_typo_reported_ok_fails():
    fetch = fake({"pip install requestss": (200, GOOD_HEADERS, json.dumps({**OK, "findings": []})),
                  "pip install requests": (200, GOOD_HEADERS, json.dumps(OK))})
    results = mon.run("https://demo", CHECKS, fetch=fetch, retry_wait=0)
    bad = [r for r in results if not r.ok]
    assert [r.command for r in bad] == ["pip install requestss"]
    assert any("verdict" in p for p in bad[0].problems)


def test_typo_without_either_finding_fails():
    """A block verdict for some other reason is not the capability we monitor."""
    other = {**BLOCK, "findings": [{"severity": "HIGH", "rule": "llm-ghost", "package": "requestss",
                                    "ecosystem": "pypi", "message": "x", "source": "command"}]}
    fetch = fake({"pip install requestss": (200, GOOD_HEADERS, json.dumps(other)),
                  "pip install requests": (200, GOOD_HEADERS, json.dumps(OK))})
    bad = [r for r in mon.run("https://demo", CHECKS, fetch=fetch, retry_wait=0) if not r.ok]
    assert len(bad) == 1 and any("finding" in p for p in bad[0].problems)


def test_typosquat_alone_is_enough_if_pypi_registers_the_name():
    only_typo = {**BLOCK, "findings": [BLOCK["findings"][1] | {"severity": "HIGH"}]}
    fetch = fake({"pip install requestss": (200, GOOD_HEADERS, json.dumps(only_typo)),
                  "pip install requests": (200, GOOD_HEADERS, json.dumps(OK))})
    assert all(r.ok for r in mon.run("https://demo", CHECKS, fetch=fetch, retry_wait=0))


def test_real_package_with_a_finding_fails():
    noisy = {**OK, "verdict": "unverified", "exit_code": 3, "findings": [
        {"severity": "INFO", "rule": "not-checked", "package": "requests", "ecosystem": "pypi",
         "message": "registry not checked (PyPI HTTP 503)", "source": "command"}]}
    fetch = fake({"pip install requestss": (200, GOOD_HEADERS, json.dumps(BLOCK)),
                  "pip install requests": (200, GOOD_HEADERS, json.dumps(noisy))})
    bad = [r for r in mon.run("https://demo", CHECKS, fetch=fetch, retry_wait=0) if not r.ok]
    assert [r.command for r in bad] == ["pip install requests"]


def test_homepage_style_200_with_html_fails():
    fetch = fake({c["command"]: (200, {"content-type": "text/html"}, "<html>ok</html>") for c in CHECKS})
    results = mon.run("https://demo", CHECKS, fetch=fetch, retry_wait=0)
    assert not any(r.ok for r in results)


def test_cached_response_fails():
    """A CDN-cached answer could hide a broken deployment, so no-store is part of the contract."""
    cached = {"content-type": "application/json", "cache-control": "public, max-age=3600"}
    fetch = fake({"pip install requestss": (200, cached, json.dumps(BLOCK)),
                  "pip install requests": (200, cached, json.dumps(OK))})
    assert not any(r.ok for r in mon.run("https://demo", CHECKS, fetch=fetch, retry_wait=0))


def test_not_labelled_nonproduction_fails():
    fetch = fake({"pip install requestss": (200, GOOD_HEADERS, json.dumps(BLOCK)),
                  "pip install requests": (200, GOOD_HEADERS, json.dumps({**OK, "deployment": "prod"}))})
    assert [r.command for r in mon.run("https://demo", CHECKS, fetch=fetch, retry_wait=0) if not r.ok] == [
        "pip install requests"]


def test_transport_error_is_retried_once_then_fails():
    fetch = fake({c["command"]: ConnectionError("down") for c in CHECKS})
    results = mon.run("https://demo", CHECKS, fetch=fetch, retry_wait=0)
    assert not any(r.ok for r in results)
    assert len(fetch.calls) == 2 * len(CHECKS)


def test_5xx_is_retried_once_and_can_recover():
    seq = iter([(502, {}, ""), (200, GOOD_HEADERS, json.dumps(OK))])
    fetch = lambda url, command: next(seq)
    check = [c for c in CHECKS if c["command"] == "pip install requests"]
    assert mon.run("https://demo", check, fetch=fetch, retry_wait=0)[0].ok


def test_assertion_failure_is_not_retried():
    fetch = fake({"pip install requests": (200, GOOD_HEADERS, json.dumps({**OK, "verdict": "block"}))})
    check = [c for c in CHECKS if c["command"] == "pip install requests"]
    assert not mon.run("https://demo", check, fetch=fetch, retry_wait=0)[0].ok
    assert len(fetch.calls) == 1


def test_canary_expectation_fails_against_a_healthy_deployment():
    canary = [{"name": "canary", "command": "pip install requests",
               "expect": {"verdict": "block", "exit_code": 1}}]
    fetch = fake({"pip install requests": (200, GOOD_HEADERS, json.dumps(OK))})
    assert not mon.run("https://demo", canary, fetch=fetch, retry_wait=0)[0].ok


def test_main_exit_code_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(mon, "http_fetch", healthy())
    report = tmp_path / "report.md"
    assert mon.main(["https://demo", "--report", str(report)]) == 0
    assert "PASS" in report.read_text("utf-8")
    bad = fake({c["command"]: (200, GOOD_HEADERS, json.dumps({**OK, "verdict": "x"})) for c in CHECKS})
    monkeypatch.setattr(mon, "http_fetch", bad)
    assert mon.main(["https://demo", "--report", str(report)]) == 1
    assert "FAIL" in report.read_text("utf-8")
