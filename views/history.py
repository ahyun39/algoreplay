"""학습 기록: activity grass, weakness, profile and the full submission history."""
import streamlit as st

from algoreplay import learning, problems
from algoreplay.heatmap import grass_html
from views.shared import get_db, no_problems_notice, recent_table, section

st.session_state._page = "history"
db = get_db()
all_problems = problems.list_problems(db)
section("LEARNING INSIGHTS", "학습 기록과 성장", "실행 결과와 반복되는 취약 유형을 살펴보고 다음 복습 계획을 세워보세요.")
if not all_problems:
    no_problems_notice()

act, month = learning.activity(db), learning.summary(db, 30)
c1, c2, c3, c4 = st.columns(4)
c1.metric("최근 30일 풀이", month["attempts"])
c1.caption("통과율 " + (f"{month['pass_rate']:.0%}" if month["pass_rate"] is not None else "-"))
c2.metric("복습한 문제", sum(1 for p in all_problems if p["last_status"]), help="한 번 이상 제출한 문제 수")
c3.metric("최장 연속 학습", f"{act['longest_streak']}일")
c4.metric("지난 1년 학습한 날", f"{act['active_days']}일")

st.subheader("학습 잔디")
st.caption(f"🔥 연속 학습 **{act['current_streak']}일** · 최장 연속 {act['longest_streak']}일 · "
           f"지난 1년간 학습한 날 {act['active_days']}일 — 제출 및 분석 횟수 기준, 칸에 마우스를 올리면 날짜별 기록")
st.markdown(grass_html(act), unsafe_allow_html=True)  # generated here from numbers only, no user text

profile = learning.get_learning_profile(db)
st.subheader("알고리즘별 약점 점수")
st.caption("다음 복습 문제를 고르기 위한 내부 지표입니다. 실력을 평가하는 점수가 아닙니다.")
if profile:
    left, right = st.columns([1.3, 1], gap="large")
    weak = {t: v["weakness"] for t, v in profile.items() if v["weakness"] > 0}
    with left:
        if weak:
            st.bar_chart(weak, horizontal=True)
        else:
            st.success(f"복습한 {len(profile)}개 topic에서 아직 약점이 발견되지 않았습니다.")
    with right:
        st.dataframe([{"topic": t, **v} for t, v in sorted(profile.items(), key=lambda x: -x[1]["weakness"])],
                     hide_index=True, column_config={"topic": "알고리즘", "attempts": "시도", "pass_rate": "통과율",
                                                     "weakness": "약점 점수"})
else:
    st.caption("아직 복습 기록이 없습니다.")

st.subheader("전체 풀이 기록")
st.caption("문제 제목을 누르면 그 문제를 푸는 화면으로 이동합니다.")
recent_table(db, "history_recent")
