"""Explanations on top of tool results: learning report, step-by-step hints, test-input generation.

Everything works without an LLM (deterministic fallbacks). With ANTHROPIC_API_KEY set, Claude writes the report,
hints and test inputs. The LLM never decides correctness: test outcomes come from the sandbox, and expected
outputs for generated inputs come from running the past accepted solution.
"""
import json
import re

from .analysis import analyze_code
from .config import env
from .theory import search_theory, section

MAX_HINT_LEVEL = 4

SYSTEM_PROMPT = """너는 사용자의 과거 알고리즘 풀이를 활용해 재풀이와 학습을 돕는 Algorithm Coach다.
- 테스트 결과(runner)와 정적 분석(AST) 값은 사실로 주어진다. 이를 바꾸거나 새로운 성능 수치를 지어내지 않는다.
- 이론적 복잡도와 측정된 실행 시간을 구분한다. 정적 분석의 복잡도는 추정치이며 confidence와 함께 해석한다.
- status가 PASS가 아니면 효율성을 칭찬하지 말고, 실패 케이스를 중심으로 스스로 고칠 수 있게 안내한다.
- 순서: 잘한 점 -> 과거 대비 변화 -> 개선점 -> 관련 이론 -> 다음 행동.
- 억지 개선점을 만들지 않는다. 완성 코드는 제공하지 않는다.
- theory 문서가 주어지면 그 내용을 우선 근거로 사용한다. 한국어 Markdown으로 간결하게 답한다."""

HINT_POLICY = {1: "문제의 핵심 관찰 한 가지만. 알고리즘 이름은 말하지 않는다.",
               2: "사용할 자료구조/알고리즘 방향만.",
               3: "풀이 전략을 단계별 문장으로. 코드는 쓰지 않는다.",
               4: "의사코드(pseudo code). 실제 Python 코드는 쓰지 않는다."}


def llm_available():
    return bool(env("ANTHROPIC_API_KEY"))


