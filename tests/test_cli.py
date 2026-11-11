import json
import os
from pathlib import Path

import pytest

import ghostcheck.registry as registry_mod
from ghostcheck import cli
from ghostcheck.rules import UNVERIFIED, exit_code


@pytest.fixture
def fake_network(monkeypatch, net):
    net.pypi("requests", [4000] + [100] * 30)
    net.pypi("flask", [4000] + [100] * 30)
    net.npm("express-tiny-helper", created_days_ago=1500, weekly=200, versions=12)
    monkeypatch.setattr(registry_mod, "_requests_fetcher", lambda: net)
    monkeypatch.setattr(registry_mod.time, "sleep", lambda s: None)
    return net


def run(args, tmp_path):
    return cli.main(args + ["--cache", str(tmp_path / "c.json")])


def test_clean_requirements_exit_0(fake_network, tmp_path, capsys):
    req = tmp_path / "requirements.txt"
    req.write_text("requests==2.32.0\nflask\n")
    assert run([str(req)], tmp_path) == 0
    assert "0 high" in capsys.readouterr().out


def test_ghost_in_requirements_exit_1(fake_network, tmp_path, capsys):
    req = tmp_path / "requirements.txt"
    req.write_text("requests\nupi-qr-generator-pro\n")
    assert run([str(req)], tmp_path) == 1
    out = capsys.readouterr().out
    assert "HIGH" in out and "upi-qr-generator-pro" in out and "not-found" in out


def test_package_json(fake_network, tmp_path, capsys):
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"dependencies": {"express-tiny-helper": "^1", "gstin-validator-xyz": "1.0.0"}}))
    assert run([str(pkg)], tmp_path) == 1
    assert "gstin-validator-xyz" in capsys.readouterr().out


def test_pip_flag(fake_network, tmp_path):
    assert run(["--pip", "pip install requests flask"], tmp_path) == 0
    assert run(["--pip", "pip install requests no-such-pkg-here"], tmp_path) == 1


def test_cmd_flag_checks_every_installer_in_agent_output(fake_network, tmp_path):
    agent_output = "uv add requests\nthen: npm i express-tiny-helper && pipx install no-such-pkg-here"
    assert run(["--cmd", agent_output], tmp_path) == 1
    assert run(["--cmd", "uv add requests && npm i express-tiny-helper"], tmp_path) == 0


def test_npm_flag(fake_network, tmp_path):
    assert run(["--npm", "npm i express-tiny-helper"], tmp_path) == 0


def test_json_output(fake_network, tmp_path, capsys):
    assert run(["--pip", "pip install no-such-pkg-here", "--json"], tmp_path) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["exit_code"] == 1 and data["findings"][0]["rule"] == "not-found"


def test_usage_errors_exit_2(tmp_path, capsys):
    assert cli.main([]) == 2
    assert cli.main([str(tmp_path / "missing.txt")]) == 2
    bad = tmp_path / "package.json"
    bad.write_text("{oops")
    assert cli.main([str(bad)]) == 2


def test_offline_mode_uses_cache_and_bundled_lists_only(monkeypatch, tmp_path, net, capsys):
    # first, an online run fills the cache
    net.pypi("requests", [4000] + [100] * 30)
    monkeypatch.setattr(registry_mod, "_requests_fetcher", lambda: net)
    assert run(["--pip", "pip install requests"], tmp_path) == 0

    def no_network():
        raise AssertionError("offline mode must not create a network client")
    monkeypatch.setattr(registry_mod, "_requests_fetcher", no_network)
    # cached name -> clean; typo of a top package -> MEDIUM from the bundled list; unknown -> INFO only
    code = run(["--offline", "--pip", "pip install requests reqeusts some-unknown-thing"], tmp_path)
    out = capsys.readouterr().out
    assert code == 3  # issue #3: the unknown name could not be verified, so it does not pass
    assert "typosquat" in out and "offline" in out
    assert "not-found" not in out  # offline cannot prove a 404


