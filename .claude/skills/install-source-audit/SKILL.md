---
name: install-source-audit
description: Use when changing how ghostcheck finds or reports files and paths that an install command reads but ghostcheck does not (`-r req.txt`, `-c`, `-e ./lib`, conda `--file`/`-f`), or how a positional file can cover one (cli.py load_inputs, parsers.py unread_install_sources*). Runs a matrix of install-source forms through the real CLI so a fail-open or a false alarm is caught before review.
---

# Install-source audit

Why this exists (Day 19, from Qodo's findings on PR #45): Qodo raised 8 findings on #45 over three review rounds, and every one was about a single install-source form being handled wrongly: conda `-f`, a conda channel read as a file, `cd sub &&`, `uv --directory sub`, an include already read, a conda explicit-spec list masked by a positional file, editable paths given file advice, and a source reported twice. Each round of fixes found the next form. The option-value audit skill covers option *values*, not install *sources*, so nothing listed the forms up front.

## Steps
1. If your change adds a new install-source form or manager, add a row to `CASES` in `probe.py` first (red first, AGENTS.md rule 2). Each row says which sources must be reported as "not read"; an empty list means nothing may be reported.
2. Run the matrix on your working tree:
   ```bash
   python .claude/skills/install-source-audit/probe.py . audits/install-source-main.md
   ```
   Exit 0 means every row passed.
3. On a FAIL, fix the code, not the row. A "fail-open" row is the most serious (AGENTS.md rule 1): an install source is never reported, so an unchecked file can pass. Change an expectation only if the tool's official docs show the row is wrong, and cite the doc in the row's comment.
4. Run `python -m pytest -q`, then open the PR as usual and wait for Qodo's review.

## Replaying a past commit
To check whether the matrix would have caught an old bug, run it against a detached worktree:
```bash
git worktree add --detach ../wt-<sha> <sha>
python .claude/skills/install-source-audit/probe.py ../wt-<sha> audits/install-source-replay-<sha>.md
git worktree remove ../wt-<sha>
```

## Evidence to save
- `audits/install-source-main.md`: the matrix on your change.
- For a bug fix, the failing matrix from before the fix.

## Limits
- The probe runs offline with a temp cache. It checks what is reported as "not read", not registry verdicts.
- It only knows the forms in `CASES`. A form nobody listed can still slip through, so add a row whenever a review finds a new one.
