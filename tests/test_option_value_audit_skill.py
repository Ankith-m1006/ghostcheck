import runpy
from pathlib import Path

PROBE = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "option-value-audit" / "probe.py"


def _main():
    return runpy.run_path(str(PROBE))["main"]


def test_empty_options_file_is_not_a_passing_audit(tmp_path):
    options = tmp_path / "options.txt"
    options.write_text("# source: nothing collected\n", encoding="utf-8")
    assert _main()(["probe.py", "pnpm", str(options), str(tmp_path / "out.md")]) == 2
    assert not (tmp_path / "out.md").exists()


def test_probe_fails_on_a_missing_option_and_passes_on_a_known_one(tmp_path):
    options = tmp_path / "options.txt"
    options.write_text("--loglevel\n--definitely-not-a-pnpm-option\n", encoding="utf-8")
    evidence = tmp_path / "out.md"
    assert _main()(["probe.py", "pnpm", str(options), str(evidence)]) == 1
    text = evidence.read_text(encoding="utf-8")
    assert "| `pnpm add --loglevel sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |" in text
    assert "FAIL" in text
