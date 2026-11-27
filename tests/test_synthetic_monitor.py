"""Issue #57: the synthetic monitor's assertions. Offline: monitor/fetch.sh (curl, in the workflow) saves the live
responses to a folder; these tests write that folder by hand. The Python side never touches the network (rule 4)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor import synthetic_check as mon

ROOT = Path(__file__).resolve().parents[1]
CHECKS = json.loads((ROOT / "monitor" / "checks.json").read_text("utf-8"))

BLOCK = {"verdict": "block", "exit_code": 1, "checked": 1, "deployment": "nonproduction-demo", "findings": [
    {"severity": "HIGH", "rule": "not-found", "package": "requestss", "ecosystem": "pypi",
     "message": "does not exist on PyPI (PyPI 404); anyone could register it", "source": "command"},
    {"severity": "MEDIUM", "rule": "typosquat", "package": "requestss", "ecosystem": "pypi",
     "message": "1 edit away from the popular package 'requests'", "source": "command"}]}
OK = {"verdict": "ok", "exit_code": 0, "checked": 1, "findings": [], "deployment": "nonproduction-demo"}
GOOD_HEADERS = "Content-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\n"


def save(folder: Path, i: int, body, status="200 0.80", headers=GOOD_HEADERS, first_line="HTTP/1.1 200 OK"):
    """Write what monitor/fetch.sh writes for check number i: <i>.status, <i>.headers, <i>.body."""
    folder.mkdir(exist_ok=True)
    (folder / f"{i}.status").write_text(status, "utf-8")
    (folder / f"{i}.headers").write_bytes(f"{first_line}\r\n{headers}\r\n".encode())  # curl writes CRLF as is
    (folder / f"{i}.body").write_text(body if isinstance(body, str) else json.dumps(body), "utf-8")


def responses(tmp_path, typo_body=BLOCK, real_body=OK, **kw):
    folder = tmp_path / "responses"
    for i, check in enumerate(CHECKS):
        save(folder, i, typo_body if check["command"] == "pip install requestss" else real_body, **kw)
    return folder


def failing(results):
    return [r.command for r in results if not r.ok]


def test_the_real_checks_cover_the_typo_and_the_real_package():
    assert [c["command"] for c in CHECKS] == ["pip install requestss", "pip install requests"]


def test_healthy_deployment_passes(tmp_path):
    results = mon.run(CHECKS, responses(tmp_path))
    assert all(r.ok for r in results), [r.problems for r in results]
    assert results[0].seconds == 0.8


def test_typo_reported_ok_fails(tmp_path):
    results = mon.run(CHECKS, responses(tmp_path, typo_body={**OK}))
    assert failing(results) == ["pip install requestss"]
    assert any("verdict" in p for p in results[0].problems)


def test_typo_without_either_finding_fails(tmp_path):
    """A block verdict for some other reason is not the capability we monitor."""
    other = {**BLOCK, "findings": [{"severity": "HIGH", "rule": "llm-ghost", "package": "requestss",
                                    "ecosystem": "pypi", "message": "x", "source": "command"}]}
    results = mon.run(CHECKS, responses(tmp_path, typo_body=other))
    assert failing(results) == ["pip install requestss"]
    assert any("finding" in p for p in results[0].problems)


def test_typosquat_alone_is_enough_if_pypi_registers_the_name(tmp_path):
    only_typo = {**BLOCK, "findings": [BLOCK["findings"][1] | {"severity": "HIGH"}]}
    assert failing(mon.run(CHECKS, responses(tmp_path, typo_body=only_typo))) == []


def test_real_package_with_a_finding_fails(tmp_path):
    noisy = {**OK, "verdict": "unverified", "exit_code": 3, "findings": [
        {"severity": "INFO", "rule": "not-checked", "package": "requests", "ecosystem": "pypi",
         "message": "registry not checked (PyPI HTTP 503)", "source": "command"}]}
    assert failing(mon.run(CHECKS, responses(tmp_path, real_body=noisy))) == ["pip install requests"]


@pytest.mark.parametrize("findings", [[None], [None, "x", 3], ["not-an-object"]])
def test_malformed_findings_fail_with_a_report_not_a_crash(tmp_path, findings):
    """Qodo on #58: a non-object finding must be a reported problem, not an exception that loses the report."""
    results = mon.run(CHECKS, responses(tmp_path, typo_body={**BLOCK, "findings": findings},
                                        real_body={**OK, "findings": findings}))
    assert failing(results) == ["pip install requestss", "pip install requests"]
    assert all(any("not an object" in p for p in r.problems) for r in results)
    assert "FAIL" in mon.report("https://demo", results)


