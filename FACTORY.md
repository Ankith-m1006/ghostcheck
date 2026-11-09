# The factory loop

How a ticket becomes a merged change in this repo without a person writing code.

## Trigger

A scheduled job checks the backlog (GitHub Issues) every 30 minutes, 08:00 to 23:00 IST. It picks the **oldest open issue labelled `ready-for-agent`** that has no open PR yet. One ticket at a time.

```bash
gh issue list --label ready-for-agent --state open --json number,title --jq 'sort_by(.number) | .[0]'
```

Only small, clear tickets get the label: one behaviour, written acceptance criteria. Anything vague stays unlabelled.

## The job

1. **Read** the ticket (title, body, acceptance criteria) and `AGENTS.md`.
2. **Branch** `ticket-<n>-<slug>` from `main`.
3. **Red test first** (rule 2): add the test that shows the ticket's behaviour and confirm it fails on `main`.
4. **Implement** the smallest change that makes it pass.
5. **Check**: `python -m pytest -q` must be green.
6. **Open a PR** with `Closes #<n>`, the acceptance criteria mapped to tests, and the test summary.
7. **Qodo reviews** the PR automatically.
8. **Fix** every finding that is a real bug, each with a red test, and push. Qodo re-reviews.
9. **Retry limit: 2 fix rounds.** If findings remain after two rounds, or the tests cannot be made green, or the ticket turns out to be unclear: stop, label the issue `needs-human`, and comment what was tried and what is blocking. No guessing.
10. **A person merges.** The agent never merges its own PR unless the owner has said so for that PR.

## What the agent may not do

- Change `AGENTS.md` rules or this file inside a ticket PR (rule changes get their own PR).
- Add a dependency without pinning it (rule 6).
- Touch the network in tests (rule 4).
- Work on more than one ticket at a time.

## Log

Each run adds one line to the PR description: ticket, rounds used, final review state.
