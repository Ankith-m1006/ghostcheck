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

# (id, positional files, flag, command, expected unread sources, expected checked count) - one row per
# install-source form. The checked count proves that a source treated as "already read" really had its packages
# checked (Qodo on #54): a row that suppresses a warning must also show the packages it claims to cover.
# Rows marked #45 replay the forms Qodo found one review round at a time on PR #45.
CASES = [
    ("pip-r", [], "--cmd", "pip install -r req.txt", ["req.txt"], 0),
    ("pip-r-joined", [], "--cmd", "pip install -rreq.txt", ["req.txt"], 0),
    ("pip-requirement-eq", [], "--pip", "pip install requests --requirement=req.txt", ["req.txt"], 1),
    ("pip-constraint", [], "--cmd", "pip install -c cons.txt requests", ["cons.txt"], 1),
    ("uv-editable", [], "--cmd", "uv pip install -e ./lib", ["./lib"], 0),
    ("conda-file-long", [], "--cmd", "conda install --file pk.txt", ["pk.txt"], 0),
    ("conda-file-short #45", [], "--cmd", "conda install -f pk.txt", ["pk.txt"], 0),
    ("conda-channel-not-a-file #45", [], "--cmd", "conda install -c conda-forge rdkit", [], 1),
    ("positional-covers-same-file", ["req.txt"], "--cmd", "pip install -r req.txt", [], 1),
    ("include-already-read #45", ["top.txt"], "--cmd", "pip install -r child.txt", [], 1),
    ("cd-points-elsewhere #45", ["req.txt"], "--cmd", "cd sub && pip install -r req.txt", ["req.txt"], 1),
    ("uv-directory-points-elsewhere #45", ["req.txt"], "--cmd", "uv --directory sub add -r req.txt", ["req.txt"], 1),
    ("conda-list-never-masked #45", ["specs.txt"], "--cmd", "conda install --file specs.txt", ["specs.txt"], 0),
    ("repeated-source-once #45", [], "--cmd", "pip install -r req.txt -r req.txt", ["req.txt"], 0),
]


def run_case(root: Path, files: list[str], flag: str, cmd: str) -> dict:
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
            doc = json.loads(out.stdout)
            findings = doc["findings"]
        except (ValueError, KeyError):
            return {"unread": ["<no JSON: exit %d %s>" % (out.returncode, out.stderr.strip()[-120:])],
                    "bad_advice": [], "checked": None, "exit": out.returncode, "json_exit": None}
        unread = [f for f in findings if "not read" in f["message"]]
        # an editable path is a folder: it must be labelled editable and never told to run `ghostcheck <file>`
        bad_advice = [f["package"] for f in unread if f["package"].rstrip("/\\").endswith("lib")
                      and ("editable" not in f["message"] or "ghostcheck <file>" in f["message"])]
        return {"unread": sorted(f["package"] for f in unread), "bad_advice": bad_advice,
                "checked": doc.get("checked"), "exit": out.returncode, "json_exit": doc.get("exit_code")}


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_ROOT
    evidence = Path(argv[2]) if len(argv) > 2 else None
    rows, fails = [], 0
    for cid, files, flag, cmd, want, want_checked in CASES:
        r = run_case(root, files, flag, cmd)
        got = r["unread"]
        # an unread source must fail closed: exit 3 from the process and the same code in the JSON (Qodo on #54)
        exit_ok = not want or (r["exit"] == 3 and r["json_exit"] == 3)
        if any(w not in got for w in want):
            why = "FAIL (fail-open: source never reported)"
        elif not exit_ok:
            why = f"FAIL (fail-open: reported but exit {r['exit']}, JSON exit_code {r['json_exit']})"
        elif r["checked"] != want_checked:
            why = f"FAIL (checked {r['checked']} packages, expected {want_checked})"
        elif r["bad_advice"]:
            why = "FAIL (editable path given file advice)"
        elif got != sorted(want):
            why = "FAIL (false alarm or duplicate)"
        else:
            why = "PASS"
        fails += why != "PASS"
        shown = " ".join(files + [flag, repr(cmd)])
        rows.append(f"| {cid} | `{shown}` | {want} | {got} | {r['checked']} | {r['exit']} | {why} |")
    table = ["| case | input | expected unread | got | checked | exit | result |", "|---|---|---|---|---|---|---|", *rows,
             "", f"{len(CASES) - fails}/{len(CASES)} pass, {fails} fail (root: {root.name})"]
    text = "\n".join(table)
    print(text)
    if evidence:
        evidence.write_text(text + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
