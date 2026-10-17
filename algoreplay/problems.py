"""Problem and test-case queries (the "tools" the workflow calls)."""
import json

from .analysis import signature
from .db import now

_LIST_COLUMNS = "id, problem_key, source, title, difficulty, tier, judge, tags_json, topics_json, solved_at"


def _row(r):
    p = dict(r)
    for k in ("tags", "topics", "hints"):
        if f"{k}_json" in p:
            p[k] = json.loads(p.pop(f"{k}_json"))
    return p


def list_problems(db, query=None, source=None, difficulty=None, topic=None, status=None):
    """status: None | 'new' (never attempted) | 'passed' | 'failed' (latest attempt)."""
    rows = [_row(r) for r in db.execute(
        f"SELECT {_LIST_COLUMNS}, (SELECT status FROM attempts a WHERE a.problem_id=p.id ORDER BY a.id DESC LIMIT 1)"
        " AS last_status, (SELECT COUNT(*) FROM tests t WHERE t.problem_id=p.id) AS test_count "
        "FROM problems p ORDER BY source, CAST(external_id AS INTEGER), title")]
    q = (query or "").strip().lower()
    return [p for p in rows
            if (not q or q in p["title"].lower() or q in p["problem_key"].lower())
            and (not source or p["source"] == source)
            and (not difficulty or p["difficulty"] == difficulty)
            and (not topic or topic in p["topics"])
            and (status is None or (status == "new" and p["last_status"] is None)
                 or (status == "passed" and p["last_status"] == "PASS")
                 or (status == "failed" and p["last_status"] not in (None, "PASS")))]


def get_problem(db, problem_id):
    """Replay view. The reference (past) solution is deliberately not included."""
    r = db.execute(f"SELECT {_LIST_COLUMNS}, statement, entrypoint, hints_json, url, past_performance "
                   "FROM problems WHERE id=?", (problem_id,)).fetchone()
    return _row(r) if r else None


def get_old_solution(db, problem_id):
    return db.execute("SELECT reference_solution FROM problems WHERE id=?", (problem_id,)).fetchone()[0]


def starter_code(db, problem_id):
    p = db.execute("SELECT judge, entrypoint, reference_solution FROM problems WHERE id=?", (problem_id,)).fetchone()
    if p["judge"] == "sql":
        return "-- PostgreSQL\nSELECT\n"
    if p["judge"] == "stdio":
        return "import sys\ninput = sys.stdin.readline\n\n"
    args = signature(p["reference_solution"], p["entrypoint"]) or []
    return f"def {p['entrypoint']}({', '.join(args)}):\n    answer = None\n    return answer\n"


def get_tests(db, problem_id):
    return [{"id": r["id"], "name": r["name"], "origin": r["origin"], "input": json.loads(r["input_json"]),
             "expected": json.loads(r["expected_json"])}
            for r in db.execute("SELECT * FROM tests WHERE problem_id=? ORDER BY id", (problem_id,))]


def add_tests(db, problem_id, tests, origin="user"):
    """tests: [{"input", "expected"}]. Named sequentially after the existing tests."""
    n = db.execute("SELECT COUNT(*) FROM tests WHERE problem_id=?", (problem_id,)).fetchone()[0]
    for i, t in enumerate(tests, n + 1):
        db.execute("INSERT INTO tests(problem_id,name,input_json,expected_json,origin,created_at) VALUES(?,?,?,?,?,?)",
                   (problem_id, t.get("name") or f"{origin} {i}", json.dumps(t["input"], ensure_ascii=False),
                    json.dumps(t["expected"], ensure_ascii=False), origin, now()))
    db.commit()


def delete_test(db, test_id):
    db.execute("DELETE FROM tests WHERE id=? AND origin!='repo'", (test_id,))
    db.commit()


def sources(db):
    return [r[0] for r in db.execute("SELECT DISTINCT source FROM problems ORDER BY source")]


def topics(db):
    return sorted({t for (j,) in db.execute("SELECT topics_json FROM problems") for t in json.loads(j)})
