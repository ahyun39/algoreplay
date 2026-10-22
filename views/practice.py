"""문제 풀이: pick a problem, write code, run it in the sandbox and read the analysis."""
import json

import streamlit as st
from streamlit_ace import st_ace

from algoreplay import coach, learning, problems, sandbox
from algoreplay.analysis import analyze_code, compare_solutions
from algoreplay.config import env
from algoreplay.theory import search_theory
from views.shared import DIFFICULTY_LABEL, LLM_ERRORS, STATUS_ICON, get_db, no_problems_notice, section, short

ss = st.session_state
entering = ss.get("_page") != "practice"  # just arrived from another page
ss._page = "practice"
db = get_db()
all_problems = problems.list_problems(db)
section("FOCUSED PRACTICE", "문제 풀이", "복습할 문제를 고르고, 코드를 실행한 다음 분석 결과로 개선점을 확인하세요.")
if not all_problems:
    no_problems_notice()

# Filters live in this page's sidebar. Widget values are dropped when the page is left,
# so the chosen values are kept in session state and passed back as defaults.
f = ss.setdefault("filters", {"query": "", "source": None, "difficulty": None, "topic": None, "status": None})


def pick(label, options, name, labels):
    # Fixed keys: a selectbox whose `index` changes between reruns is rebuilt and can show a stale choice.
    # "전체" is stored as "" because a keyed selectbox reads None as "nothing selected".
    options = ["" if o is None else o for o in options]
    if ss.get(f"flt_{name}") not in options:  # first visit, back from another page, or option gone
        ss[f"flt_{name}"] = f[name] if f[name] in options else ""
    value = st.selectbox(label, options, key=f"flt_{name}", format_func=lambda x: labels.get(x or None, x))
    f[name] = value or None


before = dict(f)
with st.sidebar:
    st.subheader("문제 필터")
    ss.setdefault("flt_query", f["query"])
    f["query"] = st.text_input("검색", key="flt_query", placeholder="제목 또는 번호")
    pick("출처", [None] + problems.sources(db), "source", {None: "전체"})
    pick("난이도", [None, "easy", "medium", "hard"], "difficulty", {None: "전체", **DIFFICULTY_LABEL})
    pick("알고리즘", [None] + problems.topics(db), "topic", {None: "전체"})
    pick("복습 상태", [None, "new", "passed", "failed"], "status",
         {None: "전체", "new": "아직 복습 안 함", "passed": "최근 통과", "failed": "최근 실패"})

if f != before:  # the user changed a filter: stop keeping the pinned (recommended/clicked) problem
    ss.pinned = None

shown = problems.list_problems(db, f["query"], f["source"], f["difficulty"], f["topic"], f["status"])
ids = [p["id"] for p in shown]
if ss.get("pinned") and ss.pinned not in ids:
    ids.insert(0, ss.pinned)
if not ids:
    st.warning("필터에 맞는 문제가 없습니다.")
    st.stop()
if ss.get("pid") not in ids:  # nothing chosen yet: start from today's recommendation when it is listed
    rec = learning.recommend_problem(db)
    ss.pid = rec["problem_id"] if rec and rec["problem_id"] in ids else ids[0]
labels = {p["id"]: f"{STATUS_ICON[p['last_status']]} [{p['tier'] or p['difficulty']}] {p['title']} · "
                    f"{p['problem_key']}" for p in all_problems}
if ss.get("pid_pick") != ss.pid:  # pid was set in code (recommendation, filter change, coming from another page)
    ss.pid_pick = ss.pid
ss.pid = st.selectbox(f"문제 ({len(shown)}개)", ids, key="pid_pick", format_func=labels.get,
                      on_change=lambda: ss.update(pid=ss.pid_pick))  # a user pick wins over the line above
if ss.pid != ss.get("pinned"):
    ss.pinned = None

