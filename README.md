# ghostcheck

Coding agents install whatever the model says. Sometimes the model invents a package that does not exist,
and whoever registers that name later gets code execution on your machine. ghostcheck checks a dependency
**before** it is installed.

```bash
pip install -e .
ghostcheck --pip "pip install reqests numpy"
ghostcheck --npm "npm install expresss"
ghostcheck requirements.txt package.json
```

It flags:
- **ghosts**: names PyPI or npm report as not found (an attacker could register them)
- **brand-new / unused** packages with squatter-like metadata
- **typosquats**: names one edit away from a popular package
- standard-library and Node built-in names are never counted as ghosts

`--json` gives machine-readable output; `--offline` uses bundled lists and the local cache only.

Exit codes, so an agent or CI step can gate the install:

| Code | Meaning |
|---|---|
| 0 | no HIGH finding (MEDIUM and INFO findings may still be reported) |
| 1 | at least one HIGH finding: do not install until reviewed |
| 2 | usage or input error |
| 3 | some packages could not be verified (registry unreachable, or offline with no cached entry). ghostcheck fails closed; pass `--allow-unverified` to accept that risk |

`--json` prints one object: `version` (the ghostcheck version that made the decision), `checked` (packages checked once each), `offline`, `exit_code`, `unverified` (packages that could not be verified), and `findings` (each with `severity`, `rule`, `package`, `ecosystem`, `message`, `source`).

## Why
Measured in our study of Gemma 4 coding agents ("Ghosts in the Loop", 2026): when a task names a library that
does not exist, the agent tries to install it in most episodes, and the install runs before any error is seen.
The install boundary is the place to check.

## Use it from a coding agent (MCP)
```bash
pip install "ghostcheck[mcp]"
ghostcheck-mcp        # stdio MCP server
```
One tool, `check_install(command, offline=false)`, reads every install in a command (same parsing as `--cmd`) and returns
`verdict` (`block`, `unverified`, `review`, `ok` or `no-install-found`), `exit_code`, `checked` and `findings`.
`no-install-found` means nothing was checked, not that the command is safe. A requirements file or editable path in
the command (`-r req.txt`, `-e ./lib`) is not read by the tool, so it is reported as not verified; check it with the CLI. An empty, non-string or over-long
`command`, or an argument the tool does not define, is rejected as an error.

Permissions: the tool is marked read-only (`readOnlyHint`, not destructive, idempotent, `openWorldHint` because it
reads the public PyPI and npm registries), so a client can let the agent call it without a prompt. It never runs the
command it checks, and it writes no files: it reads the cache the CLI keeps (`GHOSTCHECK_CACHE`) but never saves it. The server offers this one tool and
no resources or prompts. `tests/test_mcp_agent_task.py` runs a real agent task over stdio to prove it.

## Roadmap
This repository is built as a "software factory" for the Qodo hackathon: rules in `AGENTS.md`, tickets, agent-written
PRs reviewed by Qodo. Next: an approve / escalate gate for risky packages.

## License
MIT
