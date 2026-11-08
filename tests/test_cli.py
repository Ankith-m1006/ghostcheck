import json

import pytest

import ghostcheck.registry as registry_mod
from ghostcheck import cli


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


def test_explain_mentions_unverified_packages(monkeypatch, tmp_path, capsys):
    """Qodo review of #4: an unverified-only run must not print 'No findings'."""
    import ghostcheck.explain as explain_mod
    seen = {}
    monkeypatch.setattr(explain_mod, "explain", lambda fs, *a, **k: seen.setdefault("rules", [f.rule for f in fs]) and "ok")
    assert run(["--offline", "--explain", "--pip", "pip install some-unknown-thing"], tmp_path) == 3
    assert seen["rules"] == ["not-checked"]
    assert "No findings" not in capsys.readouterr().out