def as_text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def result_details(results):
    """Full input / expected / output / print() / error of each test (the table above shortens them)."""
    first_fail = next((i for i, r in enumerate(results) if not r["ok"]), None)
    for i, r in enumerate(results):
        mark = "✅" if r["ok"] else ("⏱️" if r.get("timeout") else "❌")
        with st.expander(f"{mark} {r['name']} — 전체 입출력", expanded=i == first_fail):
            st.caption("입력")
            st.code(as_text(r["input"]), language="text")
            c1, c2 = st.columns(2)
            c1.caption("기대 출력")
            c1.code("(기록 모드)" if r["expected"] is None else as_text(r["expected"]), language="text")
            c2.caption("내 출력")
            c2.code(r.get("output") or "(출력 없음)", language="text")
            if r.get("truncated"):
                st.caption(f"출력이 너무 길어 앞 {sandbox.OUTPUT_LIMIT:,}자만 표시합니다. 채점은 전체 출력으로 했습니다.")
            if r.get("stdout"):
                st.caption("print() 출력")
                st.code(r["stdout"], language="text")
            if r.get("stderr") or r.get("error"):
                st.caption("오류")
                st.code(r.get("stderr") or r["error"], language="text")


drafts = ss.setdefault("drafts", {})  # problem id -> last code saved to the DB (avoids a write per rerun)

def load_into_editor(text):
    """Replace the editor content: a new key remounts the editor with `text` as its initial value."""
    drafts[ss.pid] = ss.editor_init = text
    problems.save_draft(db, ss.pid, text)
    ss.editor_rev = ss.get("editor_rev", 0) + 1

if ss.get("loaded") != ss.pid:  # reset per-problem state, but restore the draft for this problem
    ss.loaded, ss.hint_level, ss.hints, ss.submitted = ss.pid, 0, {}, None
    ss.result = ss.setdefault("runs", {}).get(ss.pid)  # the last run of this problem survives switching
    ss.editor_init = drafts[ss.pid] = problems.get_draft(db, ss.pid) or problems.starter_code(db, ss.pid)
elif entering:  # the editor was unmounted while away: remount it with the latest draft
    ss.editor_init = drafts[ss.pid] = problems.get_draft(db, ss.pid) or problems.starter_code(db, ss.pid)
    ss.editor_rev = ss.get("editor_rev", 0) + 1

prob = problems.get_problem(db, ss.pid)
tests = problems.get_tests(db, ss.pid)
lang = "sql" if prob["judge"] == "sql" else "python"
left, right = st.columns([0.92, 1.08], gap="large")

with left:
    st.subheader(f"[{prob['tier'] or prob['difficulty']}] {prob['title']}")
    meta = [prob["problem_key"], {"stdio": "표준 입출력", "sql": "SQL (PostgreSQL)"}.get(prob["judge"],
                                                                    f"함수 `{prob['entrypoint']}`")]
    if prob["tags"]:
        meta.append(", ".join(prob["tags"]))
    if prob["url"]:
        meta.append(f"[원문]({prob['url']})")
    st.caption(" · ".join(meta))
    if prob["solved_at"]:
        st.caption(f"처음 푼 날: {prob['solved_at'][:10]}" +
                   (f" · 당시 성능 {prob['past_performance']}" if prob["past_performance"] else ""))
    with st.container(height=520):
        st.markdown(prob["statement"])
    for level in range(1, ss.hint_level + 1):
        st.info(f"**힌트 {level}** — {ss.hints[level]}")