def test_default_run_never_calls_a_model(fake_network, tmp_path, monkeypatch):
    import ghostcheck.gemma as gemma

    class Forbidden:
        def __init__(self, *a, **k):
            raise AssertionError("model used without --explain")
    monkeypatch.setattr(gemma, "Gemma", Forbidden)
    assert run(["--pip", "pip install no-such-pkg-here"], tmp_path) == 1


def test_explain_only_describes_existing_findings(fake_network, tmp_path, monkeypatch, capsys):
    import ghostcheck.explain as explain

    seen = {}

    class FakeGemma:
        def __init__(self, key, min_interval=0):
            pass

        def generate(self, model, prompt, **kw):
            seen["prompt"] = prompt
            return {"text": "This package does not exist; do not install it."}
    monkeypatch.setattr(explain, "Gemma", FakeGemma)
    monkeypatch.setattr(explain, "load_key", lambda *a: "test-key")
    code = run(["--pip", "pip install no-such-pkg-here", "--explain"], tmp_path)
    assert code == 1  # exit code comes from the rules, not the model
    assert "no-such-pkg-here" in seen["prompt"] and "do not invent" in seen["prompt"]
    assert "do not install it" in capsys.readouterr().out


def test_unreachable_registry_fails_closed(monkeypatch, tmp_path, capsys):
    """Issue #3: a package nobody could verify must not pass silently."""
    class Down:
        def __call__(self, url, method="GET", headers=None):
            raise ConnectionError("registry unreachable")
    monkeypatch.setattr(registry_mod, "_requests_fetcher", lambda: Down())
    monkeypatch.setattr(registry_mod.time, "sleep", lambda s: None)
    assert run(["--pip", "pip install some-unknown-thing"], tmp_path) == 3
    assert "not verified" in capsys.readouterr().out


def test_high_beats_unverified_and_allow_flag(monkeypatch, tmp_path, capsys, net):
    net.pypi("requests", [4000] + [100] * 30)
    monkeypatch.setattr(registry_mod, "_requests_fetcher", lambda: net)
    monkeypatch.setattr(registry_mod.time, "sleep", lambda s: None)
    run(["--pip", "pip install requests"], tmp_path)  # fill the cache
    # offline: one cached clean, one unknown -> 3; with --allow-unverified -> 0
    assert run(["--offline", "--pip", "pip install requests some-unknown-thing"], tmp_path) == 3
    assert run(["--offline", "--allow-unverified", "--pip", "pip install requests some-unknown-thing"], tmp_path) == 0
    out = capsys.readouterr()
    assert run(["--offline", "--json", "--pip", "pip install some-unknown-thing"], tmp_path) == 3
    data = json.loads(capsys.readouterr().out)
    assert data["exit_code"] == 3 and data["unverified"] == 1


def test_unverified_count_uses_registry_identity(monkeypatch, tmp_path, capsys):
    """Qodo review of #4: Foo_Bar and foo-bar are one PyPI package, so one unverified package."""
    req = tmp_path / "requirements.txt"
    req.write_text("Foo_Bar\nfoo-bar\n")
    assert run(["--offline", "--json", str(req)], tmp_path) == 3
    assert json.loads(capsys.readouterr().out)["unverified"] == 1


def _network_down(url, method="GET", headers=None):
    raise OSError("network unreachable")


