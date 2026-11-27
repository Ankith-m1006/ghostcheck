"""Install-source matrix: does every way an install can name a file or path end in exactly one honest result?

Usage: python probe.py [REPO_ROOT] [EVIDENCE.md]
REPO_ROOT defaults to this repository; pass an older checkout (git worktree) to replay a past commit.
Exit 0 when every case passes, 1 when any case fails.

Each case runs the real CLI (`python -m ghostcheck --offline --json`) in a fresh temp folder and compares the
"install source not read" findings with what the case expects. A missing finding is a fail-open (AGENTS.md rule 1);
an extra or doubled one is a false alarm.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
DEFAULT_ROOT = HERE.parents[3]

# files every case gets: a top-level requirements file that includes child.txt, a different req.txt in sub/,
# a conda package list, an explicit conda spec file and a local project folder
FILES = {
    "req.txt": "requests\n",
    "top.txt": "-r child.txt\n",
    "child.txt": "requests\n",
    "cons.txt": "urllib3<3\n",
    "sub/req.txt": "requests\n",
    "pk.txt": "numpy\n",
    "specs.txt": "@EXPLICIT\nhttps://conda.anaconda.org/conda-forge/noarch/six-1.16.0-pyh6c4a22f_0.tar.bz2\n",
    "lib/pyproject.toml": "[project]\nname = 'lib'\n",
}

# (id, positional files, flag, command, expected unread sources) - one row per install-source form.
# Rows marked #45 replay the forms Qodo found one review round at a time on PR #45.
CASES = [
    ("pip-r", [], "--cmd", "pip install -r req.txt", ["req.txt"]),
    ("pip-r-joined", [], "--cmd", "pip install -rreq.txt", ["req.txt"]),
    ("pip-requirement-eq", [], "--pip", "pip install requests --requirement=req.txt", ["req.txt"]),
    ("pip-constraint", [], "--cmd", "pip install -c cons.txt requests", ["cons.txt"]),
    ("uv-editable", [], "--cmd", "uv pip install -e ./lib", ["./lib"]),
    ("conda-file-long", [], "--cmd", "conda install --file pk.txt", ["pk.txt"]),
    ("conda-file-short #45", [], "--cmd", "conda install -f pk.txt", ["pk.txt"]),
    ("conda-channel-not-a-file #45", [], "--cmd", "conda install -c conda-forge rdkit", []),
    ("positional-covers-same-file", ["req.txt"], "--cmd", "pip install -r req.txt", []),
    ("include-already-read #45", ["top.txt"], "--cmd", "pip install -r child.txt", []),
    ("cd-points-elsewhere #45", ["req.txt"], "--cmd", "cd sub && pip install -r req.txt", ["req.txt"]),
    ("uv-directory-points-elsewhere #45", ["req.txt"], "--cmd", "uv --directory sub add -r req.txt", ["req.txt"]),
    ("conda-list-never-masked #45", ["specs.txt"], "--cmd", "conda install --file specs.txt", ["specs.txt"]),
    ("repeated-source-once #45", [], "--cmd", "pip install -r req.txt -r req.txt", ["req.txt"]),
]


def run_case(root: Path, files: list[str], flag: str, cmd: str) -> tuple[list[str], list[str]]:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name, text in FILES.items():
            p = work / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(root))
        argv = [sys.executable, "-m", "ghostcheck", *files, flag, cmd, "--offline", "--json",
                "--cache", str(work / "cache.json")]
        out = subprocess.run(argv, cwd=work, env=env, capture_output=True, text=True, timeout=120)
        try:
            findings = json.loads(out.stdout)["findings"]
        except (ValueError, KeyError):
            return ["<no JSON: exit %d %s>" % (out.returncode, out.stderr.strip()[-120:])], []
        unread = [f for f in findings if "not read" in f["message"]]
        bad_advice = [f["package"] for f in unread if f["message"].find("editable") == -1
                      and f["package"].rstrip("/\\").endswith("lib")]
        return sorted(f["package"] for f in unread), bad_advice


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_ROOT
    evidence = Path(argv[2]) if len(argv) > 2 else None
    rows, fails = [], 0
    for cid, files, flag, cmd, want in CASES:
        got, bad_advice = run_case(root, files, flag, cmd)
        ok = got == sorted(want) and not bad_advice
        if not ok:
            if any(w not in got for w in want):
                why = "FAIL (fail-open: source never reported)"
            elif bad_advice:
                why = "FAIL (editable path told to run ghostcheck <file>)"
            else:
                why = "FAIL (false alarm or duplicate)"
            fails += 1
        else:
            why = "PASS"
        shown = " ".join(files + [flag, repr(cmd)])
        rows.append(f"| {cid} | `{shown}` | {want} | {got} | {why} |")
    table = ["| case | input | expected unread | got | result |", "|---|---|---|---|---|", *rows,
             "", f"{len(CASES) - fails}/{len(CASES)} pass, {fails} fail (root: {root.name})"]
    text = "\n".join(table)
    print(text)
    if evidence:
        evidence.write_text(text + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
