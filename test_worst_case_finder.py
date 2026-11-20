from analyzer import worst_case_finder as w


def _write(tmp_path, body):
    path = tmp_path / "m.py"
    path.write_text(body)
    return str(path)


def test_finds_crash_on_empty_list(tmp_path):
    f = _write(tmp_path, "def average(xs):\n    return sum(xs) / len(xs)\n")
    result = w.find_worst_cases(f, on_event=lambda e: None)
    assert any(x["kind"] == "crash" for x in result["findings"])


def test_clean_function_has_no_findings(tmp_path):
    f = _write(tmp_path, "def double(n):\n    return n * 2\n")
    result = w.find_worst_cases(f, on_event=lambda e: None)
    assert result["findings"] == []


def test_skips_file_writers(tmp_path):
    f = _write(tmp_path, "def save(x):\n    open('o.txt', 'w').write(str(x))\n")
    listing = w.list_functions(f)
    assert listing["runnable"] == 0


def test_syntax_error_reported(tmp_path):
    f = _write(tmp_path, "def broken(:\n")
    assert w.list_functions(f).get("syntax_error")
