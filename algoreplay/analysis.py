"""Static analysis with Python `ast`: structure, algorithm family, rule-based complexity, clean-code scores.

Past and current solutions go through the same function, so the results can be compared field by field.
Complexity here is an estimate with a confidence value, never a measurement.
"""
import ast

COMPLEXITY_ORDER = ["O(1)", "O(log N)", "O(N)", "O(N log N)", "O(N^2)", "O(N^3)", "O(2^N)"]

# Calls that are linear in their argument/receiver: inside a loop they add a hidden loop level.
# `split` is left out: `input().split()` per line is linear in the line, not in N.
LINEAR_METHODS = {"replace", "index", "count", "remove", "insert", "join", "find", "reverse", "copy"}
LINEAR_BUILTINS = {"sum", "min", "max", "sorted", "list", "set", "any", "all", "reversed", "tuple"}

FAMILY_TOPICS = {
    "hash_map": ["hashmap"], "binary_search": ["binary-search"], "bfs": ["bfs", "queue"],
    "dfs_recursion": ["dfs", "recursion"], "dynamic_programming": ["dynamic-programming"], "stack": ["stack"],
    "heap": ["heap"], "two_pointer": ["two-pointer"], "sorting": ["sorting"], "brute_force": ["brute-force"],
    "simulation": ["implementation"],
}


def _is_constant_iter(node):
    """`for d in [(0,1),(1,0)]` or `for _ in range(4)` does not grow with the input."""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return True
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range"
            and all(isinstance(a, ast.Constant) for a in node.args))


def _is_worklist_loop(node):
    """`while queue:` whose body pops from that same queue."""
    name = node.test.id if isinstance(node.test, ast.Name) else None
    return bool(name) and any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("pop", "popleft")
        and isinstance(n.func.value, ast.Name) and n.func.value.id == name
        or isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "heappop"
        for n in ast.walk(node))


