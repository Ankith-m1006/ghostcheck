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
| 0 | nothing found |
| 1 | at least one HIGH finding: do not install until reviewed |
| 2 | usage error |
| 3 | some packages could not be verified (registry unreachable, or offline with no cached entry). ghostcheck fails closed; pass `--allow-unverified` to accept that risk |

## Why
Measured in our study of Gemma 4 coding agents ("Ghosts in the Loop", 2026): when a task names a library that
does not exist, the agent tries to install it in most episodes, and the install runs before any error is seen.
The install boundary is the place to check.

## Roadmap
This repository is built as a "software factory" for the Qodo hackathon: rules in `AGENTS.md`, tickets, agent-written
PRs reviewed by Qodo. Next: an MCP server so coding agents can ask ghostcheck before installing, and an
approve / escalate gate for risky packages.

## License
MIT
