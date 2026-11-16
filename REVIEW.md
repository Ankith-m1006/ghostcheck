# Review guidance for ghostcheck

ghostcheck checks package names that AI agents are about to install. A wrong "safe" is the worst possible bug; a noisy warning is a small one. Review with that in mind.

## Product decisions the review must respect
1. **Fail closed.** If a package cannot be verified (network error, timeout, registry 5xx, unknown ecosystem), it must be reported as "not verified", never as OK or safe. Flag any code path that turns an error, timeout or empty response into a pass.
2. **Offline tests.** Tests must not touch the network. Registry calls are faked. Flag any new test that would make a real HTTP request.
3. **One finding per real package.** A command-line flag, a flag's value, a path, a URL or a version specifier must never be reported as a package name.

## What to look for
- **Sibling parsers.** When a change touches flag handling for one package manager, check the equivalent logic for every other manager in `ghostcheck/parsers.py` (pip, uv, poetry, npm, pnpm, yarn, bun). Report a manager that has the same gap, even if its code is not in the diff.
- **Red test first.** A parser fix should come with a test that fails without the fix. Point out a fix whose test would also pass on the old code.
- **Quoted and chained commands** (`&&`, `;`, `|`, backticks, `sudo`) must still be split correctly.

## Do not comment on
- Style, naming or docstring wording (the linter handles it).
- Type hints in tests.
- Suggestions to add logging or retries to the CLI output.