def _ask(system, user, schema=None, effort="medium"):
    import anthropic  # optional dependency path; only imported when a key is configured

    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    output_config = {"effort": effort}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    resp = client.messages.create(
        model=env("LLM_MODEL", "claude-opus-5-5"),
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        # fallbacks: if a safety classifier declines, the API re-runs the request on a fallback model
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default", "output_config": output_config},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("the model declined this request")
    text = "".join(b.text for b in resp.content if b.type == "text")
    return json.loads(text) if schema else text


# ---------------------------------------------------------------- report

def report(facts):
    """facts: status, tests, analyses, comparison, codes, theory. Uses the LLM when available."""
    if llm_available():
        return _ask(SYSTEM_PROMPT, json.dumps(facts, ensure_ascii=False, indent=1))
    return template_report(facts["run"], facts["current_analysis"], facts["comparison"], facts["theory"])


def template_report(run, analysis, comparison, theory):
    lines = [f"### 결과: {run['status']}"]
    if run["status"] != "PASS":  # correctness first: no efficiency praise for wrong code
        advice = {"FAIL": "실패한 케이스의 입력과 기대 출력을 직접 손으로 추적해 보세요.",
                  "TIMEOUT": "무한 루프나 입력 크기에 비해 과도한 복잡도를 의심해 보세요.",
                  "RUNTIME_ERROR": "오류 메시지의 위치와 경계 입력(빈 입력, 인덱스 끝, 재귀 깊이)을 확인하세요.",
                  "SYNTAX_ERROR": "표시된 줄의 문법을 확인하세요."}.get(run["status"], "")
        lines += ["", advice]
        for r in run.get("results", []):
            if not r.get("ok"):
                why = r.get("error") or ("시간 초과" if r.get("timeout") else "출력이 기대값과 다름")
                lines.append(f"- `{r.get('name')}`: {why}")
        if theory:
            lines += ["", "**관련 개념**"] + [f"- → {t['name']}" for t in theory]
        return "\n".join(lines)
    if analysis.get("strengths"):
        lines += ["", "**잘한 점**"] + [f"- {s}" for s in analysis["strengths"]]
    if comparison:
        lines += ["", "**과거 풀이 대비 변화**"] + [f"- ✓ {s}" for s in comparison["improved"]]
        lines += [f"- ✗ {s}" for s in comparison["regressed"]]
        lines += [f"- ↔ {s}" for s in comparison.get("changed", [])]
        if comparison["tradeoff"]:
            lines.append(f"- ⚖ {comparison['tradeoff']}")
        if not comparison["improved"] and not comparison["regressed"]:
            lines.append("- 복잡도는 과거와 같고, 다른 방식으로 풀었습니다." if comparison.get("changed")
                         else "- 과거와 같은 접근과 복잡도를 다시 재현했습니다.")
    if analysis.get("issues"):
        lines += ["", "**개선점**"] + [f"- {s}" for s in analysis["issues"]]
    if theory:
        lines += ["", "**다시 볼 개념**"] + [f"- → {t['name']}" for t in theory]
    return "\n".join(lines)


# ---------------------------------------------------------------- hints

def hint(db, problem, reference_code, level, draft=""):
    """Level 1..4. Order of preference: hints written in the repo → LLM → deterministic fallback."""
    if level <= len(problem["hints"]):
        return problem["hints"][level - 1]
    if llm_available():
        return _ask(
            "너는 알고리즘 코치다. 정답 코드를 절대 보여주지 않고, 요청된 단계의 힌트만 3문장 이내 한국어로 준다.",
            f"힌트 단계 {level}: {HINT_POLICY[level]}\n\n[문제]\n{problem['statement']}\n\n"
            f"[사용자가 예전에 통과한 풀이 — 방향 참고용, 노출 금지]\n{reference_code}\n\n[현재 작성 중인 코드]\n{draft}",
            effort="low")
    if problem["judge"] == "sql":
        return _sql_hint(problem, reference_code, level)
    past = analyze_code(reference_code)
    if level == 1:  # observation only: no algorithm name yet
        return ("제약 조건에서 가장 큰 입력 크기를 찾아 허용되는 시간복잡도부터 정해 보세요. "
                "(대략 N ≤ 10 → 완전 탐색, N ≤ 1,000 → O(N^2), N ≤ 100,000 → O(N log N) 이하) "
                "그다음 작은 예제를 손으로 풀며 반복되는 계산이나 규칙을 찾아보세요.")
    if level == 2:
        docs = search_theory(db, problem["topics"] or past.get("theory_topics", []), limit=1)
        core = section(docs[0]["content"], "핵심") if docs else None
        return f"방향: **{docs[0]['name']}** — {core}" if core else "관련 자료구조를 먼저 정해 보세요."
    if level == 3:
        if "error" in past:
            return "과거 풀이를 분석할 수 없습니다."
        return (f"과거의 나는 `{past['algorithm_family']}` 방식으로, 자료구조 {past['data_structures'] or '없음'}를 "
                f"사용해 {past['time_complexity']}에 풀었습니다.")
    funcs = past.get("features", {}).get("functions") or []
    return ("과거 풀이의 구성: " + (" → ".join(f"`{f}()`" for f in funcs) if funcs else "함수 없이 한 흐름으로 작성") +
            f", 최대 반복 중첩 {past.get('features', {}).get('max_loop_depth', '?')}단계.")


SQL_TOPIC_LABEL = {"sql-join": "JOIN으로 테이블 연결", "sql-aggregate": "GROUP BY + 집계 함수",
                   "sql-window": "윈도우 함수 (OVER)", "sql-subquery": "서브쿼리 / WITH", "sql-dml": "DELETE / UPDATE"}
SQL_CLAUSES = ["WITH", "JOIN", "WHERE", "GROUP BY", "HAVING", "OVER", "UNION", "ORDER BY", "LIMIT", "DELETE", "UPDATE"]


def _sql_hint(problem, reference_code, level):
    if level == 1:
        return "결과 표의 한 행이 무엇을 뜻하는지 먼저 정하고, 그 행을 만들려면 어떤 테이블의 어떤 열이 필요한지 적어 보세요."
    if level == 2:
        return "방향: " + ", ".join(SQL_TOPIC_LABEL.get(t, t) for t in problem["topics"])
    used = [c for c in SQL_CLAUSES if re.search(r"\b" + c.replace(" ", r"\s+") + r"\b", reference_code, re.I)]
    if level == 3:
        return "과거의 나는 " + ", ".join(f"`{c}`" for c in used) + "을(를) 사용했습니다."
    joins = len(re.findall(r"\bJOIN\b", reference_code, re.I))
    ctes = len(re.findall(r"\bAS\s*\(", reference_code, re.I))
    return f"과거 풀이의 구성: JOIN {joins}번, WITH/서브쿼리 블록 {ctes}개, 절 순서 " + " → ".join(used) + "."


# ---------------------------------------------------------------- test generation

def generate_test_inputs(problem, count=6):
    """LLM proposes small, valid inputs (including edge cases). Expected outputs are NOT asked from the LLM:
    they are produced by running the past accepted solution (see sandbox.record_expected)."""
    if problem["judge"] == "stdio":
        what = "표준 입력으로 그대로 전달할 문자열"
    else:
        what = "solution 함수 인자들의 JSON 배열 문자열 (예: \"[[1,2,3], 4]\")"
    data = _ask(
        "너는 알고리즘 문제의 테스트 입력을 만드는 도구다. 문제의 입력 형식과 제약을 정확히 지킨 작은 입력만 만든다.",
        f"다음 문제에 대한 테스트 입력 {count}개를 만들어라. 각 항목은 {what}이다. 최소/경계 값, 특수한 경우, "
        f"일반적인 경우를 섞고 각 입력은 2000자 이하로 한다.\n\n[문제]\n{problem['statement']}",
        schema={"type": "object", "properties": {"inputs": {"type": "array", "items": {"type": "string"}}},
                "required": ["inputs"], "additionalProperties": False},
        effort="low")
    inputs = []
    for raw in data["inputs"][:count]:
        if problem["judge"] == "stdio":
            inputs.append(raw if raw.endswith("\n") else raw + "\n")
        else:
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(args, list):
                inputs.append(args)
    return inputs
