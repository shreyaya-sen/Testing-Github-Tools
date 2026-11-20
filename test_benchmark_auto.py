"""Tests for the friendly benchmark helpers."""

import textwrap

from analyzer.benchmark_auto import (
    benchmark_size,
    build_input,
    list_functions,
    size_label,
    summarize,
)

SOURCE = textwrap.dedent('''
    import asyncio

    def positions(nums):
        return sorted(nums)

    def calculate_age(age):
        return "Adult" if age >= 18 else "Minor"

    def shout(text):
        return text.upper()

    def count_to(limit):
        total = 0
        for i in range(limit):
            total += i
        return total

    def divide(a, b):
        return a / b

    def with_default(items, scale=2):
        return [x * scale for x in items]

    def numbers():
        yield 1

    def no_args():
        return 1

    async def later(x):
        return x

    def typed(value: str):
        return value

    class Box:
        def method(self, items):
            return items
''')


def by_name(listing):
    return {item["name"]: item for item in listing["functions"]}


def test_functions_are_listed_with_kind_and_support():
    functions = by_name(list_functions(SOURCE))

    assert functions["positions"]["ok"] and functions["positions"]["kind"] == "list"
    assert functions["calculate_age"]["kind"] == "number"
    assert functions["shout"]["kind"] == "text"
    assert functions["count_to"]["kind"] == "number"
    assert functions["typed"]["kind"] == "text"
    assert functions["with_default"]["ok"]
    assert functions["positions"]["signature"] == "positions(nums)"


def test_every_kind_of_function_can_be_timed():
    functions = by_name(list_functions(SOURCE))

    assert all(item["ok"] for item in functions.values())
    assert functions["divide"]["kinds"] == ["number", "divisor"]
    assert functions["divide"]["note"] == "Test data: a number and a number"
    assert functions["numbers"]["scales"] is False
    assert functions["no_args"]["kind"] == "none"
    assert functions["no_args"]["scales"] is False
    assert functions["later"]["ok"]


def test_methods_of_simple_classes_are_listed():
    functions = by_name(list_functions(SOURCE))

    assert functions["Box.method"]["signature"] == "Box.method(items)"
    assert functions["Box.method"]["kind"] == "list"


def test_classes_that_need_constructor_input_are_skipped():
    source = (
        "class Needs:\n"
        "    def __init__(self, x):\n        pass\n"
        "    def go(self, n):\n        return n\n"
    )
    assert list_functions(source)["functions"] == []


def test_more_kinds_of_data_are_guessed():
    source = textwrap.dedent("""
        def a(words): return len(words)
        def b(flag): return flag
        def c(table): return table["x"]
        def d(grid): return grid
        def e(start, end):
            return list(range(start, end))
        def f(*, size): return size
    """)
    functions = by_name(list_functions(source))

    assert functions["a"]["kinds"] == ["words"]
    assert functions["b"]["kinds"] == ["bool"]
    assert functions["c"]["kinds"] == ["dict"]
    assert functions["d"]["kinds"] == ["matrix"]
    assert functions["e"]["kinds"] == ["number", "number"]
    assert functions["f"]["kinds"] == ["number"]
    assert functions["f"]["keyword_only"] == ["size"]


def test_test_data_is_repeatable_and_sized():
    assert build_input("list", 100) == build_input("list", 100)
    assert len(build_input("list", 1000)) == 1000
    assert build_input("number", 500) == 500
    assert len(build_input("text", 250)) == 250
    assert size_label("list", 1000) == "1,000 items"
    assert size_label("number", 1000) == "n = 1,000"


def write(tmp_path, source):
    path = tmp_path / "target.py"
    path.write_text(textwrap.dedent(source))
    return str(path)


def test_benchmark_size_measures_a_real_function(tmp_path):
    path = write(tmp_path, "def f(nums):\n    return sorted(nums)\n")
    result = benchmark_size(path, "f", 1000)

    assert result["failed"] is False
    assert result["input_kind"] == "list"
    assert result["median_seconds"] >= 0
    assert result["label"] == "1,000 items"
    assert result["evidence_type"] == "measured"


def test_wrong_function_name_gives_a_plain_sentence_not_a_traceback(tmp_path):
    path = write(tmp_path, "def f(nums):\n    return nums\n")
    result = benchmark_size(path, "unique", 100)

    assert result["failed"] is True
    assert "could not find that function" in result["friendly"]
    assert "Traceback" not in result["friendly"]
    assert "Traceback" in result["technical"]


def test_type_errors_suggest_changing_test_data(tmp_path):
    path = write(tmp_path, "def f(text):\n    return text.upper()\n")
    result = benchmark_size(path, "f", 100, input_kind="list")

    assert result["failed"] is True
    assert "did not accept the test data" in result["friendly"]


def test_user_exceptions_are_explained(tmp_path):
    path = write(tmp_path, "def f(nums):\n    return 1 / 0\n")
    result = benchmark_size(path, "f", 100)

    assert "ZeroDivisionError" in result["friendly"]


def test_broken_file_is_explained(tmp_path):
    path = write(tmp_path, "def f(nums:\n    return 1\n")
    result = benchmark_size(path, "f", 100)

    assert result["failed"] is True
    assert "could not load your file" in result["friendly"]


