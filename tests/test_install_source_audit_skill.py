import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / ".claude" / "skills" / "install-source-audit" / "probe.py"


def test_install_source_matrix_passes_on_this_tree(tmp_path):
    evidence = tmp_path / "matrix.md"
    probe = runpy.run_path(str(PROBE))
    assert probe["main"](["probe.py", str(ROOT), str(evidence)]) == 0
    n = len(probe["CASES"])
    text = evidence.read_text(encoding="utf-8")
    assert "FAIL" not in text
    assert f"{n}/{n} pass" in text
