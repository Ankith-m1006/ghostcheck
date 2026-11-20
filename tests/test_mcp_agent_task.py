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
    # Criterion 5: nothing written outside the cache file.
    assert {p.name for p in tmp_path.iterdir()} <= {"cache.json"}
