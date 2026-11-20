"""Issue #48: an agent uses ghostcheck for a real task over MCP, and the server's permissions hold."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio

from ghostcheck import mcp_server


async def _in_memory():
    from mcp.shared.memory import create_connected_server_and_client_session
    async with create_connected_server_and_client_session(mcp_server.server._mcp_server) as client:
        tools = (await client.list_tools()).tools
        resources = (await client.list_resources()).resources
        prompts = (await client.list_prompts()).prompts
        return tools, resources, prompts


def test_check_install_declares_read_only_permissions():
    tools, _, _ = anyio.run(_in_memory)
    ann = next(t for t in tools if t.name == "check_install").annotations
    assert ann is not None
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
    assert ann.idempotentHint is True
    assert ann.openWorldHint is True


def test_server_offers_only_the_check_tool():
    tools, resources, prompts = anyio.run(_in_memory)
    assert [t.name for t in tools] == ["check_install"]
    assert resources == [] and prompts == []


async def _stdio_task(tmp: Path, commands: list[str]):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, GHOSTCHECK_CACHE=str(tmp / "cache.json"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "ghostcheck.mcp_server"], env=env, cwd=str(tmp))
    out = []
    with anyio.fail_after(60):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for c in commands:
                    out.append(await session.call_tool("check_install", {"command": c, "offline": True}))
    return out


def test_agent_task_over_real_stdio_blocks_the_typo_and_runs_nothing(tmp_path):
    marker = tmp_path / "MARKER"
    run_me = f'pip install requests && {sys.executable} -c "open(r\'{marker}\', \'w\')"'
    task, sneaky = anyio.run(_stdio_task, tmp_path, ["pip install flask reqests", run_me])
    # Criterion 3: the user's task ("add flask and reqests") is not waved through.
    assert not task.isError
    assert task.structuredContent["verdict"] != "ok"
    assert any(f["package"] == "reqests" for f in task.structuredContent["findings"])
    # Criterion 4: checking a command never runs it.
    assert not sneaky.isError
    assert not marker.exists()
    # Criterion 5 (tightened after Qodo on #49): a read-only tool writes nothing, not even its cache.
    assert list(tmp_path.iterdir()) == []


def test_check_install_never_saves_the_cache(monkeypatch):
    saved = []
    monkeypatch.setattr(mcp_server.Registry, "save", lambda self: saved.append(1))
    mcp_server.check_install("pip install flask reqests", offline=True)
    assert saved == []


def _snapshot(root: Path) -> dict[str, tuple]:
    """Every entry under root: files by size + sha256, directories too (Qodo on #52: an empty new dir is a write)."""
    import hashlib
    return {
        p.relative_to(root).as_posix(): (
            ("file", p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()) if p.is_file() else ("dir",)
        )
        for p in sorted(root.rglob("*"))
    }


def _seed_warm_cache(path: Path) -> None:
    import json
    from dataclasses import asdict
    from ghostcheck.registry import PYPI, PackageInfo, cache_key
    entries = {}
    for name in ("flask", "requests"):
        info = PackageInfo(
            name, PYPI, True, first_release="2010-04-06T00:00:00Z", latest_release="2026-01-01T00:00:00Z",
            n_releases=60, maintainers=3, weekly_downloads=50_000_000, monthly_downloads=200_000_000,
            checked_at="2026-11-20T00:00:00Z",
        )
        entries[cache_key(name, PYPI)] = asdict(info)
    path.write_text(json.dumps(entries, indent=1, sort_keys=True), "utf-8")


def test_snapshot_sees_a_new_empty_directory(tmp_path):
    before = _snapshot(tmp_path)
    (tmp_path / "new-dir").mkdir()
    assert _snapshot(tmp_path) != before


def test_no_writes_on_cold_and_warm_cache(tmp_path):
    """Issue #51: same fixture twice, cold then warm cache; the filesystem is unchanged both times."""
    cache = tmp_path / "cache.json"
    fixture = ["pip install flask"]

    # Run 1: cold, no cache file exists.
    before = _snapshot(tmp_path)
    (cold,) = anyio.run(_stdio_task, tmp_path, fixture)
    assert _snapshot(tmp_path) == before == {}
    assert cold.structuredContent["verdict"] != "ok"  # offline cache miss fails closed

    # Run 2: warm, the cache is seeded before the call.
    _seed_warm_cache(cache)
    before = _snapshot(tmp_path)
    (warm,) = anyio.run(_stdio_task, tmp_path, fixture)
    assert list(before) == ["cache.json"]
    assert _snapshot(tmp_path) == before
    # The cache was really read: flask is only verifiable from the seeded entry.
    assert warm.structuredContent["verdict"] == "ok", warm.structuredContent