def test_explain_mentions_unverified_packages(monkeypatch, tmp_path, capsys):
    """Qodo review of #4: an unverified-only run must not print 'No findings'.
    Unverified here because the registry is unreachable (not --offline, which must not call the explainer, #10)."""
    import ghostcheck.explain as explain_mod
    seen = {}
    monkeypatch.setattr(registry_mod, "_requests_fetcher", lambda: _network_down)
    monkeypatch.setattr(registry_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(explain_mod, "explain", lambda fs, *a, **k: seen.setdefault("rules", [f.rule for f in fs]) and "ok")
    assert run(["--explain", "--pip", "pip install some-unknown-thing"], tmp_path) == 3
    assert seen["rules"] == ["not-checked"]
    assert "No findings" not in capsys.readouterr().out


def test_offline_explain_never_calls_the_explainer(monkeypatch, tmp_path, capsys):
    """Issue #10 (AGENTS.md rule 4): --offline must never touch the network, --explain included."""
    import ghostcheck.explain as explain_mod

    def no_network(*a, **k):
        raise AssertionError("--offline --explain called the explainer (network)")

    monkeypatch.setattr(explain_mod, "explain", no_network)
    assert run(["--offline", "--explain", "--json", "--pip", "pip install some-unknown-thing"], tmp_path) == 3
    captured = capsys.readouterr()
    assert json.loads(captured.out)["exit_code"] == 3  # stdout stays valid JSON
    assert "skipped" in captured.err.lower() and "offline" in captured.err.lower()


def test_each_package_checked_once_across_inputs(fake_network, tmp_path, capsys):
    """Issue #5 (AGENTS.md rule 7): one registry identity, one check, whatever the spelling or input."""
    fake_network.npm("flask", created_days_ago=1500, weekly=200, versions=12)
    req = tmp_path / "requirements.txt"
    req.write_text("Flask\nflask\n")
    assert run(["--json", str(req), "--pip", "pip install FLASK requests", "--npm", "npm i flask"], tmp_path) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checked"] == 3  # pypi:flask, pypi:requests, npm:flask


def test_duplicate_keeps_the_file_and_line_source(fake_network, tmp_path, capsys):
    """Qodo review of #6: a package in a file and in --pip is reported at its file line, not as "pip command"."""
    req = tmp_path / "requirements.txt"
    req.write_text("requests\nno-such-pkg-here\n")
    assert run(["--json", str(req), "--pip", "pip install no-such-pkg-here"], tmp_path) == 1
    data = json.loads(capsys.readouterr().out)
    assert [f["source"] for f in data["findings"] if f["rule"] == "not-found"] == ["requirements.txt:2"]


def test_json_reports_the_ghostcheck_version(fake_network, tmp_path, capsys):
    """Issue #8: CI keeps the JSON, so it must say which version made the decision."""
    from ghostcheck import __version__
    assert run(["--json", "--pip", "pip install requests"], tmp_path) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["version"] == __version__
    assert {"checked", "offline", "exit_code", "unverified", "findings"} <= set(data)  # nothing else changed


def test_version_has_a_single_source():
    """Issue #8: pyproject.toml must read the version from ghostcheck.__version__, not hard-code a second copy."""
    import pathlib
    import re
    text = (pathlib.Path(__file__).parent.parent / "pyproject.toml").read_text("utf-8")
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]  # plain text, so it runs on Python 3.10 (no tomllib)
    assert not re.search(r"^version\s*=", project, re.M)
    assert re.search(r'^dynamic\s*=\s*\[[^\]]*"version"', project, re.M)
    assert re.search(r'^version\s*=\s*\{\s*attr\s*=\s*"ghostcheck.__version__"\s*\}', text.split("[tool.setuptools.dynamic]", 1)[1], re.M)


def test_requirements_includes_are_followed(tmp_path):
    # Issue #15, criteria 1 and 2: -r / --requirement / --requirement= are followed, relative to the including file.
    (tmp_path / "sub").mkdir()
    (tmp_path / "base.txt").write_text("requests==2.31.0\n", "utf-8")
    (tmp_path / "sub" / "dev.txt").write_text("\npytest\n", "utf-8")
    (tmp_path / "extra.txt").write_text("flask\n", "utf-8")
    top = tmp_path / "requirements.txt"
    top.write_text("-r base.txt\n--requirement sub/dev.txt\n--requirement=extra.txt\nnumpy\n", "utf-8")

    class A:
        files = [str(top)]
        pip = npm = cmd = None

    deps = {d.name: d.source for d in cli.load_dependencies(A())}
    assert deps == {"numpy": "requirements.txt:4", "requests": "base.txt:1", "pytest": "sub/dev.txt:2", "flask": "extra.txt:1"}


def _args(path):
    class A:
        files = [str(path)]
        pip = npm = cmd = None
    return A()


