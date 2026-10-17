"""Attempts, learning events, weakness profile and next-problem recommendation.

The scores are internal heuristics for choosing what to review next, not a measure of ability.
"""
import json
from datetime import UTC, datetime, timedelta

from .db import now

DIFFICULTY = {"easy": 0, "medium": 1, "hard": 2}
JUDGED = ("PASS", "FAIL", "TIMEOUT", "RUNTIME_ERROR", "SYNTAX_ERROR")


def save_attempt(db, problem_id, code, result, analysis=None, comparison=None, report=None):
    ts = now()
    attempt_id = db.execute(
        "INSERT INTO attempts(problem_id,code,submitted_at,status,runtime_ms,peak_memory_kb,passed_count,"
        "failed_count,stdout,stderr,results_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (problem_id, code, ts, result["status"], result.get("runtime_ms"), result.get("peak_memory_kb"),
         result.get("passed"), result.get("failed"), result.get("stdout"), result.get("stderr"),
         json.dumps(result.get("results", []), ensure_ascii=False))).lastrowid
    if analysis and "error" not in analysis:
        db.execute(
            "INSERT INTO analyses(attempt_id,complexity_time,complexity_space,complexity_confidence,"
            "algorithm_family,data_structures_json,code_quality_json,bugs_json,theory_topics_json,comparison_json,"
            "report_markdown,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (attempt_id, analysis["time_complexity"], analysis["space_complexity"],
             analysis["complexity_confidence"], analysis["algorithm_family"], json.dumps(analysis["data_structures"]),
             json.dumps(analysis["code_quality"]), json.dumps(analysis["issues"], ensure_ascii=False),
             json.dumps(analysis["theory_topics"]), json.dumps(comparison, ensure_ascii=False), report, ts))

    if result["status"] in JUDGED:  # only runner-decided outcomes count towards the profile
        topics = json.loads(db.execute("SELECT topics_json FROM problems WHERE id=?", (problem_id,)).fetchone()[0])
        passed = result["status"] == "PASS"
        for topic in topics:
            _event(db, problem_id, attempt_id, "pass" if passed else "fail", topic, 1.0 if passed else 0.0,
                   {"status": result["status"]}, ts)
            if not passed:
                fails = db.execute("SELECT COUNT(*) FROM learning_events WHERE topic=? AND event_type='fail'",
                                   (topic,)).fetchone()[0]
                if fails >= 2:
                    _event(db, problem_id, attempt_id, "repeated_mistake", topic, min(1.0, fails / 5),
                           {"reason": f"{topic}에서 {result['status']} 반복", "count": fails}, ts)
    db.commit()
    return attempt_id


def _event(db, problem_id, attempt_id, kind, topic, score, detail, ts):
    db.execute("INSERT INTO learning_events(problem_id,attempt_id,event_type,topic,score,detail_json,created_at) "
               "VALUES(?,?,?,?,?,?,?)",
               (problem_id, attempt_id, kind, topic, score, json.dumps(detail, ensure_ascii=False), ts))


def get_learning_profile(db):
    """weakness = failure_rate*.45 + repeated_mistake_rate*.35 + recent_failure*.20"""
    profile = {}
    for (topic,) in db.execute("SELECT DISTINCT topic FROM learning_events WHERE topic IS NOT NULL"):
        events = [r[0] for r in db.execute("SELECT event_type FROM learning_events WHERE topic=? ORDER BY id DESC",
                                           (topic,))]
        tries = [e for e in events if e in ("pass", "fail")]
        if not tries:
            continue
        failure_rate = tries.count("fail") / len(tries)
        repeated = min(1.0, events.count("repeated_mistake") / len(tries))
        recent = tries[:3].count("fail") / min(3, len(tries))
        profile[topic] = {"attempts": len(tries), "pass_rate": round(1 - failure_rate, 2),
                          "weakness": round(failure_rate * .45 + repeated * .35 + recent * .20, 3)}
    return profile


def _days_since(iso):
    ts = datetime.fromisoformat(iso)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return max(0, (datetime.now(UTC) - ts).days)


