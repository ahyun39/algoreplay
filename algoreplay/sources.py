"""Problem sources (GitHub, local folder) and repository parsers.

Two repository layouts are recognised anywhere in the tree:

* BaekjoonHub  – `<dir>/README.md` ("# [Gold V] 제목 - 10026") + one `.py` solution (백준, 프로그래머스, ...)
* AlgoReplay   – `<dir>/metadata.json` + `problem.md` + `solution.py` (+ optional `tests.json`)

Plus `theory/*.md` documents.
"""
import ast
import base64
import hashlib
import html
import json
import re
import unicodedata
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests

from .analysis import FAMILY_TOPICS, analyze_code
from .config import env
from .db import now

# ---------------------------------------------------------------- sources
# A source is a dict: owner, name, branch, revision, files {path: sha}, read(path) -> str.
# ponytail: two adapters as plain functions; introduce a base class when a third source needs shared behaviour.


def github_source(owner, repo, branch=None, token=None):
    token = token or env("GITHUB_TOKEN")
    session = requests.Session()
    session.headers.update({"Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": env("GITHUB_API_VERSION", "2026-03-10")})
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    api = f"https://api.github.com/repos/{owner}/{repo}"

    def get_json(url, params=None):
        r = session.get(url, params=params, timeout=20)
        if r.status_code == 404:
            raise ValueError(f"{owner}/{repo} (branch {branch or 'default'}) not found, or the token cannot read it.")
        if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
            raise ValueError("GitHub API rate limit exceeded. Set GITHUB_TOKEN to raise the limit.")
        r.raise_for_status()
        return r.json()

    branch = branch or get_json(api)["default_branch"]
    commit = get_json(f"{api}/branches/{branch}")["commit"]["sha"]
    tree = get_json(f"{api}/git/trees/{commit}", {"recursive": "1"})
    if tree.get("truncated"):
        raise ValueError("Repository tree is too large for a recursive listing (GitHub limit).")
    files = {t["path"]: t["sha"] for t in tree["tree"] if t["type"] == "blob"}

    def read(path):
        # raw.githubusercontent.com is not subject to the 60 req/h anonymous API limit; pinned to the commit.
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{requests.utils.quote(path)}"
        r = session.get(url, timeout=20)
        if r.ok:
            return r.content.decode("utf-8", errors="replace")
        blob = get_json(f"{api}/git/blobs/{files[path]}")  # fallback, e.g. some private-repo setups
        return base64.b64decode(blob["content"]).decode("utf-8", errors="replace")

    return {"owner": owner, "name": repo, "branch": branch, "revision": commit, "files": files, "read": read}


def local_source(directory):
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")
    files = {p.relative_to(root).as_posix(): hashlib.sha1(p.read_bytes()).hexdigest()
             for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts}
    return {"owner": "local", "name": str(root), "branch": None, "revision": None, "files": files,
            "read": lambda path: (root / path).read_text(encoding="utf-8", errors="replace")}


# ---------------------------------------------------------------- HTML -> markdown

def _strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def _cells(row):
    return [_strip_tags(c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S | re.I)]


def table_rows(table_html):
    return [c for c in (_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)) if c]


