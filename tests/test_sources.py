import json

from algoreplay import problems, sources
from conftest import EXAMPLES

# Self-written fixtures that mirror BaekjoonHub's README layout (not real problem text).
BOJ_README = """# [Gold V] 색 영역 - 12345

[문제 링크](https://www.acmicpc.net/problem/12345)

### 성능 요약

메모리: 114108 KB, 시간: 124 ms

### 분류

너비 우선 탐색, 깊이 우선 탐색, 그래프 이론

### 제출 일자

2024년 9월 30일 13:30:30

### 문제 설명

<p>격자에서 <code>A&lt;B</code> 규칙으로 영역을 센다. 예:</p>

<pre>AB
BA</pre>

### 입력

 <p>첫째 줄에 N이 주어진다. (1 ≤ N ≤ 100)</p>

### 출력

 <p>영역의 수를 출력한다.</p>
"""

PROGRAMMERS_README = """# [level 2] 합 구하기 - 99999

[문제 링크](https://school.programmers.co.kr/learn/courses/30/lessons/99999)

### 구분

코딩테스트 연습 > 스택／큐

### 제출 일자

2024년 02월 22일 17:50:49

### 문제 설명

<p>두 수를 더한다.</p>

<h5>[입출력 예]</h5>
<table class="table">
<thead><tr><th>a</th><th>b</th><th>result</th></tr></thead>
<tbody><tr><td>1</td><td>[2, 3]</td><td>true</td></tr>
<tr><td>"x"</td><td>KAKAO</td><td>[1, 2]</td></tr></tbody>
</table>
<h5>입출력 예 설명</h5>
<table><tr><th>ignored</th><th>table</th></tr><tr><td>1</td><td>2</td></tr></table>
"""


def test_baekjoonhub_boj():
    # real BaekjoonHub paths contain U+2005 (four-per-em space) after the problem number
    prob, reason = sources.parse_baekjoonhub(BOJ_README, "print(1)\n", "백준/Gold/12345. 색 영역")
    assert reason is None
    assert (prob["problem_key"], prob["source"], prob["title"]) == ("boj-12345", "boj", "색 영역")
    assert (prob["tier"], prob["difficulty"], prob["judge"]) == ("Gold V", "hard", "stdio")
    assert prob["topics"] == ["bfs", "dfs", "graph"]
    assert prob["solved_at"] == "2024-09-30T13:30:30"
    assert "```\nAB\nBA\n```" in prob["statement"] and "`A<B`" in prob["statement"]
    assert "### 입력" in prob["statement"] and "<p>" not in prob["statement"]


def test_baekjoonhub_programmers_examples():
    prob, _ = sources.parse_baekjoonhub(PROGRAMMERS_README, "def solution(a, b):\n    return a\n", "프로그래머스/2/x")
    assert (prob["source"], prob["judge"], prob["difficulty"]) == ("programmers", "function", "medium")
    assert prob["topics"] == ["stack", "queue"]
    assert [(t["input"], t["expected"]) for t in prob["tests"]] == [([1, [2, 3]], True), (["x", "KAKAO"], [1, 2])]
    assert "| a | b | result |" in prob["statement"]


def test_vertical_programmers_table():
    html = ("<h5>입출력 예제</h5><table><tr><th>매개변수</th><th>값</th></tr><tr><td>n</td><td>5</td></tr>"
            "<tr><td>출력</td><td>[1, 2]</td></tr></table>")
    assert sources._programmers_examples(html) == [{"name": "예제 1", "input": [5], "expected": [1, 2]}]


def test_impossible_submission_date_is_ignored():
    readme = BOJ_README.replace("2024년 9월 30일", "2024년 02월 00일")
    assert sources.parse_baekjoonhub(readme, "", "백준/x")[0]["solved_at"] is None


def test_not_baekjoonhub():
    assert sources.parse_baekjoonhub("# My notes", "", "x")[0] is None


def test_topics_fallback_from_past_solution():
    code = "def solution(nums, target):\n    seen = {}\n    for i, x in enumerate(nums):\n        seen[x] = i\n"
    assert sources.topics_for([], code) == ["hashmap"]
    assert sources.topics_for(["우선순위 큐"]) == ["heap"]


