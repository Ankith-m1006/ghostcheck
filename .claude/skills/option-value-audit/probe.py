"""Probe ghostcheck's parsers with every value-taking option of one package manager.

Usage:
    python .claude/skills/option-value-audit/probe.py <manager> <options-file> <evidence-file>

<manager>       one of: pip, uv, uv-pip, pipx, poetry, pipenv, conda, npm, pnpm, yarn, bun
<options-file>  one option per line that TAKES A VALUE, e.g. "--loglevel" (lines starting with # are skipped)
<evidence-file> Markdown file the results are written to

For every option it builds the probes below and checks that ghostcheck reports exactly the
real package, never the option's value:
    <cmd> <opt> VALUE realpkg          (value as the next word)
    <cmd> <opt>=VALUE realpkg          (long options only)
    <mgr> <opt> VALUE <sub> realpkg    (option before the subcommand; npm-family only)
Exit code 0 when every probe passes, 1 when any fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ghostcheck.parsers import parse_npm_command, parse_pip_command

# The install command for each manager, the parser that reads it, and whether the manager
# accepts global options before the subcommand (`npm --prefix x install pkg`).
MANAGERS = {
    "pip": ("pip install", parse_pip_command, None),
    "uv-pip": ("uv pip install", parse_pip_command, None),
    "uv": ("uv add", parse_pip_command, None),
    "pipx": ("pipx install", parse_pip_command, None),
    "poetry": ("poetry add", parse_pip_command, None),
    "pipenv": ("pipenv install", parse_pip_command, None),
    "conda": ("conda install", parse_pip_command, None),
    "npm": ("npm install", parse_npm_command, ("npm", "install")),
    "pnpm": ("pnpm add", parse_npm_command, ("pnpm", "add")),
    "yarn": ("yarn add", parse_npm_command, ("yarn", "add")),
    "bun": ("bun add", parse_npm_command, ("bun", "add")),
}
VALUE = "sentinelvalue"  # a lowercase word, so a parser bug reads it as a real-looking package name
REAL = {"npm": "left-pad", "py": "requests"}


def probes(manager: str, option: str) -> list[str]:
    cmd, _, split = MANAGERS[manager]
    real = REAL["npm"] if MANAGERS[manager][1] is parse_npm_command else REAL["py"]
    out = [f"{cmd} {option} {VALUE} {real}"]
    if option.startswith("--"):
        out.append(f"{cmd} {option}={VALUE} {real}")
    if split:
        out.append(f"{split[0]} {option} {VALUE} {split[1]} {real}")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in MANAGERS:
        print(__doc__)
        return 2
    manager, options_file, evidence_file = argv[1], Path(argv[2]), Path(argv[3])
    options = [ln.strip() for ln in options_file.read_text(encoding="utf-8").splitlines()
               if ln.strip() and not ln.strip().startswith("#")]
    if not options:
        print(f"{options_file}: no options to probe. Collect the value-taking options first (SKILL.md step 1); "
              "an empty list must never count as a passing audit.")
        return 2
    parser = MANAGERS[manager][1]
    real = REAL["npm"] if parser is parse_npm_command else REAL["py"]
    rows, failed = [], 0
    for option in options:
        for command in probes(manager, option):
            got = [d.name for d in parser(command)]
            ok = got == [real]
            failed += not ok
            rows.append(f"| `{command}` | `{real}` | `{', '.join(got) or '(nothing)'}` | {'PASS' if ok else 'FAIL'} |")
    total = len(rows)
    lines = [f"# Option-value audit: {manager}", "",
             f"{total} probes, {total - failed} pass, {failed} fail.", "",
             "| Command | Expected | Got | Result |", "| --- | --- | --- | --- |", *rows, ""]
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"{manager}: {total} probes, {total - failed} pass, {failed} fail -> {evidence_file}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