def recommend_problem(db, exclude_id=None):
    """Score = .40 weakness match + .25 spaced review + .20 difficulty fit + .15 novelty."""
    profile = get_learning_profile(db)
    total = sum(p["attempts"] for p in profile.values())
    pass_rate = sum(p["pass_rate"] * p["attempts"] for p in profile.values()) / total if total else 0.5
    target = 0 if pass_rate < 0.5 else 1 if pass_rate < 0.8 else 2
    recent = {r[0] for r in db.execute("SELECT problem_id FROM attempts ORDER BY id DESC LIMIT 3")}
    last_attempt = dict(db.execute("SELECT problem_id, MAX(submitted_at) FROM attempts GROUP BY problem_id"))
    test_counts = dict(db.execute("SELECT problem_id, COUNT(*) FROM tests GROUP BY problem_id"))
    best = None
    for p in db.execute("SELECT id, title, tier, difficulty, topics_json, solved_at FROM problems"):
        if p["id"] == exclude_id:
            continue
        topics = json.loads(p["topics_json"])
        weakness = max((profile.get(t, {}).get("weakness", 0) for t in topics), default=0)
        last = last_attempt.get(p["id"]) or p["solved_at"]
        days = _days_since(last) if last else 60
        spaced = days / (days + 14)  # 0 today, 0.5 after two weeks, → 1
        fit = 1 - abs(DIFFICULTY.get(p["difficulty"], 1) - target) / 2
        novelty = 0 if p["id"] in recent else 1
        score = .40 * weakness + .25 * spaced + .20 * fit + .15 * novelty
        reasons = []
        weak = [t for t in topics if profile.get(t, {}).get("weakness", 0) >= 0.3]
        if weak:
            reasons.append(f"약점 topic: {', '.join(weak)}")
        if p["id"] in last_attempt:
            reasons.append(f"마지막 복습 {days}일 전")
        elif p["solved_at"]:
            reasons.append(f"처음 푼 지 {days}일 — 아직 복습하지 않음")
        else:
            reasons.append("아직 복습하지 않음")
        if fit == 1:
            reasons.append(f"현재 수준에 맞는 난이도 ({p['tier'] or p['difficulty']})")
        if not test_counts.get(p["id"]):
            reasons.append("테스트 없음 — 풀기 전에 테스트를 추가하세요")
        if best is None or score > best["score"]:
            best = {"problem_id": p["id"], "title": p["title"], "score": round(score, 3), "reasons": reasons}
    return best


def attempt_history(db, problem_id):
    """Past solution (from the repo) followed by every replay attempt."""
    past = db.execute("SELECT solved_at, past_performance, reference_solution FROM problems WHERE id=?",
                      (problem_id,)).fetchone()
    rows = [dict(r) for r in db.execute(
        "SELECT a.id, a.submitted_at, a.status, a.code, a.runtime_ms, n.algorithm_family, n.complexity_time, "
        "n.complexity_space FROM attempts a LEFT JOIN analyses n ON n.attempt_id=a.id WHERE a.problem_id=? "
        "ORDER BY a.id", (problem_id,))]
    return past, rows


def local_time(iso):
    """Stored timestamps are UTC; show them in the viewer's local time."""
    return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")


def recent_attempts(db, limit=200):
    rows = [dict(r) for r in db.execute(
        "SELECT a.submitted_at, p.id AS problem_id, p.title, p.tier, a.status, n.algorithm_family, n.complexity_time, "
        "a.runtime_ms "
        "FROM attempts a JOIN problems p ON p.id=a.problem_id LEFT JOIN analyses n ON n.attempt_id=a.id "
        "ORDER BY a.id DESC LIMIT ?", (limit,))]
    for r in rows:
        r["submitted_at"] = local_time(r["submitted_at"])
    return rows


def summary(db, days):
    rows = db.execute("SELECT status, submitted_at FROM attempts").fetchall()
    rows = [r for r in rows if _days_since(r["submitted_at"]) < days and r["status"] in JUDGED]
    passed = sum(r["status"] == "PASS" for r in rows)
    return {"attempts": len(rows), "passed": passed, "pass_rate": passed / len(rows) if rows else None}


def activity(db, today=None):
    """GitHub-style activity: judged submissions per local calendar day, plus streaks.
    A day with no study yet today does not break the current streak until the day is over."""
    today = today or datetime.now().astimezone().date()
    days = {}
    for status, ts in db.execute("SELECT status, submitted_at FROM attempts"):
        if status in JUDGED:
            day = days.setdefault(datetime.fromisoformat(ts).astimezone().date(), {"attempts": 0, "passed": 0})
            day["attempts"] += 1
            day["passed"] += status == "PASS"

    current, d = 0, today if today in days else today - timedelta(days=1)
    while d in days:
        current, d = current + 1, d - timedelta(days=1)
    longest = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev and (d - prev).days == 1 else 1
        longest, prev = max(longest, run), d
    return {"days": days, "today": today, "current_streak": current, "longest_streak": longest,
            "active_days": len(days)}
