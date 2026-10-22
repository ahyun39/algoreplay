"""UI smoke test with Streamlit's AppTest (no browser, no Docker needed)."""
from streamlit.testing.v1 import AppTest

from algoreplay import db as database
from algoreplay import problems
from algoreplay.config import ROOT


def test_pages_sync_and_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert any("문제 저장소 연결하기" in m.value for m in at.markdown)   # 메인, empty state

    at.sidebar.radio[0].set_value("Example data").run()                # sync panel lives in the sidebar
    next(b for b in at.sidebar.button if b.label == "Sync").click().run()
    assert not at.exception
    assert any("오늘의 복습" in m.value for m in at.markdown)

    at.switch_page("views/practice.py").run()                          # 문제 풀이
    assert not at.exception
    next(b for b in at.button if b.label.startswith("힌트")).click().run()
    assert not at.exception and at.info

    first, second = [p["id"] for p in problems.list_problems(database.connect())][:2]
    for pid in (second, first, second, first):                         # switching back and forth always lands
        next(s for s in at.selectbox if s.label.startswith("문제 (")).set_value(pid).run()
        assert at.session_state.pid == pid and not at.exception

    problems.save_draft(database.connect(), second, "# half-written answer\n")
    fresh = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)  # browser closed and reopened
    fresh.session_state.pid = fresh.session_state.pinned = second
    fresh.run()
    fresh.switch_page("views/practice.py").run()
    assert fresh.session_state.editor_init == "# half-written answer\n"

    at.switch_page("views/history.py").run()                           # 학습 기록
    assert not at.exception
    assert any("학습 잔디" in s.value for s in at.subheader)


def test_grass_grid():
    from datetime import date

    from algoreplay.heatmap import grass_html

    act = {"today": date(2026, 10, 13), "days": {date(2026, 10, 12): {"attempts": 4, "passed": 3}}}
    html = grass_html(act)
    assert html.count("<i title=") == 7 * 52 + 3     # 52 full weeks + Sun..Tue of this week
    assert "2026-10-12 · 4회 풀이 · 통과 3" in html and "#30a14e" in html
