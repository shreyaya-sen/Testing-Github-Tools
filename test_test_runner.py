import textwrap
from analyzer import test_runner


def _project(tmp_path, tests):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "test_calc.py").write_text(textwrap.dedent(tests))
    return tmp_path


def test_discover_finds_tests_for_file(tmp_path):
    root = _project(tmp_path, "from calc import add\n\ndef test_a():\n    assert add(1, 1) == 2\n")
    found = test_runner.discover(str(root / "calc.py"), str(root))
    assert found["count"] == 1


def test_discover_reports_none(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    found = test_runner.discover(str(tmp_path / "calc.py"), str(tmp_path))
    assert found["count"] == 0


def test_run_reports_pass_and_failure(tmp_path):
    root = _project(tmp_path, "from calc import add\n\ndef test_ok():\n    assert add(1, 1) == 2\n\ndef test_bad():\n    assert add(1, 1) == 3\n")
    found = test_runner.discover(str(root / "calc.py"), str(root))
    result = test_runner.run_tests(found["files"], found["root"], total=found["count"])
    assert result["passed"] == 1 and result["failed"] == 1
    assert result["failed_ids"]
    assert result["problems"][0]["title"]
