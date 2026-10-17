from algoreplay.analysis import analyze_code, compare_solutions

BRUTE = """def solution(nums, target):
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
"""
HASH = """def solution(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        if target - x in seen:
            return [seen[target - x], i]
        seen[x] = i
"""
BSEARCH = """def solution(nums, target):
    lo, hi = 0, len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        if nums[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
"""
REPLACE_LOOP = """def solution(s):
    prev = None
    while prev != s:
        prev = s
        s = s.replace('()', '')
    return s == ''
"""
GRID_BFS = """from collections import deque
def bfs(x, y):
    q = deque([(x, y)])
    while q:
        x, y = q.popleft()
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            q.append((x + dx, y + dy))
"""
READ_LINES = """n = int(input())
rows = [list(map(int, input().split())) for _ in range(n)]
total = 0
for row in rows:
    total += sum(row)
print(total)
"""


def test_complexity_rules():
    cases = {BRUTE: ("brute_force", "O(N^2)", "O(1)"), HASH: ("hash_map", "O(N)", "O(N)"),
             BSEARCH: ("binary_search", "O(log N)", "O(1)"), GRID_BFS: ("bfs", "O(N)", "O(N)")}
    for code, expected in cases.items():
        a = analyze_code(code)
        assert (a["algorithm_family"], a["time_complexity"], a["space_complexity"]) == expected, code


def test_hidden_linear_call_inside_loop():
    assert analyze_code(REPLACE_LOOP)["time_complexity"] == "O(N^2)"   # replace() in a loop
    assert analyze_code(READ_LINES)["time_complexity"] == "O(N^2)"     # sum(row) per row of an N×N grid


def test_reading_input_lines_is_not_quadratic():
    code = "n = int(input())\nfor _ in range(n):\n    a, b = map(int, input().split())\n    print(a + b)\n"
    assert analyze_code(code)["time_complexity"] == "O(N)"


INLINE_GRID_BFS = """from collections import deque
n = int(input())
seen = [[False] * n for _ in range(n)]
for i in range(n):
    for j in range(n):
        if seen[i][j]:
            continue
        queue = deque([(i, j)])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((1, 0), (0, 1)):
                queue.append((x + dx, y + dy))
"""


def test_traversal_inside_grid_loop_is_amortised():
    # BFS inlined into the i/j loop visits each cell once: O(N^2) for an N×N grid, not O(N^3)
    assert analyze_code(INLINE_GRID_BFS)["time_complexity"] == "O(N^2)"


def test_exponential_recursion():
    fib = "def fib(n):\n    if n < 2:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"
    a = analyze_code(fib)
    assert a["time_complexity"] == "O(2^N)" and a["complexity_confidence"] < 0.6


def test_compare_reports_improvement_and_tradeoff():
    cmp = compare_solutions(analyze_code(BRUTE), analyze_code(HASH))
    assert "시간복잡도 O(N^2) → O(N)" in cmp["improved"]
    assert cmp["tradeoff"]


def test_sized_list_allocation_is_linear_space():
    dp = ("def solution(n):\n    dp = [0] * (n + 1)\n    for i in range(2, n + 1):\n"
          "        dp[i] = dp[i - 1] + dp[i - 2]\n    return dp[n]\n")
    assert analyze_code(dp)["space_complexity"] == "O(N)"
    assert analyze_code("DIRS = [0] * 4\n")["space_complexity"] == "O(1)"


def test_different_approach_is_not_called_an_improvement():
    cmp = compare_solutions(analyze_code(BSEARCH), analyze_code(BRUTE.replace("nums[i] + nums[j]", "nums[i]")))
    assert not any("접근 방식" in x for x in cmp["improved"]) and any("접근 방식" in x for x in cmp["changed"])


def test_comprehension_with_two_generators_nests():
    assert analyze_code("cells = [(i, j) for i in range(n) for j in range(m)]\n")["time_complexity"] == "O(N^2)"
    assert analyze_code("dirs = [(dx, dy) for dx in (-1, 1) for dy in (-1, 1)]\n")["time_complexity"] == "O(1)"


def test_syntax_error():
    assert "error" in analyze_code("def f(:\n")
