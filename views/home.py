"""메인: where am I and what should I review today."""
import streamlit as st

from algoreplay import learning, problems
from views.shared import HISTORY, get_db, mode_label, open_in_practice, recent_table, section

st.session_state._page = "home"
db = get_db()
all_problems = problems.list_problems(db)

st.markdown(f"""
<div class="ar-hero">
  <div>
    <div class="ar-eyebrow">YOUR PERSONAL CODING COACH</div>
    <div class="ar-title">다시 풀수록, 실력이 쌓이도록.</div>
    <p class="ar-subtitle">과거 풀이를 돌아보기 전에 먼저 도전하고, 실행 결과와 코드 분석을 바탕으로 다음 학습을 설계하세요.</p>
  </div>
  <div class="ar-chip">● {mode_label()}</div>
</div>""", unsafe_allow_html=True)

if not all_problems:
    section("GET STARTED", "문제 저장소 연결하기",
            "BaekjoonHub로 쌓인 GitHub 저장소나 로컬 폴더를 연결하세요.")
    with st.container(border=True):
        st.markdown("1. 왼쪽 사이드바의 **문제 저장소 동기화**를 엽니다. "
                    "(좁은 화면에서는 왼쪽 위 **>>** 를 눌러 사이드바를 여세요)\n"
                    "2. **GitHub**(owner / repository), **Local folder**, **Example data** 중 하나를 고릅니다.\n"
                    "3. **Sync**를 누르면 문제가 등록되고 이 화면에 오늘의 복습이 나타납니다.\n\n"
                    "바로 체험하려면 **Example data → Sync**.")
    st.stop()

week, month = learning.summary(db, 7), learning.summary(db, 30)
m1, m2, m3, m4 = st.columns(4)
m1.metric("최근 7일 풀이", week["attempts"], help="최근 7일 동안 채점된 제출 수")
m2.metric("최근 30일 통과율", f"{month['pass_rate']:.0%}" if month["pass_rate"] is not None else "—",
          help="최근 30일 제출 결과 기준")
m3.metric("연속 학습", f"{learning.activity(db)['current_streak']}일")
m4.metric("등록된 문제", len(all_problems))

left, right = st.columns([1.35, 1], gap="large")
with left:
    section("TODAY", "오늘의 복습", "약점, 복습 간격, 난이도를 고려해 지금 다시 풀기 좋은 문제입니다.")
    rec = learning.recommend_problem(db)
    with st.container(border=True):
        if rec:
            st.markdown(f"### {rec['title']}")
            for reason in rec["reasons"]:
                st.caption(f"• {reason}")
            if st.button("이 문제 풀러 가기", type="primary", icon=":material/arrow_forward:"):
                open_in_practice(rec["problem_id"])
        else:
            st.caption("추천할 문제가 없습니다.")
with right:
    section("FOCUS", "집중이 필요한 알고리즘", "반복해서 틀린 topic입니다. 실력 평가가 아닌 복습 우선순위예요.")
    profile = learning.get_learning_profile(db)
    weak = sorted(((t, v) for t, v in profile.items() if v["weakness"] > 0), key=lambda x: -x[1]["weakness"])[:3]
    with st.container(border=True):
        if weak:
            for topic, v in weak:
                st.markdown(f"**{topic}** · 약점 {v['weakness']:.2f}")
                st.progress(min(v["weakness"], 1.0))
        elif profile:
            st.caption(f"복습한 {len(profile)}개 topic에서 아직 약점이 발견되지 않았습니다.")
        else:
            st.caption("제출 기록이 쌓이면 여기에 약점 topic이 표시됩니다.")
        st.page_link(HISTORY, label="학습 기록 자세히 보기", icon=":material/insights:")

section("RECENT", "최근 풀이", "문제 제목을 누르면 그 문제를 푸는 화면으로 이동합니다.")
recent_table(db, "home_recent", limit=5)
