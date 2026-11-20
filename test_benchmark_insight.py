"""Tests for the code-based explanation shown after a benchmark."""

import textwrap

from analyzer.benchmark_auto import add_insight, summarize
from analyzer.benchmark_insight import explain

SOURCE = textwrap.dedent('''
    def keep(items, seen):
        out = []
        for x in items:
            if x in seen:
                out.append(x)
        return out

    def known_set(items):
        seen = set(items)
        return [x for x in items if x in seen]

    def positions(nums):
        return [nums.index(x) for x in nums]

    def tally(words):
        return [words.count(w) for w in words]

    def total(nums):
        result = 0
        for n in nums:
            result += n
        return result

    def double(a):
        return a * 2

    def fib(n):
        if n < 2:
            return n
        return fib(n - 1) + fib(n - 2)

    def pairs(nums):
        r = 0
        for i in nums:
            for j in nums:
                r += i * j
        return r

    def delegate(items):
        return helper(items)

    def drain(queue):
        out = []
        while queue:
            out.append(queue.pop(0))
        return out

    def resort(items):
        for i in range(len(items)):
            items = sorted(items)
        return items

    def build(n):
        text = ""
        for i in range(n):
            text += "x"
        return text

    def small_loops(x):
        for i in range(3):
            for j in range(3):
                x += i * j
        return x

    def sorted_once(items):
        return [y for y in sorted(items)]
''')


def test_list_search_in_loop_names_the_line_and_the_fix():
    result = explain(SOURCE, "keep", 2)

    assert result["title"] == "Try this"
    assert "Line 5" in result["found"]
    assert "`x in seen`" in result["found"]
    assert "set" in result["advice"]
    assert "seen_set = set(seen)" in result["example"]


def test_set_membership_is_not_flagged():
    result = explain(SOURCE, "known_set", 2)

    assert "membership" not in result["found"]
    assert result["title"] == "Where to look"


def test_index_and_count_in_loop():
    assert ".index()" in explain(SOURCE, "positions", 3)["found"]
    assert "Counter" in explain(SOURCE, "tally", 2)["advice"]


def test_nested_loops_are_explained():
    result = explain(SOURCE, "pairs", 2)

    assert "another loop inside" in result["found"]
    assert "quadruples" in result["found"]


def test_double_recursion_suggests_caching():
    result = explain(SOURCE, "fib", 3)

    assert "calls itself 2 times" in result["found"]
    assert "functools.cache" in result["advice"]


def test_cached_recursion_is_not_flagged():
    source = (
        "from functools import cache\n\n"
        "@cache\ndef f(n):\n    return f(n-1) + f(n-2)\n"
    )

    assert "calls itself" not in explain(source, "f", 3)["found"]


def test_front_of_list_and_sort_and_string_patterns():
    assert "deque" in explain(SOURCE, "drain", 2)["advice"]
    assert "sorted" in explain(SOURCE, "resort", 2)["found"]
    assert "join" in explain(SOURCE, "build", 2)["advice"]


def test_fast_functions_never_get_a_slow_code_tip():
    loop = explain(SOURCE, "total", 1)
    plain = explain(SOURCE, "double", 0)

    assert loop["title"] == "Nothing to fix"
    assert "once" in loop["found"]
    assert plain["title"] == "Nothing to fix"
    assert "no loops" in plain["found"]


def test_small_fixed_loops_are_not_nested_loops():
    result = explain(SOURCE, "small_loops", 1)

    assert result["title"] == "Nothing to fix"


def test_sorting_the_loop_input_once_is_not_flagged():
    assert explain(SOURCE, "sorted_once", 1)["title"] == "Nothing to fix"


def test_a_known_pattern_in_a_fast_function_is_a_heads_up_only():
    result = explain(SOURCE, "keep", 0)

    assert result["title"] == "Keep an eye on this"
    assert "nothing to fix" in result["advice"]


def test_slow_without_a_known_pattern_points_at_called_functions():
    result = explain(SOURCE, "delegate", 3)

    assert result["title"] == "Where to look"
    assert "helper()" in result["advice"]


def test_methods_and_unknown_names():
    source = (
        "class Box:\n"
        "    def go(self, items, seen):\n"
        "        return [x for x in items if x in seen]\n"
    )

    assert explain(source, "Box.go", 2)["title"] == "Try this"
    assert explain(source, "Box.missing", 2) is None
    assert explain("def broken(:\n", "f", 2) is None


def test_insight_is_attached_to_the_verdict(tmp_path):
    path = tmp_path / "t.py"
    path.write_text(SOURCE)
    measured = [
        {"failed": False, "size": size, "label": f"{size:,} items",
         "median_seconds": seconds, "peak_memory_bytes": 10}
        for size, seconds in ((100, 0.001), (1000, 0.1), (10000, 10.0))
    ]
    summary = add_insight(summarize("keep", "list", measured), str(path))

    assert summary["insight"]["title"] == "Try this"
    assert add_insight({"failed": True}, str(path)) == {"failed": True}