with right:
    # Ace editor with VS Code keys: auto-indent after ":", Tab / Shift+Tab, bracket pairing.
    # auto_update sends the code 200 ms after typing stops, so the buttons never see stale code.
    dark = getattr(getattr(st.context, "theme", None), "type", None) == "dark"
    # `value` stays fixed while the problem is open; pushing the draft back on every rerun could
    # overwrite keystrokes typed during the 200 ms update window.
    code = st_ace(value=ss.editor_init, language=lang, keybinding="vscode",
                  theme="tomorrow_night" if dark else "chrome", tab_size=4, font_size=14, min_lines=20,
                  show_print_margin=False, auto_update=True,
                  key=f"code_{ss.pid}_{ss.get('editor_rev', 0)}")
    if code is not None and code != drafts.get(ss.pid):  # saved in the DB: survives closing the browser
        drafts[ss.pid] = code
        problems.save_draft(db, ss.pid, code)
    b1, b2, b3, b4 = st.columns(4)
    run = b1.button("테스트 실행")
    submit = b2.button("제출 및 분석", type="primary")
    can_hint = ss.hint_level < coach.MAX_HINT_LEVEL
    if b4.button("초기화", help="편집기를 이 문제의 시작 코드로 되돌립니다."):
        load_into_editor(problems.starter_code(db, ss.pid))
        st.rerun()
    if b3.button(f"힌트 {ss.hint_level + 1}" if can_hint else "힌트 끝", disabled=not can_hint):
        with st.spinner("힌트 준비 중…"):
            try:
                level = ss.hint_level + 1
                ss.hints[level] = coach.hint(db, prob, problems.get_old_solution(db, ss.pid), level, code)
                ss.hint_level = level
                st.rerun()
            except LLM_ERRORS as e:
                st.error(f"힌트 생성 실패: {e}")
    st.caption(f"테스트 {len(tests)}개 · Docker sandbox에서 실행 (네트워크 차단, 테스트당 "
               f"{env('EXEC_TIMEOUT_SEC', '3')}초)")

# ------------------------------------------------------------ test cases
with st.expander(f"🧪 테스트 케이스 ({len(tests)})", expanded=not tests):
    if tests:
        st.dataframe([{"이름": t["name"], "출처": t["origin"], "입력": short(t["input"]),
                       "기대 출력": short(t["expected"])} for t in tests], hide_index=True)
        shown_test = st.selectbox("전체 내용 보기", tests, format_func=lambda t: f"{t['name']} ({t['origin']})",
                                  key=f"view_test_{ss.pid}")
        c1, c2 = st.columns(2)
        c1.caption("입력")
        c1.code(as_text(shown_test["input"]), language="text")
        c2.caption("기대 출력")
        c2.code(as_text(shown_test["expected"]), language="text")
        removable = [t for t in tests if t["origin"] != "repo"]
        if removable:
            c1, c2 = st.columns([3, 1])
            victim = c1.selectbox("삭제할 테스트", removable, format_func=lambda t: t["name"],
                                  label_visibility="collapsed")
            if c2.button("삭제"):
                problems.delete_test(db, victim["id"])
                st.rerun()
    else:
        st.info("이 문제에는 아직 테스트가 없습니다." if lang == "sql" else
                "이 문제에는 아직 테스트가 없습니다. 입력만 넣으면 **과거에 통과한 내 풀이**를 실행해 기대 출력을 만듭니다.")

    stdio = prob["judge"] == "stdio"
    if lang == "sql":  # tables come from the README examples; no free-form inputs for now
        st.caption("SQL 테스트는 문제 설명의 예제 표(Input/Output)로 자동 생성됩니다.")
    else:
        with st.form(f"add_test_{ss.pid}_{ss.get('form_rev', 0)}"):  # not cleared on error, fresh after success
            c1, c2 = st.columns(2)
            raw_in = c1.text_area("입력 (표준 입력 그대로)" if stdio else "인자 (JSON 배열, 예: [[1, 2], 3])", height=140)
            raw_out = c2.text_area("기대 출력 (비우면 과거 풀이로 계산)", height=140)
            if st.form_submit_button("테스트 추가"):
                try:
                    value = raw_in if stdio else json.loads(raw_in)
                    if not stdio and not isinstance(value, list):
                        raise ValueError("인자는 JSON 배열이어야 합니다.")
                    if stdio and not value.endswith("\n"):
                        value += "\n"
                    if raw_out.strip():
                        problems.add_tests(db, ss.pid, [{"input": value,
                                                          "expected": raw_out if stdio else json.loads(raw_out)}])
                    else:
                        made, rejected = sandbox.record_expected(problems.get_old_solution(db, ss.pid), [value],
                                                                 prob["judge"], prob["entrypoint"])
                        if rejected:
                            raise ValueError(f"과거 풀이가 이 입력을 처리하지 못했습니다: {rejected[0][1]}")
                        problems.add_tests(db, ss.pid, made)
                    ss.form_rev = ss.get("form_rev", 0) + 1
                    st.toast("테스트를 저장했습니다. 다른 문제로 이동해도 유지됩니다.", icon="✅")
                    st.rerun()
                except (ValueError, RuntimeError) as e:
                    st.error(str(e))

    c1, c2 = st.columns(2)
    if c1.button("🤖 LLM으로 테스트 입력 생성", disabled=not coach.llm_available() or lang == "sql",
                 help="LLM은 입력만 만들고, 기대 출력은 과거에 통과한 풀이를 실행해 얻습니다."):
        with st.spinner("입력 생성 → 과거 풀이로 기대 출력 계산 중…"):
            try:
                inputs = coach.generate_test_inputs(prob)
                made, rejected = sandbox.record_expected(problems.get_old_solution(db, ss.pid), inputs,
                                                         prob["judge"], prob["entrypoint"])
                problems.add_tests(db, ss.pid, made, origin="generated")
                st.success(f"{len(made)}개 추가" + (f", {len(rejected)}개는 과거 풀이가 처리하지 못해 제외" if rejected
                                                 else ""))
                st.rerun()
            except LLM_ERRORS as e:
                st.error(f"테스트 생성 실패: {e}")
    if c2.button("과거 풀이로 테스트 검증", disabled=not tests,
                 help="기대 출력이 맞는지, 또는 저장소의 과거 풀이가 완성본인지 확인합니다."):
        with st.spinner("과거 풀이 실행 중…"):
            check = sandbox.run_tests(problems.get_old_solution(db, ss.pid), tests, prob["judge"],
                                      prob["entrypoint"])
        if check["status"] == "PASS":
            st.success("과거 풀이가 모든 테스트를 통과합니다.")
        else:
            st.warning(f"과거 풀이 결과: {check['status']}. 테스트의 기대 출력이 잘못되었거나, 저장소의 풀이가 "
                       "미완성일 수 있습니다.")
            st.dataframe([{"이름": r["name"], "통과": r["ok"], "출력": short(r.get("output", "")),
                           "오류": r.get("error", "")} for r in check["results"]], hide_index=True)
            result_details(check["results"])

