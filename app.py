"""AlgoReplay Streamlit UI.  Run: streamlit run app.py

Entry point: page config, theme and navigation. The pages live in views/:
  views/home.py      메인       — overview, today's review
  (repository sync sits in the sidebar on every page)
  views/practice.py  문제 풀이  — problem, editor, tests, results
  views/history.py   학습 기록  — activity grass, weakness, full history
"""
import streamlit as st

from algoreplay import coach, problems
from algoreplay.config import ROOT, env
from views.shared import HISTORY, HOME, PRACTICE, get_db, sync_panel

st.set_page_config(page_title="AlgoReplay", page_icon="🔁", layout="wide")
st.markdown(f"<style>{(ROOT / 'algoreplay' / 'theme.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

page = st.navigation([
    st.Page(HOME, title="메인", icon=":material/home:", default=True),
    st.Page(PRACTICE, title="문제 풀이", icon=":material/code:"),
    st.Page(HISTORY, title="학습 기록", icon=":material/insights:"),
])
with st.sidebar:  # under the menu on every page; open by default until there is something to solve
    db = get_db()
    opened = not problems.list_problems(db) or st.session_state.pop("just_synced", False)
    with st.expander("문제 저장소 동기화", icon=":material/sync:", expanded=opened):
        sync_panel(db)
page.run()
with st.sidebar:  # after the page, so it sits below page-specific sidebar content such as the filters
    st.divider()
    st.caption(("🤖 LLM 사용 (" + env("LLM_MODEL", "claude-opus-5-5") + ")") if coach.llm_available()
               else "LLM 미사용 — ANTHROPIC_API_KEY를 설정하면 리포트/힌트/테스트 생성이 강화됩니다.")
