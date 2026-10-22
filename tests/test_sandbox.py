"""Runs real containers; skipped when Docker is not running (CI runs them)."""
from algoreplay.sandbox import record_expected, run_tests
from conftest import needs_docker

FN_TESTS = [{"name": "t", "input": [[2, 7, 11, 15], 9], "expected": [0, 1]}]
IO_TESTS = [{"name": "t", "input": "3 4\n", "expected": "7"}]


def status(code, tests=FN_TESTS, judge="function"):
    return run_tests(code, tests, judge)["status"]


def test_syntax_and_no_tests_need_no_docker():
    assert status("def solution(:\n") == "SYNTAX_ERROR"
    assert status("def solution(): pass\n", tests=[]) == "NO_TESTS"


@needs_docker
def test_function_judge():
    assert status("def solution(a, t):\n    return (0, 1)\n") == "PASS"   # tuple == list after JSON
    assert status("def solution(a, t):\n    return [1, 0]\n") == "FAIL"
    assert status("def solution(a, t):\n    while True: pass\n") == "TIMEOUT"
    assert status("def solution(a, t):\n    return 1 / 0\n") == "RUNTIME_ERROR"
    assert status("def other():\n    pass\n") == "RUNTIME_ERROR"   # missing entrypoint


@needs_docker
def test_stdio_judge():
    assert status("a, b = map(int, input().split())\nprint(a + b)\n", IO_TESTS, "stdio") == "PASS"
    assert status("import sys\nprint(sum(map(int, sys.stdin.buffer.read().split())), '  ')\n",
                  IO_TESTS, "stdio") == "PASS"                             # trailing spaces ignored, buffer API ok
    assert status("print(sum(map(int, open(0).read().split())))\n", IO_TESTS, "stdio") == "PASS"
    assert status("print(8)\n", IO_TESTS, "stdio") == "FAIL"
    assert status("import sys\nsys.exit(1)\n", IO_TESTS, "stdio") == "RUNTIME_ERROR"
    assert status("while True: pass\n", IO_TESTS, "stdio") == "TIMEOUT"


@needs_docker
def test_isolation():
    net = "import urllib.request\nurllib.request.urlopen('http://1.1.1.1', timeout=2)\nprint(7)\n"
    assert status(net, IO_TESTS, "stdio") == "RUNTIME_ERROR"               # --network none
    write = "open('/work/x', 'w')\nprint(7)\n"
    assert status(write, IO_TESTS, "stdio") == "RUNTIME_ERROR"             # read-only mount
    peek = "import os\nprint(7 if not os.path.exists('/work/tests.json') else 0)\n"
    assert status(peek, IO_TESTS, "stdio") == "PASS"                      # expected answers are not on disk


@needs_docker
def test_record_expected_uses_past_solution_as_oracle():
    ref = "a, b = map(int, input().split())\nprint(a * b)\n"
    made, rejected = record_expected(ref, ["3 4\n", "oops\n"], "stdio")
    assert made == [{"input": "3 4\n", "expected": "12\n"}] and len(rejected) == 1
    made, _ = record_expected("def solution(n):\n    return [n] * 2\n", [[5]], "function")
    assert made == [{"input": [5], "expected": [5, 5]}]


SQL_TESTS = [{"name": "t", "input": {"tables": [{"name": "Owner", "columns": [["id", "int"], ["kind", "ENUM"]],
                                                 "rows": [["1", "cat"], ["2", None], ["3", "cat"]]}],
                                     "result_table": None},
              "expected": {"columns": ["id"], "rows": [["3"], ["1"]], "ordered": False}}]


@needs_docker
def test_sql_judge():
    assert status("SELECT id FROM Owner WHERE kind = 'cat';", SQL_TESTS, "sql") == "PASS"  # any order
    assert status("SELECT id FROM Owner;", SQL_TESTS, "sql") == "FAIL"
    assert status("SELEC id;", SQL_TESTS, "sql") == "RUNTIME_ERROR"
    deleted = [{**SQL_TESTS[0], "input": {**SQL_TESTS[0]["input"], "result_table": "Owner"},
                "expected": {"columns": ["id", "kind"], "rows": [["1", "cat"], ["3", "cat"]], "ordered": False}}]
    assert status("DELETE FROM Owner WHERE kind IS NULL;", deleted, "sql") == "PASS"


@needs_docker
def test_full_output_and_prints_are_kept():
    r = run_tests("def solution(a, t):\n    print('debug', a)\n    return [0, 1]\n", FN_TESTS)
    assert r["status"] == "PASS" and r["results"][0]["stdout"] == "debug [2, 7, 11, 15]\n"
    long = run_tests("print('x' * 10000)\n", [{"name": "t", "input": "", "expected": "x" * 10000}], "stdio")
    assert long["status"] == "PASS" and len(long["results"][0]["output"].strip()) == 10000