# ------------------------------------------------------------ run / submit
if run or submit:
    with st.spinner("Sandbox에서 실행 중…"):
        ss.result = ss.setdefault("runs", {})[ss.pid] = sandbox.run_tests(code, tests, prob["judge"],
                                                                          prob["entrypoint"])
    ss.submitted = None
    if submit and ss.result["status"] not in ("SANDBOX_UNAVAILABLE", "NO_TESTS"):
        old_code = problems.get_old_solution(db, ss.pid)
        if lang == "sql":  # the analyzer reads Python ASTs; SQL gets grading and the report only
            cur = old = {"error": "SQL은 구조·복잡도 분석을 지원하지 않습니다. 채점 결과와 과거 풀이만 비교해 보세요."}
        else:
            cur, old = analyze_code(code), analyze_code(old_code)
        comparison = compare_solutions(old, cur) if "error" not in cur and "error" not in old else None
        theory = search_theory(db, prob["topics"] + cur.get("theory_topics", []))
        facts = {"run": {k: ss.result.get(k) for k in ("status", "runtime_ms", "peak_memory_kb", "stderr")}
                 | {"results": [{k: r.get(k) for k in ("name", "ok", "error", "timeout", "ms")}
                                for r in ss.result["results"]]},
                 "problem": {"title": prob["title"], "tags": prob["tags"]},
                 "current_analysis": cur, "past_analysis": old, "comparison": comparison,
                 "current_code": code, "past_code": old_code, "theory": theory}
        with st.spinner("학습 리포트 작성 중…"):
            try:
                report = coach.report(facts)
            except LLM_ERRORS as e:
                report = coach.template_report(facts["run"], cur, comparison, theory) + \
                    f"\n\n_(LLM 리포트 실패, 기본 리포트로 대체: {e})_"
        learning.save_attempt(db, ss.pid, code, ss.result, cur, comparison, report)
        ss.submitted = {"cur": cur, "old": old, "old_code": old_code, "theory": theory, "report": report}
        st.rerun()  # refresh recommendation and history

