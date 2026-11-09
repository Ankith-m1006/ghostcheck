"""ghostcheck command line.

    ghostcheck requirements.txt
    ghostcheck package.json
    ghostcheck --pip "pip install a b"
    ghostcheck --npm "npm install a b"
    ghostcheck --cmd "uv add a && npm i b"   # any installer, or a whole block of agent output

Exit codes: 0 = no HIGH findings, 1 = at least one HIGH finding, 2 = usage / input error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .parsers import PYPI, Dependency, normalize_pypi, parse_npm_command, parse_package_json, parse_pip_command, parse_requirements
from .registry import Registry
from .rules import HIGH, INFO, MEDIUM, UNVERIFIED, Finding, check_dependency, exit_code


def default_cache_path() -> Path:
    base = os.environ.get("GHOSTCHECK_CACHE") or os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    p = Path(base)
    return p if p.suffix == ".json" else p / "ghostcheck" / "registry_cache.json"


def load_dependencies(args) -> list[Dependency]:
    deps: list[Dependency] = []
    if args.pip:
        deps += parse_pip_command(args.pip)
    if args.npm:
        deps += parse_npm_command(args.npm)
    if args.cmd:  # any shell command or agent output: every pip/uv/poetry/pipx and npm/yarn/pnpm/bun install in it
        deps += parse_pip_command(args.cmd, source="command") + parse_npm_command(args.cmd, source="command")
    for f in args.files:
        path = Path(f)
        text = path.read_text("utf-8")
        if path.name.endswith(".json"):
            deps += parse_package_json(text, source=path.name)
        else:
            deps += parse_requirements(text, source=path.name)
    # One check per registry identity across all inputs; the first source wins (AGENTS.md rule 7).
    seen: set[tuple[str, str]] = set()
    unique: list[Dependency] = []
    for d in deps:
        key = (d.ecosystem, normalize_pypi(d.name) if d.ecosystem == PYPI else d.name)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ghostcheck", description="Flag ghost / suspicious dependencies before you install them.")
    ap.add_argument("files", nargs="*", help="requirements*.txt or package.json files")
    ap.add_argument("--pip", metavar="CMD", help='a pip command, e.g. "pip install foo bar"')
    ap.add_argument("--npm", metavar="CMD", help='an npm command, e.g. "npm install foo"')
    ap.add_argument("--cmd", metavar="TEXT", help='any shell command(s) or agent output; checks every install in it, e.g. "uv add foo && npm i bar"')
    ap.add_argument("--offline", action="store_true", help="no network: bundled lists + cache only")
    ap.add_argument("--cache", metavar="PATH", help="registry cache file (default ~/.cache/ghostcheck/registry_cache.json)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--allow-unverified", action="store_true", help="exit 0 even if some packages could not be verified (default: exit 3)")
    ap.add_argument("--explain", action="store_true", help="add a plain-English paragraph written by Gemma (needs GEMINI_API_KEY)")
    ap.add_argument("--version", action="version", version=f"ghostcheck {__version__}")
    args = ap.parse_args(argv)

    if not (args.files or args.pip or args.npm or args.cmd):
        ap.print_usage(sys.stderr)
        print("ghostcheck: give a file, --pip, --npm or --cmd", file=sys.stderr)
        return 2
    try:
        deps = load_dependencies(args)
    except (OSError, ValueError) as exc:
        print(f"ghostcheck: {exc}", file=sys.stderr)
        return 2

    registry = Registry(cache_path=args.cache or default_cache_path(), offline=args.offline)
    findings: list[Finding] = []
    for dep in deps:
        found, _ = check_dependency(dep, registry)
        findings += found
    try:
        registry.save()
    except OSError:
        pass

    code = exit_code(findings, allow_unverified=args.allow_unverified)
    # Count registry identities, not spellings: Foo_Bar and foo-bar are one PyPI package.
    ident = lambda f: (f.ecosystem, normalize_pypi(f.package) if f.ecosystem == PYPI else f.package)
    unverified = len({ident(f) for f in findings if f.rule == UNVERIFIED})
    if args.json:
        print(json.dumps({"checked": len(deps), "offline": args.offline, "exit_code": code, "unverified": unverified,
                          "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        mode = " (offline)" if args.offline else ""
        print(f"ghostcheck {__version__}: checked {len(deps)} dependencies{mode}")
        order = {HIGH: 0, MEDIUM: 1, INFO: 2}
        for f in sorted(findings, key=lambda x: (order[x.severity], x.package)):
            where = f"  [{f.source}]" if f.source else ""
            print(f"  {f.severity:<6} {f.ecosystem}:{f.package}  {f.rule}: {f.message}{where}")
        highs = sum(f.severity == HIGH for f in findings)
        meds = sum(f.severity == MEDIUM for f in findings)
        tail = "  -> do not install until reviewed" if highs else ("  -> not verified: check them or pass --allow-unverified" if code == 3 else "")
        print(f"{highs} high, {meds} medium, {unverified} not verified" + tail)
    if args.explain and findings:
        from .explain import explain
        # Unverified packages are INFO findings but decide the exit code, so they are explained too.
        print("\n" + explain([f for f in findings if f.severity != INFO or f.rule == UNVERIFIED]))
    return code


if __name__ == "__main__":
    sys.exit(main())