def test_sync_examples_incremental_and_removal(db, tmp_path):
    stats = sources.sync(db, sources.local_source(EXAMPLES))
    assert stats["added"] == 5 and not stats["skipped"]
    assert sources.sync(db, sources.local_source(EXAMPLES))["unchanged"] == 5

    by_key = {p["problem_key"]: p for p in problems.list_problems(db)}
    assert by_key["programmers-90002"]["test_count"] == 3
    assert by_key["boj-90001"]["test_count"] == 0
    assert "reference_solution" not in problems.get_problem(db, by_key["two-sum"]["id"])  # hidden during replay

    # user tests survive a re-sync; repo tests are replaced
    problems.add_tests(db, by_key["boj-90001"]["id"], [{"input": "1 1\n1\n", "expected": "1 1"}])
    src = sources.local_source(EXAMPLES)
    readme = next(p for p in src["files"] if p.endswith("90001. 섬 세기/README.md"))
    src["files"][readme] = "changed"
    assert sources.sync(db, src)["updated"] == 1
    assert len(problems.get_tests(db, by_key["boj-90001"]["id"])) == 1

    # a problem deleted from the repo disappears unless it has history or tests the user added
    del src["files"][readme]
    assert sources.sync(db, src)["removed"] == 0
    problems.delete_test(db, problems.get_tests(db, by_key["boj-90001"]["id"])[0]["id"])
    assert sources.sync(db, src)["removed"] == 1


def test_duplicate_problem_in_two_folders(db, tmp_path):
    for folder in ("백준/Gold/1. A", "백준/Gold V/1. A"):
        d = tmp_path / folder
        d.mkdir(parents=True)
        (d / "README.md").write_text(BOJ_README.replace("12345", "1"), encoding="utf-8")
        (d / "a.py").write_text("print(1)\n", encoding="utf-8")
    stats = sources.sync(db, sources.local_source(tmp_path))
    assert stats["added"] == 1 and "duplicate" in stats["skipped"][0][1]


def test_unsupported_language_is_reported(db, tmp_path):
    d = tmp_path / "프로그래머스/lv1/1. SQL"
    d.mkdir(parents=True)
    (d / "README.md").write_text(PROGRAMMERS_README, encoding="utf-8")
    (d / "q.sql").write_text("SELECT 1", encoding="utf-8")
    assert "Python" in sources.sync(db, sources.local_source(tmp_path))["skipped"][0][1]


def test_html_to_markdown_never_passes_html_through():
    md = sources.html_to_markdown('<p>a*b <script>alert(1)</script><img src="x.png"> 2<sup>10</sup></p>')
    assert "<" not in md and "a\\*b" in md and "2^10" in md


def test_native_tests_json_roundtrip(db):
    sources.sync(db, sources.local_source(EXAMPLES))
    pid = problems.list_problems(db, query="two-sum")[0]["id"]
    first = problems.get_tests(db, pid)[0]
    raw = json.loads((EXAMPLES / "problems/two-sum/tests.json").read_text())[0]
    assert (first["input"], first["expected"]) == (raw["args"], raw["expected"])


def _notebook(*cells):
    """cells: "# md text" for markdown, (code, output-or-None) for code."""
    def cell(c):
        if isinstance(c, str):
            return {"cell_type": "markdown", "source": [c]}
        out = [] if c[1] is None else [{"output_type": "execute_result", "data": {"text/plain": [c[1]]}}]
        return {"cell_type": "code", "source": [c[0]], "outputs": out}
    return json.dumps({"cells": [cell(c) for c in cells]})


def test_loose_notebook_function_with_sample_tests():
    nb = _notebook("메모: 해시로 풀었다", ("def solution(a, b):\n    return a + b", None), ("solution(1, [2][0])", "3"),
                   ("solution(2, 5)", "7"))
    p, _ = sources.parse_loose("programmers/Solutions/해시_더하기.ipynb", nb)
    assert (p["title"], p["source"], p["judge"], p["tags"]) == ("더하기", "programmers", "function", ["해시"])
    assert [t["input"] for t in p["tests"]] == [[2, 5]]  # only literal arguments become tests
    assert "solution(2, 5)" not in p["reference_solution"] and "# 메모" in p["reference_solution"]
    assert "문제 설명이 없습니다" in p["statement"] and "해시로" not in p["statement"]