res = ss.result
if res:
    st.divider()
    st.subheader(f"{STATUS_ICON.get(res['status'], '⚠️')} {res['status']}")
    if res.get("results"):
        st.dataframe([{"테스트": r["name"], "통과": r["ok"],
                       "ms": round(r["ms"], 2) if r.get("ms") is not None else None,
                       "입력": short(r["input"], 60), "기대 출력": short("" if r["expected"] is None else r["expected"], 60),
                       "출력": short(r.get("output", ""), 60),
                       "오류": r.get("error") or ("시간 초과" if r.get("timeout") else "")}
                      for r in res["results"]], hide_index=True)
        result_details(res["results"])
    elif res.get("stderr"):
        st.code(res["stderr"], language="text")

sub = ss.submitted
if sub:
    cur, old = sub["cur"], sub["old"]
    if "error" in cur:
        st.warning(cur["error"])
    else:
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**현재 풀이 (정적 분석 추정)**  \n`{cur['algorithm_family']}`  \n"
                    f"시간 {cur['time_complexity']} · 공간 {cur['space_complexity']}  \n"
                    f"confidence {cur['complexity_confidence']}")
        c2.markdown(f"**실제 실행 (측정)**  \n테스트 합계 {res.get('runtime_ms', 0):.1f} ms  \n"
                    f"peak {res.get('peak_memory_kb', 0):.0f} KB  \n*측정값은 환경에 따라 다르며 복잡도와 별개입니다*")
        if "error" not in old:
            c3.markdown(f"**과거 풀이 (정적 분석 추정)**  \n`{old['algorithm_family']}`  \n"
                        f"시간 {old['time_complexity']} · 공간 {old['space_complexity']}")
    st.markdown(sub["report"])
    with st.expander("과거 풀이 보기"):
        st.code(sub["old_code"], language=lang)
    for t in sub["theory"]:
        with st.expander(f"📖 이론: {t['name']}"):
            st.markdown(t["content"])
    nxt = learning.recommend_problem(db, exclude_id=ss.pid)
    if nxt:
        st.markdown(f"**다음 추천:** {nxt['title']} — " + " · ".join(nxt["reasons"]))

past, attempts = learning.attempt_history(db, ss.pid)
if attempts:
    st.divider()
    st.subheader("제출 결과")
    past_analysis = analyze_code(past["reference_solution"])
    timeline = [{"when": (past["solved_at"] or "")[:10] or "과거", "status": "과거 풀이",
                 "algorithm_family": past_analysis.get("algorithm_family"),
                 "complexity_time": past_analysis.get("time_complexity"),
                 "complexity_space": past_analysis.get("space_complexity"), "runtime_ms": None}]
    timeline += [{"when": learning.local_time(a["submitted_at"]), **{k: a[k] for k in (
        "status", "algorithm_family", "complexity_time", "complexity_space", "runtime_ms")}} for a in attempts]
    st.dataframe(timeline, hide_index=True, column_config={
        "when": "제출 시각", "status": "결과", "algorithm_family": "접근 방식", "complexity_time": "시간복잡도",
        "complexity_space": "공간복잡도", "runtime_ms": st.column_config.NumberColumn("실행 시간(ms)", format="%.1f")})

    # Collapsed by default so an earlier answer is not seen by accident while re-solving.
    with st.expander(f"📝 내가 제출한 코드 보기 ({len(attempts)}개)"):
        pick = st.selectbox("제출 기록", list(reversed(attempts)), key=f"attempt_pick_{ss.pid}",
                            format_func=lambda a: f"{learning.local_time(a['submitted_at'])} · "
                                                  f"{STATUS_ICON.get(a['status'], '')} {a['status']} · "
                                                  f"{a['algorithm_family'] or '-'}")
        st.code(pick["code"], language=lang, line_numbers=True)
        if st.button("이 코드를 편집기로 불러오기", key=f"load_attempt_{ss.pid}"):
            load_into_editor(pick["code"])
            st.rerun()
