---
name: option-value-audit
description: Use when adding or changing support for a package manager's install command in ghostcheck/parsers.py, or when asked to audit one (pip, uv, pipx, poetry, pipenv, conda, npm, pnpm, yarn, bun). Checks that the value after every option that takes one (`--loglevel warn`, `--cwd app`) is never reported as a package.
---

# Option-value audit

ghostcheck has shipped the same bug twice: the value after an option was read as a package name (#26 for pip, #37 for npm, yarn, pnpm and bun). `npm i --loglevel warn react` reported `warn`. Because `warn`, `dev`, `app` and `silent` may exist on the registries, the finding looks real. This skill checks one package manager's options end to end, so the class of bug is caught before review instead of by it.

## Inputs (ask if missing)
- **The package manager** to audit (one of the names in `probe.py`'s `MANAGERS`). If the user names one that `probe.py` doesn't list, stop and ask whether to add it first.
- **Mode.** "Audit only" means: run steps 1-3, save the evidence, report, and stop before step 4. Otherwise go on to fix. If the request doesn't say, ask.
- **Where the option list comes from.** Prefer the tool's own help on this machine (`npm help install`, `pnpm add --help`, `yarn add --help`, `pip install --help`, `uv add --help`). Otherwise use its official CLI docs page. If neither is available, stop and ask for the list. Never guess options from memory.

## Steps
1. **Collect the options that take a value.** Read the help output and keep only options shown with a value placeholder (`--loglevel <level>`, `--cwd <dir>`, `-C, --dir <dir>`). Write them one per line to `audits/<manager>-options.txt`, with a first comment line naming the source and version. An option shown only as `--opt=<value>` still goes in the list (the probe tests both the `=` and the space form). If the help text says an option takes something but shows no placeholder (pnpm's `--allow-build`, `--global-dir`), list it in a `#` comment under "unclear", leave it out of the probes, and name it in your report so the owner can decide. If the options file or the evidence file already exists, overwrite it with this run's results and say in the report whether the counts changed. Booleans (`--save-dev`, `-D`, `--frozen-lockfile`) must not be listed: listing one would make the parser swallow the package after it.
2. **Run the probe:**
   ```bash
   python .claude/skills/option-value-audit/probe.py <manager> audits/<manager>-options.txt audits/<manager>-option-values.md
   ```
   For each option it checks `<cmd> <opt> VALUE pkg`, `<cmd> <opt>=VALUE pkg`, and, for npm, pnpm, yarn and bun, the option placed before the subcommand.
3. **If every probe passes:** check the "unclear" list from step 1 first. If it is empty, you are done: keep the evidence file and report the counts. If it is not empty, the audit is **incomplete, not passed**. Settle each unclear option from the tool's official docs (for pnpm, pnpm.io/cli/add), move the ones that take a value into the list, and re-run the probe. Ask the owner only for options you still can't settle.
4. **If probes fail:** follow AGENTS.md rule 2 (red test first):
   1. Add the failing commands as a parametrized test in `tests/test_parsers.py` and run it. It must fail on the current code.
   2. Add the missing options to the right table in `ghostcheck/parsers.py` (`_PIP_VALUE_FLAGS`, `_UV_PIPX_VALUE_FLAGS` or `_INSTALL_VALUE_FLAGS[...]`). The pre-subcommand and runner tables already share `_INSTALL_VALUE_FLAGS`.
   3. Run `python -m pytest -q`; every test must be green.
   4. Re-run the probe; it must now report 0 fails.
5. **Hand it to the factory's usual verification:** branch `ticket-<n>-<slug>`, open a PR with `Closes #n` mapping each acceptance criterion to its test, and wait for Qodo's review. Fix real findings (at most 2 rounds) before merging.

## Expected results
- Every probe returns exactly the real package (`left-pad` for npm-family, `requests` for Python ones). Two ways to fail:
  - **Extra package:** `sentinelvalue` is reported as well. This is a false alarm.
  - **Nothing reported:** the real package was never checked. This is worse: it is a fail-open (AGENTS.md rule 1). Report it first.
- `python -m pytest -q` passes.

## Evidence to save
- `audits/<manager>-options.txt`: the options and where they came from (first comment line, e.g. `# source: pnpm add --help, pnpm 10.x`).
- `audits/<manager>-option-values.md`: the probe table with counts.
- On fixes: the red test run, the green test run, and the PR link with Qodo's review result.

## Stop and ask when
- The manager isn't in `probe.py`, or its install subcommand differs from the one there.
- You can't get an authoritative option list (no help output and no docs).
- An option is a boolean in one tool and takes a value in another (pnpm `-w` is a boolean; npm `-w` takes a workspace). Ask which semantics to follow rather than guessing.
- A fix would change a table shared by several managers in a way that could break another manager's booleans.
