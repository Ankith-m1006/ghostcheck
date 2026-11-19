"""Issue #41: the check_install MCP tool. Offline only: every call uses offline=True or an empty cache."""
import anyio
import pytest

from ghostcheck import cli
from ghostcheck import mcp_server
from ghostcheck.mcp_server import MAX_COMMAND_CHARS, check_install


@pytest.fixture(autouse=True)
def empty_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "default_cache_path", lambda: tmp_path / "cache.json")


def test_known_ghost_blocks():
    out = check_install("npm install number-to-words-indian", offline=True)
    assert out["verdict"] == "block" and out["exit_code"] == 1
    assert out["checked"] == 1
    assert any(f["package"] == "number-to-words-indian" and f["severity"] == "HIGH" for f in out["findings"])


def test_offline_typosquat_is_flagged_and_not_ok():
    out = check_install("pip install reqests", offline=True)
    assert out["verdict"] == "unverified"
    assert any(f["rule"] == "typosquat" for f in out["findings"])


def test_offline_cache_miss_is_unverified_never_ok():
    out = check_install("pip install some-real-looking-package-xyz", offline=True)
    assert out["verdict"] == "unverified" and out["exit_code"] == 3
    assert out["verdict"] != "ok"


def test_medium_only_is_review():
    out = check_install("pip install json", offline=True)
    assert out["verdict"] == "review" and out["exit_code"] == 0
    assert [f["rule"] for f in out["findings"]] == ["builtin-install"]


def test_no_install_is_not_ok():
    out = check_install("ls -la && echo done", offline=True)
    assert out == {"verdict": "no-install-found", "exit_code": 0, "checked": 0, "findings": []}


def test_mixed_pip_and_npm_in_one_command():
    out = check_install("pip install reqests && npm i expresss", offline=True)
    assert out["checked"] == 2
    assert {f["ecosystem"] for f in out["findings"]} >= {"pypi", "npm"}


@pytest.mark.parametrize("bad", ["", "   ", "\n"])
def test_empty_command_rejected(bad):
    with pytest.raises(ValueError, match="command"):
        check_install(bad)


def test_non_string_command_rejected():
    with pytest.raises(ValueError, match="command"):
        check_install(["pip", "install", "x"])  # type: ignore[arg-type]


def test_overlong_command_rejected_before_any_lookup(monkeypatch):
    called = []
    monkeypatch.setattr(mcp_server, "Registry", lambda *a, **k: called.append(1))
    with pytest.raises(ValueError, match=str(MAX_COMMAND_CHARS)):
        check_install("pip install a " + "x" * MAX_COMMAND_CHARS)
    assert called == []


async def _over_protocol(arguments):
    from mcp.shared.memory import create_connected_server_and_client_session
    async with create_connected_server_and_client_session(mcp_server.server._mcp_server) as client:
        tools = (await client.list_tools()).tools
        result = await client.call_tool("check_install", arguments)
        return tools, result


def test_tool_is_discoverable_and_matches_direct_call():
    tools, result = anyio.run(_over_protocol, {"command": "pip install reqests", "offline": True})
    tool = next(t for t in tools if t.name == "check_install")
    assert "command" in tool.inputSchema["properties"] and tool.inputSchema["required"] == ["command"]
    assert not result.isError
    assert result.structuredContent == check_install("pip install reqests", offline=True)


@pytest.mark.parametrize("arguments", [{}, {"command": ""}, {"command": 42}, {"command": "pip install x", "surprise": 1}])
def test_invalid_calls_over_protocol_are_errors(arguments):
    _, result = anyio.run(_over_protocol, arguments)
    assert result.isError


# Qodo review on #42, finding 1: an offline cache miss on a popular package is still unverified (AGENTS.md rule 1).
@pytest.mark.parametrize("command", ["pip install requests", "npm i express"])
def test_popular_package_offline_is_unverified_not_ok(command):
    out = check_install(command, offline=True)
    assert out["verdict"] == "unverified" and out["exit_code"] == 3


# Qodo review on #42, finding 2: a requirements file named in the command is not read, so it cannot pass as ok.
@pytest.mark.parametrize("command", ["pip install -r requirements.txt json", "pip install json --requirement=dev.txt",
                                     "uv pip install -r req.txt json", "pip install -e . json"])
def test_unread_install_source_makes_it_unverified(command):
    out = check_install(command, offline=True)
    assert out["verdict"] == "unverified" and out["exit_code"] == 3
    assert any(f["rule"] == "not-checked" and "not read" in f["message"] for f in out["findings"])


def test_only_a_requirements_file_is_unverified_not_no_install():
    out = check_install("pip install -r requirements.txt", offline=True)
    assert out["verdict"] == "unverified" and out["checked"] == 0
