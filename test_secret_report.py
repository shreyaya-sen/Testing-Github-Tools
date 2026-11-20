"""Tests for the friendly secret report."""

import json
import textwrap

from analyzer.secret_report import scan_report

KEY = "gsk_" + "a1B2c3D4e5F6g7H8i9J0k1L2"

SOURCE = textwrap.dedent(f'''
    import os

    GROQ_API_KEY = "{KEY}"
    db_password = "hunter2hunter2"
    safe = os.environ["TOKEN"]
    note = "password: your-password-here"
''')


def test_clean_file_has_no_findings_and_counts_lines():
    result = scan_report("x = 1\ny = 2\n", "a.py")

    assert result["count"] == 0
    assert result["lines_checked"] == 2
    assert result["tip"] is None
    assert result["file"] == "a.py"


def test_findings_have_plain_names_lines_and_reasons():
    result = scan_report(SOURCE, "demo.py")
    names = [item["title"] for item in result["findings"]]

    assert result["count"] == 2
    assert names == ["Groq API key", "Password"]
    assert [item["line"] for item in result["findings"]] == [4, 5]
    assert all(item["why"] for item in result["findings"])


def test_real_values_never_appear_in_the_report():
    text = json.dumps(scan_report(SOURCE, "demo.py"))

    assert KEY not in text
    assert "hunter2hunter2" not in text


def test_placeholders_are_not_flagged():
    assert scan_report('password = "your-password-here"\n')["count"] == 0


def test_tip_uses_the_real_variable_name():
    result = scan_report(f'api_key = "{KEY}"\n')

    assert 'api_key = os.environ["API_KEY"]' in result["tip"]["example"]
    assert "new one" in result["tip"]["text"]


def test_password_tip_does_not_claim_exposure():
    result = scan_report('db_password = "hunter2hunter2"\n')

    assert "change the password" in result["tip"]["text"]
    assert 'db_password = os.environ["DB_PASSWORD"]' in result["tip"]["example"]


def test_private_key_gets_a_file_based_example():
    result = scan_report("-----BEGIN RSA PRIVATE KEY-----\n")

    assert result["findings"][0]["title"] == "Private key"
    assert "PRIVATE_KEY_PATH" in result["tip"]["example"]


def test_many_findings_are_flagged_for_the_ui():
    assert scan_report(SOURCE)["tip"]["more"] is True
