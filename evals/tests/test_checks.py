import pathlib

from evals.harness import checks


def _ws(tmp_path, **files):
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def test_file_glob(tmp_path):
    _ws(tmp_path, **{"workflow.py": "x=1"})
    r = checks.run_checks(tmp_path, [{"kind": "file_glob", "glob": "*.py"}])[0]
    assert r.passed
    r2 = checks.run_checks(tmp_path, [{"kind": "file_glob", "glob": "*.md"}])[0]
    assert not r2.passed


def test_python_parses_and_imports(tmp_path):
    _ws(tmp_path, **{"a.py": "import flyte\n@x.task\ndef f():\n    return 1\n"})
    assert checks.run_checks(tmp_path, [{"kind": "python_parses"}])[0].passed
    assert checks.run_checks(tmp_path, [{"kind": "python_imports", "module": "flyte"}])[0].passed
    assert not checks.run_checks(tmp_path, [{"kind": "python_imports", "module": "torch"}])[0].passed


def test_python_parses_fails_on_syntax_error(tmp_path):
    _ws(tmp_path, **{"bad.py": "def (:"})
    assert not checks.run_checks(tmp_path, [{"kind": "python_parses"}])[0].passed


def test_contains_and_not_contains(tmp_path):
    _ws(tmp_path, **{"m.py": "TaskEnvironment()\n@env.task\ndef g(): ..."})
    assert checks.run_checks(tmp_path, [{"kind": "contains_regex", "pattern": "@\\w+\\.task"}])[0].passed
    assert checks.run_checks(tmp_path, [{"kind": "not_contains_regex", "pattern": "ReusePolicy"}])[0].passed
    assert not checks.run_checks(tmp_path, [{"kind": "not_contains_regex", "pattern": "TaskEnvironment"}])[0].passed


def test_yaml_valid(tmp_path):
    _ws(tmp_path, **{"k.yaml": "kind: Cluster\nnodes: []\n"})
    assert checks.run_checks(tmp_path, [{"kind": "yaml_valid", "file_glob": "*.yaml"}])[0].passed
    _ws(tmp_path, **{"bad.yaml": "a: b: c: :::"})
    assert not checks.run_checks(tmp_path, [{"kind": "yaml_valid", "file_glob": "bad.yaml"}])[0].passed


def test_cmd_succeeds(tmp_path):
    assert checks.run_checks(tmp_path, [{"kind": "cmd_succeeds", "cmd": "true"}])[0].passed
    assert not checks.run_checks(tmp_path, [{"kind": "cmd_succeeds", "cmd": "false"}])[0].passed


def test_stub_called(tmp_path):
    (tmp_path / ".stublog").write_text("kind create cluster --name flyte\nhelm install foo\n")
    assert checks.run_checks(tmp_path, [{"kind": "stub_called", "pattern": "kind create cluster"}])[0].passed
    assert not checks.run_checks(tmp_path, [{"kind": "stub_called", "pattern": "terraform apply"}])[0].passed


def test_unknown_kind_is_failure_not_crash(tmp_path):
    r = checks.run_checks(tmp_path, [{"kind": "nope"}])[0]
    assert not r.passed and "unknown" in r.detail
