# Contributing to AlgoReplay

기여를 환영합니다. 버그 제보, 새로운 문제 저장소 형식 지원, 분석 규칙 개선, 이론 문서 추가 모두 좋은 기여입니다.

## 개발 환경

```bash
git clone https://github.com/ahyun39/algoreplay.git
cd algoreplay
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker pull python:3.11-slim     # sandbox 테스트용
docker pull postgres:16-alpine   # SQL sandbox 테스트용
```

## 테스트와 린트

```bash
python -m pytest          # Docker가 꺼져 있으면 sandbox 테스트는 skip 됩니다
ruff check .
```

PR을 올리면 GitHub Actions가 Docker를 포함한 전체 테스트와 `ruff`를 실행합니다.

## 코드 구조

| 모듈 | 역할 |
|---|---|
| `algoreplay/sources.py` | GitHub/로컬 소스, BaekjoonHub·AlgoReplay 형식 파서, 증분 동기화 |
| `algoreplay/sandbox.py` | Docker 격리 실행, function / stdio 채점, 과거 풀이로 기대 출력 기록 |
| `algoreplay/analysis.py` | AST 기반 구조 분석, 알고리즘 탐지, 복잡도 추정, Clean Code 점수, 비교 |
| `algoreplay/learning.py` | attempt 저장, learning event, 약점 점수, 추천 |
| `algoreplay/coach.py` | 학습 리포트, 단계형 힌트, 테스트 입력 생성 (LLM은 선택) |
| `algoreplay/theory.py`, `algoreplay/theory/*.md` | 내장 이론 문서와 검색 |
| `algoreplay/problems.py`, `algoreplay/db.py` | 조회 함수, SQLite 스키마 |
| `app.py` | 진입점: 페이지 설정, 테마, 사이드바 메뉴 (`st.navigation`) |
| `views/home.py`, `views/practice.py`, `views/history.py` | 메인 / 문제 풀이 / 학습 기록 화면 |
| `views/shared.py` | 화면 공통 도우미 (DB 연결, 저장소 동기화 패널, 최근 풀이 표, 화면 이동) |
| `algoreplay/theme.css` | 화면 테마 (색상·카드·사이드바 스타일은 이 파일에서 수정) |

## 설계 원칙 (리뷰 기준)

1. **Tool이 사실을 만들고, LLM은 해석만 한다.** 테스트 통과 여부, 기대 출력, 복잡도 추정값은 코드가 결정합니다. LLM 출력으로 이 값들을 대체하는 변경은 받지 않습니다.
2. **제출 코드는 호스트에서 실행하지 않는다.** `sandbox.py` 밖에서 사용자 코드를 `exec`/`import`/`subprocess`로 실행하는 변경은 받지 않습니다.
3. **과거 풀이는 재풀이 중에 노출하지 않는다.** `get_problem()`은 reference solution을 반환하지 않습니다.
4. **LLM 없이도 동작해야 한다.** LLM 기능에는 결정적인(deterministic) fallback을 둡니다.
5. **추정과 측정을 구분한다.** UI와 리포트에서 정적 분석 복잡도와 실행 시간을 섞어 표현하지 않습니다.

## 자주 하는 기여

### 새로운 문제 저장소 형식 지원
`sources.py`에 `parse_<format>()`을 추가하고 `_candidates()`에서 해당 폴더를 인식하도록 합니다. 파서는 `(problem_dict, None)` 또는 `(None, "건너뛴 이유")`를 반환합니다. **테스트 fixture는 직접 작성한 내용**으로 만들어 주세요 (아래 콘텐츠 정책).

### 분석 규칙 개선
`analysis.py`의 규칙을 바꿀 때는 `tests/test_analysis.py`에 "이 코드는 이 복잡도여야 한다"는 케이스를 함께 추가합니다. 오탐을 고치는 PR이라면 오탐이 나던 코드를 테스트로 남겨 주세요.

### 이론 문서 추가
`algoreplay/theory/<topic>.md`를 추가하고, 태그와 연결하려면 `sources.TOPIC_KEYWORDS`에 키워드를 등록합니다. 문서 구조는 기존 문서(핵심 개념 → 동작 원리 → 시간복잡도 → Python에서 → 언제 사용하는가 → 자주 하는 실수 → 연습 질문)를 따릅니다.

## 콘텐츠 정책

- 백준, 프로그래머스 등 **제3자 사이트의 문제 원문, 테스트 데이터, 해설을 이 저장소에 넣지 마세요.** 예제와 테스트 fixture는 직접 작성한 문제로 만듭니다.
- 사용자의 문제/풀이는 각자의 저장소에 있고, AlgoReplay는 그것을 읽기만 합니다.
- 이론 문서는 직접 작성한 설명이어야 합니다.

## Pull Request 체크리스트

- [ ] `python -m pytest`와 `ruff check .` 통과
- [ ] 동작이 바뀌었다면 테스트 추가/수정
- [ ] 사용자에게 보이는 변경이면 README의 Features / Limitations 갱신
- [ ] secret, 개인 풀이, 제3자 문제 원문이 포함되지 않음

## 보안 문제

sandbox 탈출 등 보안 문제는 공개 이슈로 올리지 말고 [SECURITY.md](SECURITY.md)의 절차를 따라 주세요.
