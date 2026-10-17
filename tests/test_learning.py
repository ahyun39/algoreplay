from algoreplay import coach, learning, problems, sources
from algoreplay.theory import search_theory
from conftest import EXAMPLES


def test_profile_and_recommendation(db):
    sources.sync(db, sources.local_source(EXAMPLES))
    pid = problems.list_problems(db, query="two-sum")[0]["id"]
    for _ in range(2):
        learning.save_attempt(db, pid, "x", {"status": "FAIL"})
    profile = learning.get_learning_profile(db)
    assert profile["hashmap"]["weakness"] > 0.8
    assert db.execute("SELECT COUNT(*) FROM learning_events WHERE event_type='repeated_mistake'").fetchone()[0] == 1

    db.execute("UPDATE attempts SET submitted_at='2020-01-01T00:00:00+00:00'")
    rec = learning.recommend_problem(db)
    assert rec["problem_id"] == pid and any("hashmap" in r for r in rec["reasons"])
    assert learning.recommend_problem(db, exclude_id=pid)["problem_id"] != pid


def test_non_judged_status_does_not_count(db):
    sources.sync(db, sources.local_source(EXAMPLES))
    pid = problems.list_problems(db, query="two-sum")[0]["id"]
    learning.save_attempt(db, pid, "x", {"status": "SANDBOX_UNAVAILABLE"})
    assert learning.get_learning_profile(db) == {}


def test_theory_builtin_and_repo_override(db):
    assert search_theory(db, ["bfs"])[0]["name"] == "bfs"
    db.execute("INSERT INTO theory(repository_id, name, content) VALUES(1, 'bfs', '# my notes')")
    assert search_theory(db, ["bfs"])[0]["content"] == "# my notes"


def test_hints_without_llm(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sources.sync(db, sources.local_source(EXAMPLES))
    pid = problems.list_problems(db, query="90001")[0]["id"]
    prob, ref = problems.get_problem(db, pid), problems.get_old_solution(db, pid)
    hints = [coach.hint(db, prob, ref, level) for level in range(1, coach.MAX_HINT_LEVEL + 1)]
    assert "bfs" not in hints[0] and "bfs" in hints[1] and "dfs_recursion" in hints[2]  # name revealed from level 2
    assert all("def " not in h for h in hints)  # never the solution code


def test_template_report_does_not_praise_failures():
    run = {"status": "FAIL", "results": [{"name": "t1", "ok": False}]}
    text = coach.template_report(run, {"strengths": ["fast"]}, {"improved": ["O(N)"]}, [])
    assert "fast" not in text and "t1" in text


def test_starter_code(db):
    sources.sync(db, sources.local_source(EXAMPLES))
    fn = problems.list_problems(db, query="90002")[0]["id"]
    io = problems.list_problems(db, query="90001")[0]["id"]
    assert problems.starter_code(db, fn).startswith("def solution(s):")
    assert "sys.stdin.readline" in problems.starter_code(db, io)


def test_activity_counts_and_streaks(db):
    from datetime import date, datetime, timedelta

    sources.sync(db, sources.local_source(EXAMPLES))
    pid = problems.list_problems(db, query="two-sum")[0]["id"]
    today = date(2026, 10, 13)

    def submit(day, status):
        learning.save_attempt(db, pid, "x", {"status": status})
        local_noon = datetime(day.year, day.month, day.day, 12).astimezone()  # stored like real attempts
        db.execute("UPDATE attempts SET submitted_at=? WHERE id=(SELECT MAX(id) FROM attempts)",
                   (local_noon.isoformat(),))

    for back in (1, 2, 3):                       # 3-day streak ending yesterday
        submit(today - timedelta(days=back), "PASS")
    submit(today - timedelta(days=1), "FAIL")
    for back in (10, 11, 12, 13, 14):            # an older, longer streak
        submit(today - timedelta(days=back), "FAIL")
    learning.save_attempt(db, pid, "x", {"status": "SANDBOX_UNAVAILABLE"})  # not a judged attempt

    act = learning.activity(db, today=today)
    assert act["days"][today - timedelta(days=1)] == {"attempts": 2, "passed": 1}
    assert act["current_streak"] == 3            # not studying *yet* today keeps the streak alive
    assert act["longest_streak"] == 5 and act["active_days"] == 8
    assert learning.activity(db, today=today + timedelta(days=1))["current_streak"] == 0
