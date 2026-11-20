import pytest

from analyzer.data_cleaner import clean_csv
from analyzer.hygiene import check_hygiene
from analyzer.repo_scan import analyze_repo

SAMPLE_CSV = (
    "name,age,city\n"
    "Asha,21,Pune\n"
    "Asha,21,Pune\n"
    " Ravi ,25,Mumbai\n"
    ",,\n"
    "Meera,,Delhi\n"
    "Ravi,25,Mumbai\n"
)

HYGIENE_SOURCE = (
    "import os\n"
    "import sys\n"
    "\n"
    "\n"
    "def total(items):\n"
    "    unused = 1\n"
    "    result = 0\n"
    "    for x in items:\n"
    "        result += sorted(items)[0] + x\n"
    "    return result\n"
    "\n"
    "\n"
    "def grow(items):\n"
    "    out = []\n"
    "    for x in items:\n"
    "        out.append(x)\n"
    "        if len(out) > 3:\n"
    "            break\n"
    "    return out\n"
)


def test_hygiene_finds_expected_issues():
    result = check_hygiene(HYGIENE_SOURCE)
    categories = [item["category"] for item in result["findings"]]

    assert categories.count("unused_import") == 2
    assert categories.count("unused_variable") == 1
    assert categories.count("loop_invariant_call") == 1

    invariant = next(
        item for item in result["findings"]
        if item["category"] == "loop_invariant_call"
    )

    assert invariant["function"] == "total"


def test_hygiene_can_skip_import_check():
    assert check_hygiene("import os\n", check_imports=False)["count"] == 0


def test_hygiene_clean_code_has_no_findings():
    assert check_hygiene("def add(a, b):\n    return a + b\n")["count"] == 0


def test_clean_csv_report(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(SAMPLE_CSV, encoding="utf-8")

    result = clean_csv(path)

    assert result["rows_in"] == 6
    assert result["rows_out"] == 3
    assert result["duplicates_removed"] == 2
    assert result["empty_rows_removed"] == 1
    assert result["missing_by_column"]["age"] == 1
    assert result["output_file"] is None


def test_clean_csv_can_drop_rows_with_missing_values(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(SAMPLE_CSV, encoding="utf-8")

    result = clean_csv(path, drop_missing=True)

    assert result["rows_out"] == 2
    assert result["rows_dropped_missing"] == 1


def test_clean_csv_writes_a_new_file_and_keeps_the_original(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(SAMPLE_CSV, encoding="utf-8")
    before = path.read_bytes()

    result = clean_csv(path, write=True)

    assert result["output_file"].endswith("data.cleaned.csv")
    assert path.read_bytes() == before


def test_analyze_repo_skips_hidden_folders(tmp_path):
    (tmp_path / "app.py").write_text("import os\n", encoding="utf-8")
    hidden = tmp_path / ".venv"
    hidden.mkdir()
    (hidden / "lib.py").write_text("import sys\n", encoding="utf-8")

    result = analyze_repo(tmp_path)

    assert result["files_scanned"] == 1
    assert any(
        item["category"] == "unused_import" for item in result["findings"]
    )


def test_analyze_repo_needs_python_files(tmp_path):
    with pytest.raises(ValueError):
        analyze_repo(tmp_path)