def test_loose_stdio_files():
    swea = _notebook("## 1001. 숫자 세기 D2\n[링크](https://swexpertacademy.com/x)", ("n = int(input())\nprint(n)", None))
    p, _ = sources.parse_loose("sw_expert_academy/D2/1001_.ipynb", swea)
    assert (p["problem_key"], p["title"], p["tier"], p["judge"]) == ("swea-1001", "숫자 세기", "D2", "stdio")
    assert "swexpertacademy.com" in p["statement"]
    txt, _ = sources.parse_loose("baekjoon/1002.txt", "a = input()  // 한 줄 입력\nprint(a // 2)\n\n**다른 답안**\n")
    assert txt["problem_key"] == "boj-1002" and "acmicpc.net/problem/1002" in txt["url"]
    assert txt["reference_solution"] == "a = input()  # 한 줄 입력\nprint(a // 2)\n"


def test_loose_ignored_or_rejected():
    assert sources.parse_loose("notes/requirements.txt", "streamlit\n") == (None, None)
    assert sources.parse_loose("programmers/연습문제/연습문제_3개.ipynb", "{}")[0] is None
    assert sources.parse_loose("programmers/Solutions/a_b", "def solution(:\n")[1]


def test_loose_file_loses_to_structured_duplicate(db, tmp_path):
    d = tmp_path / "백준/Gold/12345. 색 영역"
    d.mkdir(parents=True)
    (d / "README.md").write_text(BOJ_README, encoding="utf-8")
    (d / "a.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "baekjoon").mkdir()
    (tmp_path / "baekjoon/12345_색 영역.txt").write_text("print(input())\n", encoding="utf-8")
    stats = sources.sync(db, sources.local_source(tmp_path))
    assert stats["added"] == 1 and "duplicate of 백준" in stats["skipped"][0][1]


# Self-written LeetHub-style README (layout only, not LeetCode text).
LEETHUB_README = """<h2><a href="https://leetcode.com/problems/pet-owners/">9001. Pet Owners</a></h2><h3>Easy</h3><hr>
<p>Table: <code>Owner</code></p>
<pre>
+-------------+---------+
| Column Name | Type    |
+-------------+---------+
| id          | int     |
| kind        | ENUM    |
+-------------+---------+
</pre>
<p>List owners with a cat. Return the result table in <strong>any order</strong>.</p>
<p><strong class="example">Example 1:</strong></p>
<pre><strong>Input:</strong>
Owner table:
+----+------+
| id | kind |
+----+------+
| 1  | cat  |
| 2  | null |
+----+------+
<strong>Output:</strong>
+----+
| id |
+----+
| 1  |
+----+
</pre>"""


def test_leethub_sql_tests_from_examples():
    p, _ = sources.parse_leethub(LEETHUB_README, "SELECT id FROM Owner WHERE kind = 'cat';", "9001-pet-owners.sql")
    assert (p["problem_key"], p["judge"], p["difficulty"], p["topics"]) == ("leetcode-9001", "sql", "easy", ["sql"])
    t = p["tests"][0]
    assert t["input"]["tables"][0] == {"name": "Owner", "columns": [["id", "int"], ["kind", "ENUM"]],
                                       "rows": [["1", "cat"], ["2", None]]}
    assert t["expected"] == {"columns": ["id"], "rows": [["1"]], "ordered": False}
    assert sources.parse_leethub(LEETHUB_README, "class Solution: pass", "x.py")[0] is None
    assert sources.parse_leethub(BOJ_README, "", "a.sql") is None  # not LeetHub: falls through


def test_user_tests_survive_resync(db, tmp_path):
    d = tmp_path / "baekjoon"
    d.mkdir()
    (d / "77_old name.txt").write_text("print(input())\n", encoding="utf-8")
    sources.sync(db, sources.local_source(tmp_path))
    pid = problems.list_problems(db)[0]["id"]
    problems.add_tests(db, pid, [{"input": "1\n", "expected": "1"}])
    (d / "77_old name.txt").rename(d / "77_new name.txt")  # file moved: the problem keeps the user's test
    sources.sync(db, sources.local_source(tmp_path))
    assert any(t["origin"] == "user" for p in problems.list_problems(db) for t in problems.get_tests(db, p["id"]))


def test_drafts_persist_and_starter_is_not_stored(db):
    sources.sync(db, sources.local_source(EXAMPLES))
    pid = problems.list_problems(db)[0]["id"]
    problems.save_draft(db, pid, "print('half done')\n")
    assert problems.get_draft(db, pid) == "print('half done')\n"
    problems.save_draft(db, pid, None)                                   # editor not mounted: keep the draft
    assert problems.get_draft(db, pid) == "print('half done')\n"
    problems.save_draft(db, pid, problems.starter_code(db, pid))         # reset to starter: nothing to keep
    assert problems.get_draft(db, pid) is None