def test_homepage_style_200_with_html_fails(tmp_path):
    folder = responses(tmp_path, typo_body="<html>ok</html>", real_body="<html>ok</html>",
                       headers="Content-Type: text/html\r\nCache-Control: no-store\r\n")
    assert len(failing(mon.run(CHECKS, folder))) == 2


def test_cached_response_fails(tmp_path):
    """A CDN-cached answer could hide a broken deployment, so no-store is part of the contract."""
    folder = responses(tmp_path, headers="Content-Type: application/json\r\nCache-Control: public, max-age=3600\r\n")
    assert len(failing(mon.run(CHECKS, folder))) == 2


def test_not_labelled_nonproduction_fails(tmp_path):
    folder = responses(tmp_path, real_body={**OK, "deployment": "prod"})
    assert failing(mon.run(CHECKS, folder)) == ["pip install requests"]


def test_http_error_and_no_response_fail(tmp_path):
    folder = tmp_path / "responses"
    save(folder, 0, "", status="502 1.2", first_line="HTTP/1.1 502 Bad Gateway")
    (folder / "1.status").write_text("000 40.0", "utf-8")  # curl could not connect: no headers, no body
    results = mon.run(CHECKS, folder)
    assert len(failing(results)) == 2
    assert "HTTP 502" in results[0].problems[0] and "no response" in results[1].problems[0]


def test_missing_response_files_fail(tmp_path):
    results = mon.run(CHECKS, tmp_path / "never-written")
    assert len(failing(results)) == 2


def test_only_the_last_header_block_counts(tmp_path):
    """curl -D keeps a redirect's or a retried attempt's headers too; the final response decides."""
    folder = responses(tmp_path)
    for i in range(len(CHECKS)):
        h = folder / f"{i}.headers"
        h.write_bytes(b"HTTP/1.1 503 Service Unavailable\r\nCache-Control: public\r\n\r\n" + h.read_bytes())
    assert failing(mon.run(CHECKS, folder)) == []


def test_canary_expectation_fails_against_a_healthy_deployment(tmp_path):
    canary = [{"name": "canary", "command": "pip install requests", "expect": {"verdict": "block", "exit_code": 1}}]
    folder = tmp_path / "responses"
    save(folder, 0, OK)
    assert failing(mon.run(canary, folder)) == ["pip install requests"]


def test_main_exit_code_and_report(tmp_path):
    report = tmp_path / "report.md"
    args = ["--target", "https://demo", "--responses", str(responses(tmp_path)), "--report", str(report)]
    assert mon.main(args) == 0 and "PASS" in report.read_text("utf-8")
    (tmp_path / "b").mkdir()
    bad = responses(tmp_path / "b", typo_body={**OK})
    assert mon.main(["--target", "https://demo", "--responses", str(bad), "--report", str(report)]) == 1
    assert "FAIL" in report.read_text("utf-8")


def test_monitor_code_has_no_network_client():
    """Rule 4: only registry.py (and the opt-in gemma.py) may reach the network from Python."""
    src = (ROOT / "monitor" / "synthetic_check.py").read_text("utf-8")
    for client in ("import requests", "urllib.request", "http.client", "import socket", "httpx"):
        assert client not in src


def test_fetch_script_retries_once_and_caps_time():
    sh = (ROOT / "monitor" / "fetch.sh").read_text("utf-8")
    assert "--retry 1" in sh and "--max-time" in sh and "--data-urlencode" in sh
