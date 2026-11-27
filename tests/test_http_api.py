"""Issue #57: the read-only HTTP check behind the Day 20 synthetic monitor. Offline: every request goes to FakeNet."""
from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from api import check as api
from ghostcheck import cli, mcp_server
from ghostcheck.registry import Registry


def call(net, command=None, method="GET", budget=api.TIME_BUDGET_S, raw_query=None):
    query = raw_query if raw_query is not None else ("" if command is None else "command=" + quote(command))
    status, headers, body = api.respond(method, "/api/check?" + query, fetcher=net, budget_s=budget)
    return status, headers, json.loads(body)


@pytest.fixture
def registry_net(net):
    net.pypi("requests", [4000, 30, 10], monthly=900_000_000)
    return net


def test_typo_blocks_with_not_found(registry_net):
    status, _, out = call(registry_net, "pip install requestss")
    assert status == 200
    assert out["verdict"] == "block" and out["exit_code"] == 1 and out["checked"] == 1
    assert any(f["package"] == "requestss" and f["rule"] == "not-found" and f["severity"] == "HIGH"
               for f in out["findings"])
    assert any(f["rule"] == "typosquat" and "requests" in f["message"] for f in out["findings"])


def test_real_package_is_clean(registry_net):
    status, _, out = call(registry_net, "pip install requests")
    assert status == 200
    assert (out["verdict"], out["exit_code"], out["checked"], out["findings"]) == ("ok", 0, 1, [])


def test_response_is_labelled_nonproduction_and_never_cached(registry_net):
    _, headers, out = call(registry_net, "pip install requests")
    assert out["deployment"] == "nonproduction-demo"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Type"].startswith("application/json")


@pytest.mark.parametrize("command", [
    "pip install requestss",
    "pip install requests",
    "pip install json",
    "pip install -r req.txt requests",
    "pip install reqests && npm i expresss",
    "ls -la && echo done",
])
def test_same_verdict_as_the_mcp_tool(registry_net, monkeypatch, tmp_path, command):
    """The HTTP path and check_install must never drift apart: same fake registry, same answer."""
    monkeypatch.setattr(cli, "default_cache_path", lambda: tmp_path / "cache.json")
    monkeypatch.setattr(mcp_server, "Registry", lambda cache_path=None, offline=False: Registry(
        cache_path=cache_path, offline=offline, fetcher=registry_net, min_interval=0))
    expected = mcp_server.check_install(command)
    _, _, out = call(registry_net, command)
    out.pop("deployment"), out.pop("ghostcheck_version")
    assert out == expected


def test_never_writes_a_cache(registry_net, monkeypatch, tmp_path):
    monkeypatch.setenv("GHOSTCHECK_CACHE", str(tmp_path / "cache.json"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(Registry, "save", lambda self: pytest.fail("the HTTP check must not save a cache"))
    call(registry_net, "pip install requestss requests")
    assert list(tmp_path.iterdir()) == []


def test_spent_time_budget_is_unverified_never_ok(registry_net):
    status, _, out = call(registry_net, "pip install requests", budget=0)
    assert status == 200
    assert out["verdict"] == "unverified" and out["exit_code"] == 3
    assert registry_net.calls == []


def test_registry_error_is_not_retried_and_fails_closed():
    calls = []

    def flaky(url, method="GET", headers=None):
        calls.append(url)
        return 503, None

    status, _, out = call(flaky, "pip install requests")
    assert status == 200 and out["verdict"] == "unverified" and out["exit_code"] == 3
    assert len(calls) == 1  # no retry sleeps inside a serverless time limit


def test_network_exception_fails_closed():
    def down(url, method="GET", headers=None):
        raise ConnectionError("no route")

    _, _, out = call(down, "pip install requests")
    assert out["verdict"] == "unverified" and out["exit_code"] == 3


@pytest.mark.parametrize("query", ["", "command=", "command=%20%20", "other=1", "command=a&command=b"])
def test_bad_query_is_400(net, query):
    status, _, out = call(net, raw_query=query)
    assert status == 400 and "command" in out["error"]
    assert net.calls == []


def test_too_long_is_413(net):
    status, _, out = call(net, "pip install " + "a" * api.MAX_COMMAND_CHARS)
    assert status == 413 and "error" in out
    assert net.calls == []


def test_too_many_packages_is_400(net):
    names = " ".join(f"pkg{i}" for i in range(api.MAX_PACKAGES + 1))
    status, _, out = call(net, "pip install " + names)
    assert status == 400 and str(api.MAX_PACKAGES) in out["error"]
    assert net.calls == []


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_other_methods_are_405(net, method):
    status, headers, out = call(net, "pip install requests", method=method)
    assert status == 405 and headers["Allow"] == "GET"
    assert net.calls == []


def test_live_fetcher_uses_registry_transport_with_a_short_timeout(monkeypatch):
    """Rule 4: the HTTP check reaches PyPI only through registry.py, and each request is capped."""
    import requests

    seen = {}

    class FakeSession:
        headers: dict = {}

        def request(self, method, url, headers=None, timeout=None):
            seen["timeout"] = timeout
            raise requests.ConnectionError("offline test")

    monkeypatch.setattr(requests, "Session", FakeSession)
    _, _, out = call(None, "pip install requests")
    assert seen["timeout"] == api.REQUEST_TIMEOUT_S
    assert out["verdict"] == "unverified"


class _Captured:
    def __init__(self):
        import io
        self.status, self.headers, self.wfile = None, {}, io.BytesIO()


def _drive_handler(method: str, monkeypatch, net):
    """Run the real handler class the way BaseHTTPRequestHandler dispatches: getattr(self, 'do_' + method)."""
    cap = _Captured()
    h = api.handler.__new__(api.handler)
    h.path, h.command, h.wfile = "/api/check?command=pip+install+requests", method, cap.wfile
    h.send_response = lambda code, message=None: setattr(cap, "status", code)
    h.send_header = lambda k, v: cap.headers.__setitem__(k, v)
    h.end_headers = lambda: None
    real = api.respond
    monkeypatch.setattr(api, "respond", lambda m, p: real(m, p, fetcher=net))
    getattr(h, "do_" + method)()
    return cap


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS", "TRACE", "CONNECT", "PROPFIND", "POST"])
def test_every_non_get_method_gets_json_405_from_the_handler(method, monkeypatch, net):
    """Qodo on #58: HEAD and OPTIONS fell through to BaseHTTPRequestHandler's HTML 501."""
    cap = _drive_handler(method, monkeypatch, net)
    assert cap.status == 405 and cap.headers["Allow"] == "GET"
    assert cap.headers["Content-Type"].startswith("application/json")
    body = cap.wfile.getvalue()
    if method == "HEAD":
        assert body == b""  # HEAD carries headers only
    else:
        assert "error" in json.loads(body)
    assert net.calls == []


def test_handler_get_writes_the_json_verdict(monkeypatch, net):
    net.pypi("requests", [4000, 30, 10], monthly=900_000_000)
    cap = _drive_handler("GET", monkeypatch, net)
    assert cap.status == 200 and json.loads(cap.wfile.getvalue())["verdict"] == "ok"
    assert cap.headers["Content-Length"] == str(len(cap.wfile.getvalue()))
