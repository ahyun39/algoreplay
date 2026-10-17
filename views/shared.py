"""Helpers shared by the pages (메인 / 문제 풀이 / 학습 기록)."""
import json

import anthropic
import requests
import streamlit as st

from algoreplay import coach, learning, sources
from algoreplay import db as database
from algoreplay.config import ROOT, env

HOME, PRACTICE, HISTORY = "views/home.py", "views/practice.py", "views/history.py"
LLM_ERRORS = (anthropic.APIError, RuntimeError, ValueError, KeyError)
STATUS_ICON = {"PASS": "✅", "FAIL": "❌", "TIMEOUT": "⏱️", "RUNTIME_ERROR": "💥", "SYNTAX_ERROR": "📝",
               "NO_TESTS": "🧪", "SANDBOX_UNAVAILABLE": "🐳", "RECORDED": "📼", None: "·"}
DIFFICULTY_LABEL = {"easy": "쉬움", "medium": "보통", "hard": "어려움"}


def get_db():
    """One connection per script run: SQLite connections are not shared across threads."""
    try:
        return database.connect()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()


def short(value, n=80):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= n else text[:n] + "…"


def mode_label():
    return f"AI 코치 연결 · {env('LLM_MODEL', 'claude-opus-5-5')}" if coach.llm_available() else "기본 분석 모드"


def section(label, title, caption):
    st.markdown(f'<div class="ar-section-label">{label}</div>', unsafe_allow_html=True)
    st.markdown(f"## {title}")
    st.caption(caption)


def open_in_practice(problem_id):
    """Select a problem and go to the practice page (pinned: selectable even if filters exclude it)."""
    st.session_state.pid = st.session_state.pinned = problem_id
    st.switch_page(PRACTICE)


def recent_table(db, key, limit=200):
    """Recent submissions. Clicking a problem title opens that problem on the practice page."""
    ss = st.session_state
    rows = learning.recent_attempts(db, limit)
    if not rows:
        st.caption("아직 제출 기록이 없습니다.")
        return
    table_key = f"{key}_{ss.get(key + '_rev', 0)}"
    event = st.dataframe(
        rows, hide_index=True, key=table_key, on_select="rerun", selection_mode="single-cell",
        column_order=["submitted_at", "title", "tier", "status", "algorithm_family", "complexity_time", "runtime_ms"],
        column_config={"submitted_at": "제출 시각", "title": "문제 (클릭)", "tier": "난이도", "status": "결과",
                       "algorithm_family": "접근 방식", "complexity_time": "시간복잡도",
                       "runtime_ms": st.column_config.NumberColumn("실행 시간(ms)", format="%.1f")})
    cells = event.selection.cells
    if cells and cells[0][1] == "title":
        ss[key + "_rev"] = ss.get(key + "_rev", 0) + 1  # fresh key = selection cleared when we come back
        open_in_practice(rows[cells[0][0]]["problem_id"])


def sync_panel(db):
    """Connect a problem repository (GitHub / local folder / bundled examples) and sync it."""
    ss = st.session_state
    kind = st.radio("Source", ["GitHub", "Local folder", "Example data"], horizontal=True, label_visibility="collapsed")
    if kind == "GitHub":  # one field per row: this panel lives in the narrow sidebar
        owner = st.text_input("Owner", env("GITHUB_OWNER", ""))
        repo = st.text_input("Repository", env("GITHUB_REPO", ""))
        branch = st.text_input("Branch (비우면 기본 브랜치)", env("GITHUB_BRANCH", ""))
        token = st.text_input("Token (private repo만 필요)", type="password",
                              help="비워 두면 .env의 GITHUB_TOKEN을 사용합니다. 세션에만 보관됩니다.")
    elif kind == "Local folder":
        folder = st.text_input("폴더 경로", placeholder="~/CodingTest")
    if st.button("Sync", type="primary"):
        bar = st.progress(0.0, "파일 목록을 가져오는 중…")
        try:
            if kind == "GitHub":
                src = sources.github_source(owner.strip(), repo.strip(), branch.strip() or None, token or None)
            elif kind == "Local folder":
                src = sources.local_source(folder)
            else:
                src = sources.local_source(ROOT / "examples")
            ss.sync_stats = sources.sync(db, src, progress=lambda f, label: bar.progress(f, label[-60:]))
            ss.just_synced = True  # keep the panel open once so the result summary is visible
            st.rerun()
        except (requests.RequestException, ValueError, OSError) as e:
            bar.empty()
            st.error(f"동기화 실패: {e}")
    if ss.get("sync_stats"):
        s = ss.sync_stats
        st.caption(f"추가 {s['added']} · 갱신 {s['updated']} · 변경 없음 {s['unchanged']} · 삭제 {s['removed']}")
        if s["skipped"]:
            with st.popover(f"건너뛴 폴더 {len(s['skipped'])}개"):
                for d, reason in s["skipped"]:
                    st.caption(f"`{d}` — {reason}")


def no_problems_notice():
    st.info("아직 등록된 문제가 없습니다. 왼쪽 사이드바의 **문제 저장소 동기화**에서 저장소를 연결하세요. "
            "(좁은 화면에서는 왼쪽 위 **>>** 를 눌러 사이드바를 여세요)")
    st.stop()
