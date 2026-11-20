"""Regression tests for test-suggestion coverage detection."""

import textwrap

import pytest

from analyzer.test_advisor import advise_tests

AGE_SOURCE = textwrap.dedent('''
    def calculate_age(age):
        if age < 0 or age > 120:
            raise ValueError("Invalid age")
        elif age >= 18:
            return "Adult"
        else:
            return "Minor"
''')

AGE_VALUES = [-1, 0, 1, 119, 120, 121, 17, 18, 19]


def make_project(tmp_path, source=AGE_SOURCE, tests=None, name="calc.py"):
    """Create a project. `tests` maps relative test paths to source text."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    source_path = tmp_path / name
    source_path.write_text(source)

    for relative, text in (tests or {}).items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(text))

    return source_path


def run(tmp_path, source=AGE_SOURCE, tests=None, name="calc.py"):
    path = make_project(tmp_path, source, tests, name)
    return advise_tests(path.read_text(), file_path=str(path))


def direct_tests(values, module="calc", func="calculate_age"):
    body = "\n".join(
        f"def test_case_{index}():\n    {func}({value!r})\n"
        for index, value in enumerate(values)
    )
    return f"from {module} import {func}\n\n{body}"


def counts(result):
    return result["suggested"], result["covered"], result["missing"]


def covered_inputs(result):
    return sorted(
        next(iter(s["input"].values()))
        for fn in result["functions"]
        for s in fn["suggestions"]
        if s["covered"]
    )


# ---------------------------------------------------------------- the example


def test_all_nine_calculate_age_suggestions_are_recognised(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": direct_tests(AGE_VALUES),
    })

    assert counts(result) == (9, 9, 0)
    assert result["coverage"]["covered"] == 9


def test_five_of_nine_gives_five_covered_four_missing(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": direct_tests([-1, 0, 119, 120, 18]),
    })

    assert counts(result) == (9, 5, 4)
    assert covered_inputs(result) == [-1, 0, 18, 119, 120]


def test_no_tests_gives_zero_of_nine(tmp_path):
    result = run(tmp_path)

    assert counts(result) == (9, 0, 9)
    assert result["coverage_status"] == "available"


def test_per_function_counts_match_the_totals(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": direct_tests([-1, 0]),
    })

    function = result["functions"][0]
    assert function["covered_count"] == 2
    assert function["missing_count"] == 7
    assert result["covered"] == sum(f["covered_count"] for f in result["functions"])


# ---------------------------------------------------------------- test styles


def test_parametrized_tests_are_recognised(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": """
            import pytest
            from calc import calculate_age

            @pytest.mark.parametrize("age", [-1, 0, 1, 119, 120, 121, 17, 18, 19])
            def test_age(age):
                calculate_age(age)
        """,
    })

    assert counts(result) == (9, 9, 0)


def test_parametrize_with_pytest_param_constants_and_raises(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": """
            import pytest
            from calc import calculate_age

            BAD = [-1, 121]

            @pytest.mark.parametrize("age", BAD)
            def test_invalid(age):
                with pytest.raises(ValueError):
                    calculate_age(age)

            @pytest.mark.parametrize(
                "age, expected",
                [
                    pytest.param(17, "Minor", id="minor"),
                    (18, "Adult"),
                ],
            )
            def test_valid(age, expected):
                assert calculate_age(age) == expected
        """,
    })

    assert covered_inputs(result) == [-1, 17, 18, 121]


def test_pytest_raises_callable_form_is_recognised(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": """
            import pytest
            from calc import calculate_age

            def test_invalid():
                pytest.raises(ValueError, calculate_age, -1)
        """,
    })

    assert covered_inputs(result) == [-1]


def test_keyword_arguments_are_recognised(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": """
            from calc import calculate_age

            def test_keyword():
                assert calculate_age(age=18) == "Adult"
        """,
    })

    assert covered_inputs(result) == [18]


def test_loop_over_literal_values_is_recognised(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": """
            from calc import calculate_age

            def test_loop():
                for age in (0, 1, 119):
                    calculate_age(age)
        """,
    })

    assert covered_inputs(result) == [0, 1, 119]


def test_local_variables_and_class_based_tests(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": """
            import calc

            class TestAge:
                def test_with_variable(self):
                    age = 121
                    calc.calculate_age(age)

                def test_negative(self):
                    calc.calculate_age(-1)
        """,
    })

    assert covered_inputs(result) == [-1, 121]


def test_tests_added_in_the_same_file_are_recognised(tmp_path):
    source = AGE_SOURCE + "\n\ndef test_young():\n    assert calculate_age(0) == 'Minor'\n"
    result = run(tmp_path, source=source)

    assert covered_inputs(result) == [0]


# ---------------------------------------------------------------- files


def test_tests_spread_over_multiple_files_are_combined(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_low.py": direct_tests([-1, 0, 1]),
        "tests/unit/deep/test_mid.py": direct_tests([17, 18, 19]),
        "other_test.py": direct_tests([119, 120, 121]),
    })

    assert counts(result) == (9, 9, 0)
    assert len(result["coverage"]["test_files"]) == 3


def test_unparsable_test_file_does_not_hide_other_results(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_good.py": direct_tests([-1, 0]),
        "tests/test_broken.py": "def test_x(:\n",
    })

    assert counts(result) == (9, 2, 7)


# ---------------------------------------------------------------- precision


def test_duplicate_tests_are_not_counted_twice(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_a.py": direct_tests([18, 18, 18]),
        "tests/test_b.py": direct_tests([18]),
    })

    assert counts(result) == (9, 1, 8)


def test_unrelated_function_calls_are_not_counted(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_noise.py": """
            from calc import calculate_age

            def other_age(age):
                return age

            def helper():
                calculate_age(-1)          # not a test function

            def test_unrelated():
                other_age(-1)              # different function
                print(0)                   # builtin
                len([1])                   # builtin
                max(18, 19)                # builtin
        """,
        "tests/test_local_copy.py": """
            def calculate_age(age):         # local function, not imported from calc
                return age

            def test_local():
                calculate_age(119)
        """,
    })

    assert counts(result) == (9, 0, 9)


def test_substring_of_another_value_is_not_a_match(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": direct_tests([119, 121]),
    })

    assert covered_inputs(result) == [119, 121]


def test_bool_does_not_cover_an_integer_boundary(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": direct_tests([True, False]),
    })

    assert counts(result) == (9, 0, 9)


def test_calls_that_use_unknown_values_are_not_counted(tmp_path):
    result = run(tmp_path, tests={
        "tests/test_age.py": """
            from calc import calculate_age

            def test_fixture_like(some_fixture):
                calculate_age(some_fixture)

            def test_computed():
                calculate_age(int(input()))
        """,
    })

    assert counts(result) == (9, 0, 9)


# ---------------------------------------------------------------- categories


COLLECTION_SOURCE = textwrap.dedent('''
    def find_second_largest(nums):
        return sorted(set(nums))[-2]
''')

RATIO_SOURCE = textwrap.dedent('''
    def ratio(a, b):
        return a / b
''')


def test_empty_single_and_repeated_categories(tmp_path):
    result = run(tmp_path, source=COLLECTION_SOURCE, tests={
        "tests/test_second.py": """
            from calc import find_second_largest

            def test_empty():
                find_second_largest([])

            def test_single():
                find_second_largest([99])

            def test_repeated():
                find_second_largest([3, 3, 3])
        """,
    })

    categories = {
        s["category"]: s["covered"]
        for s in result["functions"][0]["suggestions"]
    }
    assert categories == {
        "empty_collection": True,
        "single_element": True,
        "repeated_values": True,
    }
    assert counts(result) == (3, 3, 0)


def test_collection_categories_report_missing_when_absent(tmp_path):
    result = run(tmp_path, source=COLLECTION_SOURCE, tests={
        "tests/test_second.py": """
            from calc import find_second_largest

            def test_two_values():
                find_second_largest([1, 2])
        """,
    })

    assert counts(result) == (3, 0, 3)


def test_zero_denominator_with_positional_and_keyword_calls(tmp_path):
    result = run(tmp_path, source=RATIO_SOURCE, tests={
        "tests/test_ratio.py": """
            import pytest
            from calc import ratio

            def test_zero_positional():
                with pytest.raises(ZeroDivisionError):
                    ratio(1, 0)
        """,
    })

    assert result["functions"][0]["suggestions"][0]["category"] == "zero_denominator"
    assert counts(result) == (1, 1, 0)

    result = run(tmp_path, source=RATIO_SOURCE, tests={
        "tests/test_ratio.py": "from calc import ratio\n\ndef test_ok():\n    ratio(1, 2)\n",
    })
    assert counts(result) == (1, 0, 1)


def test_comparison_boundary_on_second_argument(tmp_path):
    source = textwrap.dedent('''
        def divide(a, b):
            if b < 0:
                return None
            return a / b if b else 0
    ''')
    result = run(tmp_path, source=source, tests={
        "tests/test_divide.py": """
            from calc import divide

            def test_edges():
                divide(10, -1)
                divide(a=10, b=0)
        """,
    })

    boundary = sorted(
        next(iter(s["input"].values()))
        for s in result["functions"][0]["suggestions"]
        if s["category"] == "comparison_boundary" and s["covered"]
    )
    assert boundary == [-1, 0]


def test_methods_are_matched_through_an_instance(tmp_path):
    source = textwrap.dedent('''
        class Account:
            def withdraw(self, amount):
                if amount > 100:
                    raise ValueError("limit")
                return amount
    ''')
    result = run(tmp_path, source=source, tests={
        "tests/test_account.py": """
            from calc import Account

            def test_limit():
                account = Account()
                account.withdraw(101)
                Account().withdraw(99)
        """,
    })

    assert covered_inputs(result) == [99, 101]


# ---------------------------------------------------------------- existing behaviour


def test_existing_suggestion_categories_are_still_generated(tmp_path):
    source = textwrap.dedent('''
        def mixed(nums, limit, divisor):
            if limit > 10:
                return nums[0]
            return limit / divisor
    ''')
    result = run(tmp_path, source=source)
    categories = {s["category"] for s in result["suggestions"]}

    assert {
        "empty_collection",
        "single_element",
        "repeated_values",
        "comparison_boundary",
        "zero_denominator",
    } <= categories
    assert result["count"] == result["suggested"] == len(result["suggestions"])


def test_coverage_failure_is_reported_not_hidden(tmp_path, monkeypatch):
    import analyzer.test_coverage as coverage

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(coverage, "inspect_test_coverage", boom)
    result = run(tmp_path)

    assert result["coverage_status"] == "error"
    assert "boom" in result["coverage"]["note"]


@pytest.mark.parametrize("count", [0, 3, 9])
def test_counts_always_add_up(tmp_path, count):
    result = run(tmp_path, tests={
        "tests/test_age.py": direct_tests(AGE_VALUES[:count]),
    })

    suggested, covered, missing = counts(result)
    assert (suggested, covered, missing) == (9, count, 9 - count)