class FeatureVisitor(ast.NodeVisitor):
    def __init__(self):
        self.for_count = self.while_count = self.comprehensions = 0
        self.depth = self.max_loop_depth = self.hidden_depth = 0
        self.nest = self.max_nesting = 0
        self.calls, self.attr_calls, self.names = [], [], []
        self.funcs, self.func_stack = [], []
        self.self_calls = {}
        self.halving = self.sized_lists = False

    def _block(self, node):
        self.nest += 1
        self.max_nesting = max(self.max_nesting, self.nest)
        self.generic_visit(node)
        self.nest -= 1

    def _loop(self, node):
        self.depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self.depth)
        self._block(node)
        self.depth -= 1

    def visit_For(self, node):
        self.for_count += 1
        if _is_constant_iter(node.iter):
            self._block(node)  # constant-size loop: no extra factor of N
        else:
            self._loop(node)

    def visit_While(self, node):
        self.while_count += 1
        # a loop that halves a range (mid = (lo+hi)//2, x //= 2, x >>= 1) is logarithmic
        if any(isinstance(n, (ast.BinOp, ast.AugAssign)) and isinstance(n.op, (ast.FloorDiv, ast.RShift))
               for n in ast.walk(node)):
            self.halving = True
            self._block(node)
            return
        if self.depth and _is_worklist_loop(node):
            # BFS/DFS worklist inside `for i: for j:` with a visited check: every cell is processed once in
            # total, so the traversal is amortised over the outer loops instead of multiplying them.
            self._block(node)
            return
        self._loop(node)

    visit_If = visit_With = visit_Try = _block

    def _comprehension(self, node):
        self.comprehensions += 1
        # `[... for i in range(n) for j in range(m)]` nests like two for-loops
        levels = sum(not _is_constant_iter(g.iter) for g in node.generators)
        self.depth += levels
        self.max_loop_depth = max(self.max_loop_depth, self.depth)
        self._block(node)
        self.depth -= levels

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _comprehension

    def visit_FunctionDef(self, node):
        self.funcs.append({"name": node.name, "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                           "args": [a.arg for a in node.args.args]})
        self.func_stack.append(node.name)
        outer_depth, self.depth = self.depth, 0  # a nested function body starts its own loop count
        self.generic_visit(node)
        self.depth = outer_depth
        self.func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        linear = False
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
            if node.func.id in self.func_stack:
                self.self_calls[node.func.id] = self.self_calls.get(node.func.id, 0) + 1
            # sum(arr) / sorted(arr) scan a collection; list(map(int, input().split())) only reads one line
            linear = node.func.id in LINEAR_BUILTINS and len(node.args) == 1 and isinstance(
                node.args[0], (ast.Name, ast.Attribute, ast.Subscript))
        elif isinstance(node.func, ast.Attribute):
            self.attr_calls.append(node.func.attr)
            linear = node.func.attr in LINEAR_METHODS or (
                node.func.attr == "pop" and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == 0)
        if linear and self.depth:
            self.hidden_depth = max(self.hidden_depth, self.depth + 1)
        self.generic_visit(node)

    def visit_BinOp(self, node):
        # [0] * (n + 1): a list whose size depends on a variable
        if isinstance(node.op, ast.Mult) and any(isinstance(x, ast.List) for x in (node.left, node.right)) and \
                not all(isinstance(x, (ast.List, ast.Constant)) for x in (node.left, node.right)):
            self.sized_lists = True
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.names.append(node.id)

    def visit_arg(self, node):
        self.names.append(node.arg)


def _detect(v, tree):
    calls, attrs, names = set(v.calls), set(v.attr_calls), set(v.names)
    nodes = list(ast.walk(tree))
    ds = set()
    if calls & {"dict", "defaultdict", "Counter"} or any(isinstance(n, (ast.Dict, ast.DictComp)) for n in nodes):
        ds.add("dict")
    if "set" in calls or any(isinstance(n, (ast.Set, ast.SetComp)) for n in nodes):
        ds.add("set")
    if "deque" in calls:
        ds.add("deque")
    if attrs & {"heappush", "heappop", "heapify"} or calls & {"heappush", "heappop", "heapify"}:
        ds.add("heap")
    if "append" in attrs and "pop" in attrs and "deque" not in calls:
        ds.add("stack")
    if any(isinstance(n, (ast.List, ast.ListComp)) for n in nodes):
        ds.add("list")

    recursive = bool(v.self_calls)
    if "popleft" in attrs:
        family = "bfs"
    elif "heap" in ds:
        family = "heap"
    elif (v.halving and {"mid", "lo", "hi", "left", "right", "l", "r", "start", "end"} & names) or \
            attrs & {"bisect_left", "bisect_right", "bisect"} or calls & {"bisect_left", "bisect_right"}:
        family = "binary_search"
    elif any(n.startswith("dp") for n in names) or {"lru_cache", "cache"} & (attrs | calls):
        family = "dynamic_programming"
    elif recursive:
        family = "dfs_recursion"
    elif "stack" in ds:
        family = "stack"
    elif ds & {"dict", "set"} and v.max_loop_depth >= 1:
        family = "hash_map"
    elif ({"left", "right"} <= names or {"l", "r"} <= names or {"i", "j"} <= names) and v.while_count:
        family = "two_pointer"
    elif "sorted" in calls or "sort" in attrs:
        family = "sorting"
    elif max(v.max_loop_depth, v.hidden_depth) >= 2 or calls & {"permutations", "combinations", "product"}:
        family = "brute_force"
    else:
        family = "simulation"
    return family, sorted(ds)


def _complexity(v, family, ds):
    branching = max(v.self_calls.values(), default=0)
    depth = max(v.max_loop_depth, v.hidden_depth)
    if branching >= 2 and family != "dynamic_programming":
        return "O(2^N)", "O(N)", 0.4
    if depth == 0:
        time = "O(log N)" if v.halving else ("O(N)" if v.self_calls else "O(1)")
    elif depth == 1:
        time = "O(N log N)" if v.halving else "O(N)"
    else:
        time = f"O(N^{min(depth, 3)})"
    if ("sorted" in v.calls or "sort" in v.attr_calls) and \
            COMPLEXITY_ORDER.index(time) < COMPLEXITY_ORDER.index("O(N log N)"):
        time = "O(N log N)"
    grows = "append" in v.attr_calls or v.comprehensions or "sorted" in v.calls or "list" in v.calls or v.sized_lists
    space = "O(N)" if set(ds) - {"list"} or v.self_calls or grows else "O(1)"
    # Calls between functions are not inlined, so multi-function code is less certain.
    confidence = 0.8 if family != "simulation" and not v.self_calls and len(v.funcs) <= 1 else 0.6
    if v.self_calls:
        confidence = 0.5
    return time, space, confidence


def _quality(code, v):
    lines = [ln for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    short = sorted({n for n in v.names if len(n) == 1} - set("abijknmxyqr_"))
    dup = len(lines) - len({ln.strip() for ln in lines})
    longest = max((f["lines"] for f in v.funcs), default=len(lines))

    def clamp(x):
        return max(1, min(5, x))

    quality = {"readability": clamp(5 - max(0, v.max_nesting - 4)), "naming": clamp(5 - len(short)),
               "structure": clamp(5 - max(0, (longest - 30) // 10)), "duplication": clamp(5 - dup // 3)}
    issues = []
    if short:
        issues.append(f"의미가 드러나지 않는 한 글자 이름: {', '.join(short)}")
    if v.max_nesting > 4:
        issues.append(f"중첩 깊이 {v.max_nesting} — early return이나 helper 함수로 분리를 고려")
    if longest > 30:
        issues.append(f"긴 함수 ({longest}줄)")
    if dup > 3:
        issues.append(f"중복된 줄 {dup}개")
    return quality, issues


def analyze_code(code):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"error": f"SyntaxError line {e.lineno}: {e.msg}"}
    v = FeatureVisitor()
    v.visit(tree)
    family, ds = _detect(v, tree)
    time, space, confidence = _complexity(v, family, ds)
    quality, issues = _quality(code, v)
    strengths = []
    if max(v.max_loop_depth, v.hidden_depth) <= 1 and not v.self_calls:
        strengths.append("중첩 반복 없이 선형 이하로 처리")
    if min(quality.values()) >= 4:
        strengths.append("읽기 쉬운 구조와 이름")
    return {"algorithm_family": family, "data_structures": ds, "time_complexity": time,
            "space_complexity": space, "complexity_confidence": confidence, "code_quality": quality,
            "strengths": strengths, "issues": issues, "theory_topics": FAMILY_TOPICS.get(family, []),
            "features": {"for": v.for_count, "while": v.while_count, "max_loop_depth": v.max_loop_depth,
                         "hidden_linear_calls_in_loop": v.hidden_depth > v.max_loop_depth,
                         "recursive": bool(v.self_calls), "functions": [f["name"] for f in v.funcs]}}


def signature(code, entrypoint):
    """Argument names of the entrypoint in the past solution (used for the starter code only)."""
    try:
        for node in ast.walk(ast.parse(code)):
            if isinstance(node, ast.FunctionDef) and node.name == entrypoint:
                return [a.arg for a in node.args.args]
    except SyntaxError:
        pass
    return None


def compare_solutions(old, new):
    improved, regressed, unchanged = [], [], []
    for key, label in (("time_complexity", "시간"), ("space_complexity", "공간")):
        o, n = COMPLEXITY_ORDER.index(old[key]), COMPLEXITY_ORDER.index(new[key])
        if n < o:
            improved.append(f"{label}복잡도 {old[key]} → {new[key]}")
        elif n > o:
            regressed.append(f"{label}복잡도 {old[key]} → {new[key]}")
        else:
            unchanged.append(f"{label}복잡도 {old[key]}")
    changed = []  # different is neither better nor worse by itself
    if old["algorithm_family"] != new["algorithm_family"]:
        changed.append(f"접근 방식 {old['algorithm_family']} → {new['algorithm_family']}")
    else:
        unchanged.append(f"접근 방식 {new['algorithm_family']}")
    added = sorted(set(new["data_structures"]) - set(old["data_structures"]))
    removed = sorted(set(old["data_structures"]) - set(new["data_structures"]))
    if added or removed:
        changed.append("자료구조 " + ", ".join([f"+{d}" for d in added] + [f"-{d}" for d in removed]))
    for k, nv in new["code_quality"].items():
        ov = old["code_quality"][k]
        if nv != ov:
            (improved if nv > ov else regressed).append(f"{k} {ov} → {nv}")
    tradeoff = None
    if COMPLEXITY_ORDER.index(new["time_complexity"]) < COMPLEXITY_ORDER.index(old["time_complexity"]) and \
            COMPLEXITY_ORDER.index(new["space_complexity"]) > COMPLEXITY_ORDER.index(old["space_complexity"]):
        tradeoff = "time-space trade-off: 더 빠르지만 추가 메모리를 사용"
    return {"improved": improved, "regressed": regressed, "changed": changed, "unchanged": unchanged,
            "tradeoff": tradeoff}