def html_to_markdown(text):
    """Small converter for problem statements; unknown tags are dropped, never rendered as HTML."""
    blocks = []

    def keep(md):
        blocks.append(md)
        return f"\x00{len(blocks) - 1}\x00"

    def pre(m):
        return keep("\n```\n" + _strip_tags(m.group(1)).strip("\n") + "\n```\n")

    def table(m):
        rows = table_rows(m.group(0))
        if not rows:
            return ""
        width = max(map(len, rows))
        rows = [[c.replace("|", "\\|").replace("\n", " ") for c in r] + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return keep("\n" + "\n".join(lines) + "\n")

    s = text.replace("\r", "")
    s = re.sub(r"<pre[^>]*>(.*?)</pre>", pre, s, flags=re.S | re.I)
    s = re.sub(r"<table.*?</table>", table, s, flags=re.S | re.I)
    s = re.sub(r"<code[^>]*>(.*?)</code>", lambda m: keep("`" + _strip_tags(m.group(1)) + "`"), s, flags=re.S | re.I)
    s = re.sub(r"<h\d[^>]*>(.*?)</h\d>", lambda m: "\n\n#### " + _strip_tags(m.group(1)).strip() + "\n\n", s,
               flags=re.S | re.I)
    s = re.sub(r"<img[^>]*>", "*(이미지 생략 — 원문 링크 참고)*", s, flags=re.I)
    s = re.sub(r"<sup[^>]*>(.*?)</sup>", r"^\1", s, flags=re.S | re.I)
    s = re.sub(r"<sub[^>]*>(.*?)</sub>", r"_\1", s, flags=re.S | re.I)
    s = re.sub(r"<li[^>]*>", "\n- ", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "  \n", s, flags=re.I)
    s = re.sub(r"</(p|ul|ol|div|blockquote)>", "\n\n", s, flags=re.I)
    s = _strip_tags(s).replace("*", "\\*")
    s = re.sub(r"\x00(\d+)\x00", lambda m: blocks[int(m.group(1))], s)
    s = re.sub(r"[ \t]+\n", lambda m: "  \n" if m.group(0).startswith("  ") else "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


# ---------------------------------------------------------------- topics

# (keyword in tag, canonical topic). Canonical topics are the names of the theory documents.
TOPIC_KEYWORDS = [
    ("너비 우선", "bfs"), ("bfs", "bfs"), ("깊이 우선", "dfs"), ("dfs", "dfs"),
    ("다이나믹", "dynamic-programming"), ("동적계획", "dynamic-programming"), ("dynamic", "dynamic-programming"),
    ("그리디", "greedy"), ("탐욕", "greedy"), ("greedy", "greedy"),
    ("이분 탐색", "binary-search"), ("이분탐색", "binary-search"), ("매개 변수 탐색", "binary-search"),
    ("우선순위 큐", "heap"), ("힙", "heap"), ("heap", "heap"),
    ("해시", "hashmap"), ("hash", "hashmap"), ("스택", "stack"), ("큐", "queue"), ("덱", "queue"),
    ("정렬", "sorting"), ("sort", "sorting"), ("브루트포스", "brute-force"), ("완전탐색", "brute-force"),
    ("백트래킹", "backtracking"), ("두 포인터", "two-pointer"), ("슬라이딩 윈도우", "sliding-window"),
    ("누적 합", "prefix-sum"), ("데이크스트라", "shortest-path"), ("최단 경로", "shortest-path"),
    ("플로이드", "shortest-path"), ("분리 집합", "union-find"), ("트리", "tree"), ("그래프", "graph"),
    ("구현", "implementation"), ("시뮬레이션", "implementation"), ("문자열", "string"), ("파싱", "string"),
    ("수학", "math"), ("정수론", "math"), ("사칙연산", "math"), ("조합론", "math"), ("재귀", "recursion"),
    ("분할 정복", "recursion"),
]


THEORY_NAMES = {t for _, t in TOPIC_KEYWORDS}


def topics_for(tags, reference_code=""):
    topics = []
    for tag in tags:
        t = tag.lower()
        slug = re.sub(r"[\s_]+", "-", t)
        if slug in THEORY_NAMES and slug not in topics:  # tag already uses a canonical name, e.g. "binary-search"
            topics.append(slug)
        for kw, topic in TOPIC_KEYWORDS:
            if kw in t and topic not in topics and not (topic == "queue" and "우선순위" in t):
                topics.append(topic)
    if not topics and reference_code:  # no usable tags (e.g. 프로그래머스 연습문제): infer from the past solution
        topics = FAMILY_TOPICS.get(analyze_code(reference_code).get("algorithm_family"), [])[:1]
    return topics


def difficulty_of(tier):
    t = (tier or "").lower()
    if t.startswith(("bronze", "level 0", "level 1", "lv0", "lv1", "d1", "d2", "easy", "unrated")):
        return "easy"
    if t.startswith(("silver", "level 2", "lv2", "d3", "d4", "medium")):
        return "medium"
    return "hard"


# ---------------------------------------------------------------- parsers
# Each parser returns (problem_dict, None) or (None, reason_skipped).

HEADER = re.compile(r"^#\s*\[(?P<tier>[^\]]+)\]\s*(?P<title>.+)\s+-\s+(?P<id>\d+)\s*$", re.M)
LINK = re.compile(r"\[문제 링크\]\((?P<url>[^)]+)\)")


def _sections(md):
    parts = re.split(r"^###\s*(.+?)\s*$", md, flags=re.M)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def _literal(cell):
    text = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", re.sub(r"\bnull\b", "None", cell)))
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return cell  # plain text value such as an unquoted string


def _parse_date(text):
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(\d{1,2}):(\d{2}):(\d{2})", text or "")
    try:  # BaekjoonHub occasionally writes impossible dates such as "02월 00일"
        return datetime(*map(int, m.groups())).isoformat() if m else None
    except ValueError:
        return None


def _programmers_examples(statement_html):
    """Tables under the "입출력 예" heading (also 예제 / 예시 / [입출력 예]).
    Horizontal: one row per example (args..., result). Vertical ("매개변수 | 값"): one table per example."""
    heading = re.search(r"<h\d[^>]*>[^<]*입출력\s*예[^<]*</h\d>", statement_html)
    if not heading:
        return []
    rest = statement_html[heading.end():]
    stop = re.search(r"<h\d[^>]*>[^<]*설명", rest)  # "입출력 예 설명" ends the examples
    tables = [table_rows(t) for t in re.findall(r"<table.*?</table>", rest[:stop.start()] if stop else rest,
                                                re.S | re.I)]
    tests = []
    for rows in tables:
        if len(rows) < 2:
            continue
        if rows[0][0] in ("매개변수", "파라미터", "변수"):
            cases = [[r[-1] for r in rows[1:]]]
        else:
            cases = [r for r in rows[1:] if len(r) == len(rows[0])]
        for case in cases:
            if len(case) >= 2:
                tests.append({"name": f"예제 {len(tests) + 1}", "input": [_literal(c) for c in case[:-1]],
                              "expected": _literal(case[-1])})
    return tests


def parse_baekjoonhub(readme, solution, dir_path):
    header = HEADER.search(readme)
    if not header:
        return None, "README.md is not in BaekjoonHub format"
    sec = _sections(readme)
    link = LINK.search(readme)
    url = link.group("url") if link else None
    path = unicodedata.normalize("NFC", dir_path)
    if (url and "acmicpc.net" in url) or path.startswith(("백준", "baekjoon")):
        source = "boj"
    elif (url and "programmers.co.kr" in url) or path.startswith(("프로그래머스", "programmers")):
        source = "programmers"
    else:
        source = re.sub(r"[^a-z0-9]+", "-", path.split("/")[0].lower()).strip("-") or "bjh"

    tests = []
    if source == "programmers":
        judge = "function"
        tags = [t.strip() for t in sec.get("구분", "").split(">")[1:] if t.strip() not in ("연습문제", "")]
        statement = html_to_markdown(sec.get("문제 설명", ""))
        tests = _programmers_examples(sec.get("문제 설명", ""))
    else:
        judge = "stdio"
        tags = [t.strip() for t in sec.get("분류", "").split(",") if t.strip()]
        statement = html_to_markdown(sec.get("문제 설명", ""))
        for name in ("입력", "출력"):
            if sec.get(name):
                statement += f"\n\n### {name}\n\n" + html_to_markdown(sec[name])

    title = unicodedata.normalize("NFC", header.group("title").strip())
    return {"problem_key": f"{source}-{header.group('id')}", "source": source, "external_id": header.group("id"),
            "title": title, "statement": statement, "tier": header.group("tier").strip(),
            "difficulty": difficulty_of(header.group("tier")), "judge": judge, "entrypoint": "solution",
            "tags": tags, "topics": topics_for(tags, solution), "hints": [], "url": url,
            "solved_at": _parse_date(sec.get("제출 일자")), "past_performance": sec.get("성능 요약"),
            "reference_solution": solution, "tests": tests}, None


# ---------------------------------------------------------------- LeetHub (LeetCode) SQL
# README.md starts with <h2><a href="https://leetcode.com/problems/…">175. Title</a></h2><h3>Easy</h3>.
# Tests come from the README itself: the "Table: X" schema boxes plus each example's Input / Output boxes.

LEETHUB = re.compile(r'<h2><a href="(?P<url>https://leetcode\.com/problems/[^"]+)">(?P<id>\d+)\.\s*(?P<title>.+?)</a>'
                     r'</h2>\s*<h3>(?P<level>\w+)</h3>')
SQL_TOPICS = [("sql-join", r"\bJOIN\b"), ("sql-aggregate", r"\bGROUP\s+BY\b|\b(COUNT|SUM|AVG|MIN|MAX)\s*\("),
              ("sql-window", r"\bOVER\s*\("), ("sql-subquery", r"\(\s*SELECT\b|^\s*WITH\b"),
              ("sql-dml", r"^\s*(DELETE|UPDATE)\b")]


def _box(block):
    """ASCII table (+---+ / | a | b |) -> (header, rows). "null" cells become None."""
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in block.splitlines() if line.strip().startswith("|") and not re.fullmatch(r"[|+\-\s]+", line)]
    if not rows:
        return None
    return rows[0], [[None if c.lower() == "null" else c for c in r] for r in rows[1:]]


def _sql_examples(plain):
    boxes = r"((?:[ \t]*[+|].*(?:\n|$))+)"
    schema = {m.group(1): [(r[0], r[1]) for r in _box(m.group(2))[1]]
              for m in re.finditer(r"Table:\s*(\w+)\s*\n+" + boxes, plain) if _box(m.group(2))}
    ordered = bool(re.search(r"\border(ed)?\s+by\b", plain, re.I)) and not re.search(r"any order", plain, re.I)
    dml = re.search(r"\b(DELETE|UPDATE) statement", plain, re.I)
    tests = []
    for chunk in re.split(r"Example \d+:", plain)[1:]:
        if "Input:" not in chunk or "Output:" not in chunk:
            continue
        given, out = chunk.split("Input:", 1)[1].split("Output:", 1)
        out = _box(re.split(r"Explanation:", out)[0])
        tables = []
        for m in re.finditer(r"(\w+)(?: table:)?[ \t]*\n" + boxes, given):  # "Person table:" or just "Visits"
            header, rows = _box(m.group(2))
            types = dict(schema.get(m.group(1), []))
            tables.append({"name": m.group(1), "columns": [[c, types.get(c, "varchar")] for c in header], "rows": rows})
        if not tables or not out:
            continue
        target = next((t["name"] for t in tables if [c.lower() for c, _ in t["columns"]] ==
                       [c.lower() for c in out[0]]), tables[0]["name"]) if dml else None
        tests.append({"name": f"Example {len(tests) + 1}", "input": {"tables": tables, "result_table": target},
                      "expected": {"columns": out[0], "rows": out[1], "ordered": ordered}})
    return tests


def parse_leethub(readme, solution, filename):
    header = LEETHUB.search(readme)
    if not header:
        return None
    if not filename.endswith(".sql"):
        return None, "LeetCode Python(class Solution) 문제는 아직 지원하지 않음"
    body = readme[header.end():]
    plain = html.unescape(re.sub(r"<[^>]+>", "", body))
    level = header.group("level")
    topics = [t for t, rx in SQL_TOPICS if re.search(rx, solution, re.I | re.M)] or ["sql"]
    mysql = re.search(r"\bAS\s+'|DATE_FORMAT|DATE_SUB|IFNULL|GROUP_CONCAT|INTERVAL\s+\d+\s+DAY", solution, re.I)
    note = "\n\n> 채점: PostgreSQL 16 · 예제 표로 테이블을 만들어 결과 표를 비교합니다."
    note += "\n\n> ⚠️ 과거 풀이는 MySQL 문법이라 PostgreSQL 채점에서 그대로 실행되지 않을 수 있습니다." * bool(mysql)
    return {"problem_key": f"leetcode-{header.group('id')}", "source": "leetcode", "external_id": header.group("id"),
            "title": html.unescape(header.group("title")), "tier": level,
            "statement": html_to_markdown(body) + note,
            "difficulty": level.lower() if level.lower() in ("easy", "medium", "hard") else "medium",
            "judge": "sql", "entrypoint": "", "tags": ["SQL"], "topics": topics, "hints": [],
            "url": header.group("url"), "solved_at": None, "past_performance": None,
            "reference_solution": solution, "tests": _sql_examples(plain)}, None


# ---------------------------------------------------------------- loose files (notebooks / plain code)
# One file = one problem: Jupyter notebooks (.ipynb), .txt or extensionless code files outside the two
# structured formats (e.g. older Colab exports). They carry code but usually no problem statement.

LOOSE_EXTENSIONS = {"ipynb", "txt", ""}
FOLDER_SOURCES = {"baekjoon": "boj", "백준": "boj", "boj": "boj", "programmers": "programmers",
                  "프로그래머스": "programmers", "codility": "codility", "sw_expert_academy": "swea", "swea": "swea"}


def _clean_code(text):
    """Make a scraped code file parseable: `// 한글 설명` comments become `#`, trailing notes are cut."""
    # ponytail: "//" followed by Hangul on the same line is treated as a comment, not floor division
    text = re.sub(r"(^|[\s:])//(?=.*[가-힣])", r"\1#", text.replace("\r", ""), flags=re.M)
    text = re.sub(r"^(\s*)//", r"\1#", text, flags=re.M)
    lines = text.rstrip().splitlines()
    while lines:
        code = "\n".join(lines).rstrip()
        if code and _parses(code):
            return code + "\n"
        lines.pop()  # e.g. "**다른 답안**" notes after the code
    return None


def _parses(code):
    with warnings.catch_warnings():  # old code may use invalid escapes like "\d" (SyntaxWarning)
        warnings.simplefilter("ignore")
        try:
            return ast.parse(code)
        except SyntaxError:
            return None


def _notebook_parts(text):
    nb = json.loads(text)
    cells = nb.get("cells", [])
    markdown = ["".join(c.get("source", [])) for c in cells if c.get("cell_type") == "markdown"]
    markdown = [m for m in markdown if "colab-badge" not in m and m.strip()]
    codes = []
    for c in cells:
        if c.get("cell_type") != "code":
            continue
        out = next(("".join(o["data"]["text/plain"]) for o in c.get("outputs", [])
                    if o.get("output_type") == "execute_result" and "text/plain" in o.get("data", {})), None)
        codes.append(("".join(c.get("source", [])), out))
    return markdown, codes


def _tests_from_outputs(codes):
    """`solution(<literals>)` as the last line of a cell + its saved output -> a test case."""
    tests = []
    for src, out in codes:
        tree = _parses(src)
        if not tree or not tree.body:
            continue
        last = tree.body[-1]
        if out is None or not (isinstance(last, ast.Expr) and isinstance(last.value, ast.Call)
                               and getattr(last.value.func, "id", None) == "solution"):
            continue
        try:
            args = [ast.literal_eval(a) for a in last.value.args]
            expected = ast.literal_eval(out)
        except (ValueError, SyntaxError):
            continue
        tests.append({"name": f"노트북 예제 {len(tests) + 1}", "input": args, "expected": expected})
    return tests


def parse_loose(path, text):
    parts = unicodedata.normalize("NFC", path).split("/")
    folder_source = FOLDER_SOURCES.get(parts[0].lower(), re.sub(r"[^a-z0-9]+", "-", parts[0].lower()).strip("-"))
    stem = parts[-1].rsplit(".", 1)[0] if "." in parts[-1] else parts[-1]
    if re.search(r"_\d+개(\(.*\))?$", stem):  # "연습문제_3개", "연습문제_2개(다소간단)"
        return None, "한 파일에 여러 문제가 있어 문제 하나로 나눌 수 없음"

    notes, tests, judge = [], [], None
    if path.endswith(".ipynb"):
        try:
            notes, codes = _notebook_parts(text)
        except (ValueError, KeyError):
            return None, "노트북 파일을 읽을 수 없음"
        if any("def solution" in src for src, _ in codes):
            judge = "function"
            code = "\n\n".join(src for src, _ in codes if "input(" not in src or "def solution" in src)
            code = re.sub(r"^(print\()?solution\(.*$\n?", "", code, flags=re.M)  # sample calls -> tests below
            tests = _tests_from_outputs(codes)
        else:
            stdin_cells = [src for src, _ in codes if "input(" in src]
            judge = "stdio" if stdin_cells else None
            code = stdin_cells[-1] if stdin_cells else ""  # the last attempt is usually the final answer
    else:
        code = text
        judge = "function" if "def solution" in text else "stdio" if "input(" in text else None
    if judge is None:
        return None, None  # not a solution file (e.g. requirements.txt): ignore silently
    code = _clean_code(code)
    if not code:
        return None, "Python 코드로 해석할 수 없음"

    category = number = None
    if folder_source == "programmers":  # "<category>_<title>"; the leading digits are a year, not an id
        if "_" not in stem and len(parts) > 3 and not re.fullmatch(r"Lv_?\d", parts[-2]):
            stem = parts[-2]  # "…/2018_KAKAO_BLIND_RECRUITMENT_[1차]캐시/2018 KAKAO BLIND RECRUITMENT.ipynb"
        if "_" not in stem:
            title = stem
        elif " " in stem or stem.count("_") == 1:  # "해시_위장", "2019 KAKAO BLIND RECRUITMENT_오픈채팅방"
            category, title = (s.strip() for s in stem.split("_", 1))
        else:  # all-underscore names ("2020_KAKAO_INTERNSHIP_키패드누르기"): drop leading category words
            title = re.sub(r"^((\d{4}|[A-Z]+|카카오|개발자|겨울|인턴십|채용연계형|연습문제)_)+", "", stem)
    else:
        number = re.match(r"^(\d+)", stem)
        title = re.sub(r"^\d+[_.\s-]*", "", stem)
    title = title.replace("_", " ").strip()
    if category and re.fullmatch(r"\d+번", title):  # "PCCP 모의고사 1회_1번"
        title = f"{category} {title}"
    heading = next((m.group(1) for n in notes if (m := re.match(r"\s*#+\s*\d+\.\s*(.+)", n))), "")
    if heading:  # numbered heading, e.g. "## 1204. [S/W 문제해결 기본] 1일차 - 최빈수 구하기 D2"
        title = re.sub(r"\s+D\d$", "", heading.strip()).strip() or title
    title = title or (f"{number.group(1)}번 문제" if number else stem)
    link = re.search(r"\]\((https?://[^)]+)\)", "\n".join(notes))
    url = link.group(1) if link else (f"https://www.acmicpc.net/problem/{number.group(1)}"
                                      if folder_source == "boj" and number else None)
    tier = next((p for p in parts[1:-1] if re.fullmatch(r"(D|Lv_?)\d", p, re.I)), None)
    tags = [t for t in (category, parts[1] if len(parts) > 2 else None) if t and t not in (tier, "Solutions", "연습문제")]

    statement = (f"### {title}\n\n> 이 문제는 저장소에 **문제 설명이 없습니다** (코드만 저장된 파일). "
                 "원문을 확인한 뒤 풀어 보세요.\n\n")
    statement += f"[원문 보기]({url})\n" if url else f"원문 검색어: `{title}`\n"
    statement += "\n채점 방식: " + ("`solution()` 반환값 비교" if judge == "function" else "표준 입출력") + "\n"
    if notes:  # personal study notes reveal the approach: keep them with the past solution, shown after submitting
        code = "".join(f"# {line}\n" for n in notes for line in n.splitlines()) + "\n" + code
    key = f"{folder_source}-{number.group(1)}" if number else f"{folder_source}-{_slug(title)}"
    return {"problem_key": key, "source": folder_source, "external_id": number.group(1) if number else None,
            "title": title, "statement": statement, "tier": tier,
            "difficulty": difficulty_of(tier) if tier else "medium", "judge": judge, "entrypoint": "solution",
            "tags": tags, "topics": topics_for(tags, code), "hints": [], "url": url, "solved_at": None,
            "past_performance": None, "reference_solution": code, "tests": tests}, None


def _slug(text):
    return re.sub(r"[^\w]+", "-", unicodedata.normalize("NFC", text).lower()).strip("-")


def parse_native(meta_text, statement, solution, tests_text):
    meta = json.loads(meta_text)
    judge = meta.get("judge", "function")
    tests = []
    for i, t in enumerate(json.loads(tests_text) if tests_text else [], 1):
        tests.append({"name": t.get("name", f"test {i}"),
                      "input": t["args"] if judge == "function" else t["input"], "expected": t["expected"]})
    tags = meta.get("tags", [])
    return {"problem_key": meta["problem_id"], "source": meta.get("source") or "native", "external_id": None,
            "title": meta.get("title", meta["problem_id"]), "statement": statement,
            "tier": meta.get("difficulty"), "difficulty": difficulty_of(meta.get("difficulty")), "judge": judge,
            "entrypoint": meta.get("entrypoint", "solution"), "tags": tags,
            "topics": meta.get("topics") or topics_for(tags, solution), "hints": meta.get("hints", []),
            "url": meta.get("url"), "solved_at": meta.get("solved_at"), "past_performance": None,
            "reference_solution": solution, "tests": tests}, None


# ---------------------------------------------------------------- sync

def _candidates(files):
    """Group files by directory and decide which directories look like problems (no network access)."""
    by_dir = {}
    for path in files:
        if "/" in path:
            d, name = path.rsplit("/", 1)
            by_dir.setdefault(d, []).append(name)
    found, skipped = {}, []
    for d, names in sorted(by_dir.items()):
        if "metadata.json" in names:
            needed = ["metadata.json", "problem.md", "solution.py"] + (["tests.json"] if "tests.json" in names else [])
            if all(n in names for n in needed[:3]):
                found[d] = ("native", [f"{d}/{n}" for n in needed])
            else:
                skipped.append((d, "metadata.json without problem.md / solution.py"))
        elif "README.md" in names and d.split("/")[0] != "theory":
            py = sorted(n for n in names if n.endswith((".py", ".sql")))  # .sql: LeetHub only, see fetch()
            if py:
                found[d] = ("bjh", [f"{d}/README.md", f"{d}/{py[0]}"])
            elif any(n.rsplit(".", 1)[-1] in ("java", "cpp", "c", "js", "kt", "cs", "swift") for n in names):
                skipped.append((d, "no Python solution (only Python is supported)"))
    for d, names in sorted(by_dir.items()):  # loose code files, outside the directories claimed above
        if d in found or any(d.startswith(f + "/") for f in found) or d.split("/")[0] in ("theory", ".github"):
            continue
        for n in sorted(names):
            if not n.startswith(".") and (n.rsplit(".", 1)[-1].lower() if "." in n else "") in LOOSE_EXTENSIONS:
                found[f"{d}/{n}"] = ("loose", [f"{d}/{n}"])
    return found, skipped


def sync(db, src, progress=None):
    """Incremental sync: a problem is re-fetched only when the SHA of one of its files changed."""
    ts = now()
    db.execute("INSERT INTO repositories(owner,name,default_branch,created_at,updated_at) VALUES(?,?,?,?,?) "
               "ON CONFLICT(owner,name) DO UPDATE SET default_branch=excluded.default_branch, "
               "updated_at=excluded.updated_at", (src["owner"], src["name"], src["branch"], ts, ts))
    repo_id = db.execute("SELECT id FROM repositories WHERE owner=? AND name=?",
                         (src["owner"], src["name"])).fetchone()[0]
    files = src["files"]
    found, skipped = _candidates(files)
    known = {r["github_path"]: r["github_sha"] for r in
             db.execute("SELECT github_path, github_sha FROM problems WHERE repository_id=?", (repo_id,))}
    shas = {d: hashlib.sha1("".join(files[p] for p in paths).encode()).hexdigest() for d, (_, paths) in found.items()}
    order = {"native": 0, "bjh": 1, "loose": 2}  # structured formats first: they win over a loose copy
    todo = sorted((d for d in found if known.get(d) != shas[d]), key=lambda d: (order[found[d][0]], d))
    stats = {"added": 0, "updated": 0, "unchanged": len(found) - len(todo), "removed": 0, "skipped": skipped}

    def fetch(d):
        kind, paths = found[d]
        texts = [src["read"](p) for p in paths]
        try:
            if kind == "native":
                return d, parse_native(texts[0], texts[1], texts[2], texts[3] if len(texts) > 3 else None)
            if kind == "loose":
                return d, parse_loose(d, texts[0])
            leethub = parse_leethub(texts[0], texts[1], paths[1])
            if leethub:
                return d, leethub
            if paths[1].endswith(".sql"):
                return d, (None, "no Python solution (SQL is supported for LeetCode/LeetHub only)")
            return d, parse_baekjoonhub(texts[0], texts[1], d)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return d, (None, f"parse error: {e}")

    with ThreadPoolExecutor(max_workers=16) as pool:
        for n, (d, (prob, reason)) in enumerate(pool.map(fetch, todo), 1):
            if progress:
                progress(n / max(len(todo), 1), unicodedata.normalize("NFC", d))
            if not prob:
                if reason:  # None = not a solution file at all (e.g. requirements.txt)
                    skipped.append((d, reason))
                continue
            owner_path = db.execute("SELECT github_path FROM problems WHERE repository_id=? AND problem_key=?",
                                    (repo_id, prob["problem_key"])).fetchone()
            if found[d][0] == "loose" and not owner_path:  # unnumbered file: match an existing problem by title
                owner_path = db.execute("SELECT github_path FROM problems WHERE repository_id=? AND source=? "
                                        "AND REPLACE(title,' ','')=? AND github_path!=?",
                                        (repo_id, prob["source"], prob["title"].replace(" ", ""), d)).fetchone()
            if owner_path and owner_path[0] != d and owner_path[0] in found:
                skipped.append((d, f"duplicate of {owner_path[0]}"))
                continue
            _upsert(db, repo_id, d, shas[d], prob, ts)
            stats["updated" if d in known or owner_path else "added"] += 1

    # Removed from the repo: delete only if never attempted, so personal history survives.
    for (pid, path) in db.execute("SELECT id, github_path FROM problems WHERE repository_id=?", (repo_id,)).fetchall():
        if path not in found and not db.execute("SELECT 1 FROM attempts WHERE problem_id=?", (pid,)).fetchone():
            db.execute("DELETE FROM problems WHERE id=?", (pid,))
            stats["removed"] += 1

    db.execute("DELETE FROM theory WHERE repository_id=?", (repo_id,))
    for path in files:
        parts = path.split("/")
        if "theory" in parts[:-1] and path.endswith(".md"):
            db.execute("INSERT OR REPLACE INTO theory(repository_id,name,content) VALUES(?,?,?)",
                       (repo_id, Path(path).stem, src["read"](path)))
    db.execute("UPDATE repositories SET last_sync_sha=? WHERE id=?", (src["revision"], repo_id))
    db.commit()
    return stats


def _upsert(db, repo_id, path, sha, p, ts):
    db.execute(
        "INSERT INTO problems(repository_id,problem_key,source,external_id,title,statement,difficulty,tier,judge,"
        "entrypoint,tags_json,topics_json,hints_json,url,solved_at,past_performance,github_path,github_sha,"
        "reference_solution,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(repository_id,problem_key) DO UPDATE SET source=excluded.source, title=excluded.title, "
        "statement=excluded.statement, difficulty=excluded.difficulty, tier=excluded.tier, judge=excluded.judge, "
        "entrypoint=excluded.entrypoint, tags_json=excluded.tags_json, topics_json=excluded.topics_json, "
        "hints_json=excluded.hints_json, url=excluded.url, solved_at=excluded.solved_at, "
        "past_performance=excluded.past_performance, github_path=excluded.github_path, "
        "github_sha=excluded.github_sha, reference_solution=excluded.reference_solution, "
        "updated_at=excluded.updated_at",
        (repo_id, p["problem_key"], p["source"], p["external_id"], p["title"], p["statement"], p["difficulty"],
         p["tier"], p["judge"], p["entrypoint"], json.dumps(p["tags"], ensure_ascii=False),
         json.dumps(p["topics"]), json.dumps(p["hints"], ensure_ascii=False), p["url"], p["solved_at"],
         p["past_performance"], path, sha, p["reference_solution"], ts, ts))
    pid = db.execute("SELECT id FROM problems WHERE repository_id=? AND problem_key=?",
                     (repo_id, p["problem_key"])).fetchone()[0]
    db.execute("DELETE FROM tests WHERE problem_id=? AND origin='repo'", (pid,))
    for t in p["tests"]:
        db.execute("INSERT INTO tests(problem_id,name,input_json,expected_json,origin,created_at) "
                   "VALUES(?,?,?,?,'repo',?)", (pid, t["name"], json.dumps(t["input"], ensure_ascii=False),
                                                json.dumps(t["expected"], ensure_ascii=False), ts))