def test_requirements_include_cycles_are_read_once(tmp_path):
    # Issue #15 criterion 3 (Qodo finding on #16): cycles and repeated includes must not loop or re-read.
    (tmp_path / "a.txt").write_text("-r b.txt\n-r a.txt\nrequests\n", "utf-8")
    (tmp_path / "b.txt").write_text("-r a.txt\nflask\n", "utf-8")
    top = tmp_path / "requirements.txt"
    top.write_text("-r a.txt\n-r b.txt\n", "utf-8")
    deps, problems = cli.load_inputs(_args(top))
    assert sorted(d.name for d in deps) == ["flask", "requests"]
    assert problems == []


def test_unreadable_includes_fail_closed(tmp_path):
    # Issue #15 criterion 4 (Qodo finding on #16): a missing or undecodable include is "not checked", so exit 3.
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe\x00not utf-8")
    top = tmp_path / "requirements.txt"
    top.write_text("-r missing.txt\n--requirement=bad.txt\nnumpy\n", "utf-8")
    deps, problems = cli.load_inputs(_args(top))
    assert [d.name for d in deps] == ["numpy"]
    assert [(p.rule, p.source) for p in problems] == [(UNVERIFIED, "requirements.txt:1"), (UNVERIFIED, "requirements.txt:2")]
    assert "missing.txt" in problems[0].message and "bad.txt" in problems[1].message
    assert exit_code(problems) == 3


def test_symlink_loop_include_fails_closed(tmp_path, monkeypatch):
    # Qodo finding on #16 (0442d8e): Path.resolve() on a looping symlink raises RuntimeError before Python 3.13.
    # Simulated so the test runs on every OS (Windows needs admin rights to create symlinks).
    real_resolve = cli.Path.resolve

    def resolve(self, *a, **k):
        if self.name == "loop.txt":
            raise RuntimeError("Symlink loop from 'loop.txt'")
        return real_resolve(self, *a, **k)

    monkeypatch.setattr(cli.Path, "resolve", resolve)
    top = tmp_path / "requirements.txt"
    top.write_text("-r loop.txt\nnumpy\n", "utf-8")
    deps, problems = cli.load_inputs(_args(top))
    assert [d.name for d in deps] == ["numpy"]
    assert [(p.rule, p.source) for p in problems] == [(UNVERIFIED, "requirements.txt:1")]
    assert "RuntimeError" in problems[0].message


def test_include_sources_keep_their_relative_path(tmp_path):
    # Issue #17: same file name in two folders must not print the same source; ../ stays relative.
    for d in ("a", "b", "proj"):
        (tmp_path / d).mkdir()
    (tmp_path / "a" / "dev.txt").write_text("flask\n", "utf-8")
    (tmp_path / "b" / "dev.txt").write_text("pytest\n", "utf-8")
    (tmp_path / "shared.txt").write_text("requests\n", "utf-8")
    top = tmp_path / "proj" / "requirements.txt"
    top.write_text("-r ../a/dev.txt\n-r ../b/dev.txt\n-r ../shared.txt\n-r gone.txt\n", "utf-8")
    deps, problems = cli.load_inputs(_args(top))
    assert {d.name: d.source for d in deps} == {"flask": "../a/dev.txt:1", "pytest": "../b/dev.txt:1", "requests": "../shared.txt:1"}
    assert [p.source for p in problems] == ["requirements.txt:4"]


def test_include_on_another_drive_uses_absolute_path_exception(tmp_path, monkeypatch):
    # Qodo local review of #17: os.path.relpath raises ValueError across Windows drives.
    # No relative path exists then, so the label falls back to the absolute path with / separators.
    real_relpath = cli.os.path.relpath

    def relpath(path, start=None):
        if Path(path).name == "other-drive.txt":
            raise ValueError("path is on mount 'D:', start on mount 'C:'")
        return real_relpath(path, start)

    monkeypatch.setattr(cli.os.path, "relpath", relpath)
    (tmp_path / "other-drive.txt").write_text("flask\n", "utf-8")
    top = tmp_path / "requirements.txt"
    top.write_text("-r other-drive.txt\nnumpy\n", "utf-8")
    deps, problems = cli.load_inputs(_args(top))
    assert {d.name: d.source for d in deps} == {"numpy": "requirements.txt:2", "flask": (tmp_path / "other-drive.txt").as_posix() + ":1"}
    assert problems == []