def measurement(size, seconds, memory=1000):
    return {
        "failed": False,
        "size": size,
        "label": f"{size:,} items",
        "median_seconds": seconds,
        "peak_memory_bytes": memory,
    }


def test_flat_growth_is_rated_fast():
    result = summarize("f", "list", [
        measurement(100, 0.01), measurement(1000, 0.01), measurement(10000, 0.011),
    ])

    assert result["word"] == "Fast" and result["level"] == 0


def test_linear_growth_is_rated_good():
    result = summarize("f", "list", [
        measurement(100, 0.01), measurement(1000, 0.1), measurement(10000, 1.0),
    ])

    assert result["word"] == "Good"
    assert round(result["growth_ratio"]) == 10


def test_quadratic_growth_is_rated_slow():
    result = summarize("f", "list", [
        measurement(100, 0.001), measurement(1000, 0.1), measurement(10000, 10.0),
    ])

    assert result["word"] == "Slow"
    assert round(result["growth_ratio"]) == 100


def test_worse_than_quadratic_is_very_slow():
    result = summarize("f", "list", [
        measurement(1000, 0.01), measurement(10000, 100.0),
    ])

    assert result["word"] == "Very slow"


def test_tiny_times_are_always_fast_even_if_noisy():
    result = summarize("f", "list", [
        measurement(100, 0.000001), measurement(1000, 0.00005),
    ])

    assert result["word"] == "Fast"


def test_one_measurement_is_unclear_not_a_guess():
    result = summarize("f", "list", [measurement(100, 0.5)])

    assert result["word"] == "Unclear" and result["level"] is None


def test_partial_results_keep_the_stop_reason():
    failure = {"size": 10000, "reason": "too_slow", "friendly": "Took too long."}
    result = summarize("f", "list", [
        measurement(100, 0.01), measurement(1000, 1.0),
    ], failure)

    assert result["failed"] is False
    assert result["stopped"]["reason"] == "too_slow"
    assert result["largest"]["size"] == 1000


def test_no_measurements_returns_a_failure():
    result = summarize("f", "list", [], {"friendly": "Nope.", "technical": "tb"})

    assert result["failed"] is True
    assert result["friendly"] == "Nope."


def test_two_input_function_is_timed_without_any_setup(tmp_path):
    path = write(tmp_path, "def divide(a, b):\n    return a / b\n")
    result = benchmark_size(path, "divide", 1000)

    assert result["failed"] is False
    assert result["kinds"] == ["number", "divisor"]
    assert result["label"] == "n = 1,000"


def test_list_and_number_function_gets_both_inputs(tmp_path):
    path = write(
        tmp_path,
        "def find(items, target):\n"
        "    return [i for i, x in enumerate(items) if x == target]\n",
    )
    result = benchmark_size(path, "find", 1000)

    assert result["failed"] is False
    assert result["input_kind"] == "list"


def test_keyword_only_and_default_inputs_work(tmp_path):
    path = write(
        tmp_path,
        "def f(items, *, scale, extra=3):\n"
        "    return [x * scale + extra for x in items]\n",
    )
    result = benchmark_size(path, "f", 100)

    assert result["failed"] is False


def test_wrong_first_guess_is_retried_with_other_data(tmp_path):
    # The name says "list" but the code needs a dictionary-like object.
    path = write(
        tmp_path,
        "def f(data):\n    return sum(data.values())\n",
    )
    result = benchmark_size(path, "f", 100)

    assert result["failed"] is False
    assert result["kinds"] == ["dict"]


def test_function_with_no_input_is_timed_as_it_is(tmp_path):
    path = write(tmp_path, "def f():\n    return sum(range(1000))\n")
    result = benchmark_size(path, "f", 100)

    assert result["failed"] is False
    assert result["input_kind"] == "none"
    assert result["label"] == "One run"
    verdict = summarize("f", "none", [result])
    assert verdict["word"] == "Fast"


def test_async_and_generator_functions_are_timed(tmp_path):
    path = write(
        tmp_path,
        "async def a(n):\n    return n\n\ndef g(n):\n    yield from range(n)\n",
    )

    assert benchmark_size(path, "a", 100)["failed"] is False
    assert benchmark_size(path, "g", 1000)["failed"] is False


def test_class_methods_are_timed(tmp_path):
    path = write(
        tmp_path,
        "class Box:\n    def total(self, items):\n        return sum(items)\n",
    )
    result = benchmark_size(path, "Box.total", 1000)

    assert result["failed"] is False


def test_in_place_changes_do_not_affect_later_runs(tmp_path):
    # A sort in place would otherwise be timed on already sorted data.
    path = write(tmp_path, "def f(nums):\n    nums.sort()\n    return nums\n")
    result = benchmark_size(path, "f", 1000)

    assert result["failed"] is False


def test_large_inputs_do_not_hit_the_command_line_limit(tmp_path):
    path = write(tmp_path, "def f(nums):\n    return len(nums)\n")
    result = benchmark_size(path, "f", 10000)

    assert result["failed"] is False
