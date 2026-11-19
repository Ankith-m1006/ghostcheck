"""ghostcheck as an MCP tool, so a coding agent can ask before it installs (issue #41).

    pip install "ghostcheck[mcp]"
    ghostcheck-mcp            # stdio server with one tool: check_install
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from . import cli
from .parsers import PYPI, normalize_pypi, parse_npm_command, parse_pip_command, unread_install_sources
from .registry import Registry
from .rules import INFO, MEDIUM, UNVERIFIED, Finding, check_dependency, exit_code

MAX_COMMAND_CHARS = 20_000
VERDICTS = {0: "ok", 1: "block", 3: "unverified"}

server = FastMCP("ghostcheck")


def check_install(command: str, offline: bool = False) -> dict[str, Any]:
    """Check every package install in `command` (pip/uv/pipx/poetry/conda, npm/yarn/pnpm/bun) before running it.

    verdict: "block" (a HIGH finding: do not install), "unverified" (some package could not be checked: fail closed),
    "review" (MEDIUM findings only), "ok", or "no-install-found" (nothing to check: not a statement that it is safe).
    """
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must be a non-empty string, e.g. 'pip install requests'")
    if len(command) > MAX_COMMAND_CHARS:
        raise ValueError(f"command is longer than {MAX_COMMAND_CHARS} characters; send one install at a time")
    deps = parse_pip_command(command, source="command") + parse_npm_command(command, source="command")
    # One check per registry identity (AGENTS.md rule 7).
    seen: set[tuple[str, str]] = set()
    unique = []
    for d in deps:
        key = (d.ecosystem, normalize_pypi(d.name) if d.ecosystem == PYPI else d.name)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    # A requirements file or editable path is installed too, but this tool does not read files (Qodo on #42).
    findings = [Finding(INFO, UNVERIFIED, src, "", f"install source not read: '{src}'; check it with the ghostcheck CLI", "command")
                for src in unread_install_sources(command)]
    if not unique and not findings:
        return {"verdict": "no-install-found", "exit_code": 0, "checked": 0, "findings": []}
    registry = Registry(cache_path=cli.default_cache_path(), offline=offline)
    for dep in unique:
        findings += check_dependency(dep, registry)[0]
    try:
        registry.save()
    except OSError:
        pass
    code = exit_code(findings)
    verdict = VERDICTS[code]
    if verdict == "ok" and any(f.severity == MEDIUM for f in findings):
        verdict = "review"
    return {"verdict": verdict, "exit_code": code, "checked": len(unique), "findings": [asdict(f) for f in findings]}


server.tool(name="check_install", structured_output=True)(check_install)
# Reject arguments the tool does not define instead of silently ignoring them (issue #41, criterion 4).
server._tool_manager.get_tool("check_install").fn_metadata.arg_model.model_config = ConfigDict(extra="forbid")
server._tool_manager.get_tool("check_install").fn_metadata.arg_model.model_rebuild(force=True)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
