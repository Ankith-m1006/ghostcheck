# AGENTS.md

Instructions for any coding agent (and any reviewer) working in this repository.

## What this is

ghostcheck checks a dependency **before** it is installed: names that do not exist on PyPI or npm (ghosts an attacker could register), brand-new or unused packages, and typosquats of popular packages. It reads `pip`/`npm`/`uv`/`pipx` commands, requirement files, `package.json`, and raw agent output (`--cmd`). It is a security tool: a wrong "looks fine" is worse than a noisy warning.

Layout:
- `ghostcheck/parsers.py`: turns commands and files into `Dependency` objects.
- `ghostcheck/registry.py`: every network lookup (PyPI, npm), with a JSON cache.
- `ghostcheck/rules.py`: findings and severities; `exit_code()` decides pass or fail.
- `ghostcheck/stdlib.py`, `ghostcheck/data/`: standard-library names, popular-package lists, the measured LLM-ghost list.
- `tests/`: pytest, no network.

## Setup and verify

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q                                 # must pass, offline, in seconds
ghostcheck --offline --pip "pip install reqests"    # smoke test: expect a typosquat finding
```

Every change must leave `python -m pytest -q` green. Do not open a PR with a failing or skipped test.

## Rules

1. **Fail closed.** If ghostcheck could not verify a package (registry unreachable, timeout, offline cache miss), it must never be reported as safe and must not exit 0 silently. Say "not verified" and let the caller decide. *Where:* `rules.py` (`check_dependency`, `exit_code`). *Why:* this tool sits in front of `pip install`; a network blip must not turn into "install anything".

2. **Red test first for every parser change.** Before changing `parsers.py`, add a test in `tests/test_parsers.py` that fails on the current code and shows the input that broke. Then fix. *Why:* on our first PR, the fix for four review findings introduced a fifth bug (an apostrophe in prose hid chained installs). Only a test written from the broken input would have caught it before review.

3. **Quotes are counted from the installer word, never from the start of the line.** When splitting a shell line on `;`, `&&`, `||`, `|`, ignore separators inside quotes that open at or after `pip`/`npm`/`uv`/`pipx`; if a quote never closes, fall back to a plain split. *Where:* `parsers.py` (`_segments`, `_split_line`). *Why:* agent output mixes prose ("don't") with commands; counting quotes from the line start hides real installs.

4. **Registry lookups go through `registry.py`; the only other network call is the opt-in `--explain`.** No module except `registry.py` may query PyPI or npm. `gemma.py` (used only by `--explain`) is the one other module allowed to reach the network, and a default run must never import or call it (a test enforces this). Every request has a timeout; `--offline` must never touch the network; registry results are cached. *Why:* agents run ghostcheck inside sandboxes and CI where the network is slow, metered or blocked, and tests must stay offline.

5. **Never flag the standard library or Node built-ins as ghosts.** Check `stdlib.py` before any "not found" finding. *Why:* `pip install json` style mistakes are common in agent output, and a false "ghost" on a built-in teaches users to ignore the tool.

6. **Pin exact versions.** Dependencies in `pyproject.toml` and `requirements*.txt` use `==`. *Why:* a supply-chain tool must not pull floating versions of its own dependencies.

7. **Compare package names by registry identity, everywhere.** For PyPI that is `normalize_pypi(name)` (PEP 503: case-insensitive, runs of `-_.` are one `-`); npm names are compared exactly. Use it for de-duplication, counting, caching and registry URLs. *Where:* `cli.py` (`load_dependencies`, summary counts), `registry.py` (`cache_key`, lookups), `rules.py`. *Why:* Qodo's review of #4 caught `Foo_Bar` and `foo-bar` counted as two unverified packages; the same mistake existed in input de-duplication (#5). Nobody had written this down, so every new code path re-made it.

## Pull requests

- One ticket per PR. Put the ticket link and its acceptance criteria in the PR body.
- Say what you tested and paste the test output summary.
- Keep the diff small; no drive-by refactors.
