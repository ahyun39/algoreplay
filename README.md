# AlgoReplay

> Re-solve your past algorithm problems, compare your solutions over time, and turn your coding history into a personalized learning loop.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](#quick-start)
[![CI](https://github.com/ahyun39/algoreplay/actions/workflows/ci.yml/badge.svg)](https://github.com/ahyun39/algoreplay/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-v0.2-orange)](#limitations)

AlgoReplay는 GitHub에 저장된 과거 알고리즘 풀이를 활용하는 개인 맞춤형 복습 도구입니다.

이미 해결한 문제를 다시 풀고, 제출한 코드를 채점·분석해 과거 풀이와 비교합니다. 반복적으로 실패하는 주제를 기록하고, 복습 이력과 난이도를 바탕으로 다음 학습 문제를 추천합니다.

```text
과거 풀이 불러오기 → 다시 풀기 → 채점 및 분석 → 과거 풀이와 비교 → 복습 및 다음 문제 추천
```

BaekjoonHub 등 기존 알고리즘 풀이 저장소를 연결해 별도의 문제 데이터를 처음부터 구축하지 않고 시작할 수 있습니다.

## Features

- **Problem Replay** — 과거 정답 코드를 숨긴 상태에서 같은 문제를 다시 풀이하고, 제출 후 기존 풀이와 비교합니다. 자동 들여쓰기와 문법 강조를 지원하는 코드 편집기를 제공합니다.
- **안전한 코드 실행** — Docker 컨테이너에서 제출 코드를 실행하고 테스트 결과를 확인합니다. 백준의 표준 입출력, 프로그래머스의 `solution()` 반환값, LeetCode SQL의 결과 테이블을 각각 지원합니다.
- **테스트 케이스 생성** — 프로그래머스 예제 입출력을 테스트로 변환합니다. 백준 문제는 입력을 제공하면 과거 풀이를 실행해 기대 출력을 생성할 수 있습니다.
- **코드 분석** — AST 기반으로 알고리즘·자료구조 패턴을 탐지하고, 규칙 기반으로 시간·공간복잡도를 추정합니다. Clean Code 점검 결과도 제공합니다.
- **과거 풀이 비교** — 현재 코드와 과거 코드의 개선·후퇴·접근 방식 변화·시간 및 공간 복잡도 간 트레이드오프를 비교합니다.
- **단계형 힌트** — 정답 코드를 직접 제공하지 않고 단계별 힌트를 통해 스스로 문제를 해결하도록 돕습니다.
- **이론 학습** — 28개의 내장 이론 문서(SQL 4개 포함)와 저장소의 개인 `theory/*.md` 문서를 활용합니다.
- **약점 분석 및 문제 추천** — 주제별 실패 기록과 복습 이력, 난이도를 활용해 다음 문제를 추천합니다.
- **학습 기록** — 날짜별 풀이 기록과 연속 학습 일수를 잔디 형태로 표시합니다.
- **LLM 기반 학습 지원 (선택)** — Anthropic API key를 설정하면 구현된 LLM 기능을 활용할 수 있습니다. 채점 결과와 코드 분석 지표는 코드가 결정하며, LLM은 지원되는 기능에서 학습 내용을 설명하거나 보조합니다.

## Quick Start

### Requirements

- Python 3.11+
- Docker Engine 또는 Docker Desktop
- Git

SQL 문제를 풀려면 PostgreSQL Docker 이미지도 필요합니다.

### Installation

```bash
git clone https://github.com/ahyun39/algoreplay.git
cd algoreplay

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

docker pull python:3.11-slim
docker pull postgres:16-alpine  # SQL 문제를 풀 때만 필요

streamlit run app.py
```

브라우저에서 [http://localhost:8501](http://localhost:8501)을 엽니다.

### 첫 복습 진행하기

1. 사이드바의 **문제 저장소 동기화**에서 GitHub 저장소, 로컬 폴더 또는 Example data를 선택하고 동기화합니다.
2. **오늘의 복습 → 이 문제 풀러 가기**를 선택합니다.
3. 문제를 열고 직접 코드를 작성합니다.
4. 테스트 케이스가 없다면 입력을 추가해 테스트를 구성합니다.
5. **제출 및 분석**을 실행합니다.
6. 채점 결과, 코드 분석, 과거 풀이와의 차이 및 다음 추천 문제를 확인합니다.

자세한 설정과 사용 방법은 [실행 가이드](docs/GUIDE.md)를 참고하세요.

### Configuration (Optional)

`.env.example`을 `.env`로 복사한 뒤 필요한 항목을 설정합니다.

| 환경 변수 | 설명 |
|---|---|
| `GITHUB_OWNER` / `GITHUB_REPO` | 저장소 연결 시 사용할 기본 소유자 및 저장소 |
| `GITHUB_TOKEN` | 비공개 저장소 접근용 토큰. 필요한 범위만 부여하는 것을 권장합니다. |
| `ANTHROPIC_API_KEY` | 지원되는 LLM 기능 활성화 |
| `EXEC_TIMEOUT_SEC` | 코드 실행 시간 제한 |
| `EXEC_MEMORY_MB` | 코드 실행 메모리 제한 |

기본 실행 제한은 실행 환경의 설정에 따르며, 현재 기본값은 테스트당 3초와 256MB입니다.

## How It Works

AlgoReplay는 채점, 코드 분석, 과거 풀이 비교, 학습 리포트를 순서대로 수행합니다.

### 1. 채점

Docker 컨테이너에서 테스트를 실행해 통과 여부와 실행 시간, 메모리 사용량을 측정합니다.

- 백준: 표준 입력 및 표준 출력 비교
- 프로그래머스: `solution()` 반환값 비교
- LeetCode SQL: PostgreSQL에서 쿼리를 실행하고 결과 테이블 비교

### 2. 정적 코드 분석

코드를 실행하지 않고 AST(Abstract Syntax Tree)를 분석해 알고리즘·자료구조 패턴을 탐지합니다. 규칙에 따라 시간·공간복잡도와 코드 품질을 추정합니다.

복잡도는 정적 분석에 기반한 추정치이며, 모든 코드의 실제 복잡도를 정확하게 판정하는 것은 아닙니다.

### 3. 과거 풀이 비교

과거 풀이와 현재 풀이를 동일한 분석 기준으로 비교합니다.

- 개선: 복잡도나 코드 구조 등에서 긍정적인 변화
- 후퇴: 복잡도나 코드 구조 등에서 부정적인 변화
- 변화: 접근 방식 또는 구현 구조의 변화
- 트레이드오프: 시간과 공간 사용량 사이의 상충 관계

비교 결과는 분석 규칙과 측정 환경에 영향을 받으므로, 지표를 코드의 절대적인 우열로 해석하지 않는 것이 좋습니다.

### 4. 학습 리포트

잘한 점, 과거 대비 변화, 개선점, 관련 이론을 정리합니다. 오답인 경우 실패한 테스트를 먼저 확인할 수 있습니다.

LLM 없이도 채점과 규칙 기반 분석을 수행할 수 있습니다. LLM 사용 여부와 구체적인 적용 범위는 설정 및 구현된 기능에 따라 달라집니다.

자세한 설명은 [실행 가이드 7장: 피드백은 어떻게 만들어지나](docs/GUIDE.md#7-피드백은-어떻게-만들어지나)를 참고하세요.

## Supported Repository Formats

기존 저장소를 최대한 재사용할 수 있도록 여러 풀이 형식을 지원합니다.

### 1. BaekjoonHub

백준 및 프로그래머스 풀이가 저장된 BaekjoonHub 형식의 저장소를 연결할 수 있습니다.

예시:

```text
백준/Gold/10026. 적록색약/
├── README.md
└── 적록색약.py

프로그래머스/2/12914. 멀리 뛰기/
├── README.md
└── 멀리 뛰기.py
```

### 2. LeetHub — LeetCode SQL

LeetHub 형식으로 저장된 SQL 문제를 지원합니다.

예시:

```text
0175-combine-two-tables/
├── README.md
└── 0175-combine-two-tables.sql
```

문제 설명에 포함된 테이블 구조(`Table: ...`)와 예제 입출력 표를 바탕으로 테스트를 구성하고, PostgreSQL 16에서 결과 테이블을 비교합니다.

- `any order` 조건이 명시된 문제는 행 순서를 무시하고 비교합니다.
- `DELETE` 및 `UPDATE` 문제는 실행 후 테이블 상태를 비교합니다.
- LeetCode Python의 `class Solution` 형식은 아직 지원하지 않습니다.
- MySQL 전용 문법은 PostgreSQL에서 그대로 실행되지 않을 수 있습니다.

### 3. Native AlgoReplay Format

AlgoReplay 전용 형식으로 문제와 풀이를 관리할 수 있습니다.

```text
problem-folder/
├── problem.md
├── solution.py
├── metadata.json
└── tests.json       # 선택 사항
```

예제는 [`examples/`](examples)에서 확인할 수 있습니다.

### 4. Code-only Files

문제 설명과 메타데이터가 없는 코드 파일도 가져올 수 있습니다.

지원 예시:

- Jupyter 또는 Colab 노트북 (`.ipynb`)
- 텍스트 파일 (`.txt`)
- 확장자가 없는 코드 파일

```text
baekjoon/1371_가장 많은 글자.ipynb
programmers/Solutions/해시_위장.ipynb
sw_expert_academy/D2/1204_.ipynb
Codility/Arrays/CyclicRotation.ipynb
```

가져오기 동작:

- 파일명이나 노트북 내부 정보를 이용해 문제를 식별합니다.
- 문제 설명이 없는 경우 원문 링크 또는 검색어를 표시합니다.
- 노트북에 저장된 `solution(...)` 호출과 출력은 조건에 따라 테스트로 변환할 수 있습니다.
- 테스트가 없다면 입력을 제공해 과거 풀이의 기대 출력을 생성할 수 있습니다.
- 노트북의 Markdown 메모는 풀이가 노출될 수 있어 복습 중에는 숨기고, 제출 후 과거 풀이와 함께 보여 줍니다.
- 동일한 문제가 BaekjoonHub 형식으로도 존재하면 해당 형식을 우선합니다.
- 한 파일에 여러 문제가 혼합된 경우는 건너뜁니다.
- `.py` 풀이가 없는 폴더는 가져오기 대상에서 제외됩니다.

**테스트 신뢰성 안내:** 백준 문제의 기대 출력은 기존에 통과한 과거 풀이를 기준으로 생성할 수 있습니다. 따라서 해당 풀이가 모든 입력에서 올바르다는 보장은 없습니다. 중요한 문제는 공식 예제나 별도의 테스트 케이스를 추가해 검증하는 것이 좋습니다.

## Safe Code Execution

제출 코드는 호스트에서 직접 실행하지 않고 Docker 컨테이너에서 실행합니다. 실행 환경에 제한을 적용하고, 실행이 끝나면 컨테이너를 폐기합니다.

적용하는 주요 제한은 다음과 같습니다.

- 네트워크 접근 제한
- 읽기 전용 파일 시스템 및 허용된 임시 디렉터리 사용
- 비루트 사용자 실행 및 Linux capability 제거
- CPU·메모리·실행 시간 제한

실제 적용 범위는 Docker 실행 옵션과 환경 설정에 따릅니다.

AlgoReplay는 로컬 개인 사용을 전제로 하며, 신뢰할 수 없는 코드를 실행하는 공개 서비스 환경을 위한 완전한 격리 솔루션은 아닙니다. 보안 가정과 알려진 제한 사항은 [SECURITY.md](SECURITY.md)를 참고하세요.

## Limitations

- **복잡도 분석:** 정적 분석 기반의 추정치이며, 모든 알고리즘과 입력 크기에 대한 정확한 복잡도를 보장하지 않습니다.
- **실행 성능:** 측정 시간과 메모리는 하드웨어 및 실행 환경에 따라 달라질 수 있습니다.
- **기대 출력:** 과거 풀이로 생성한 기대 출력은 해당 풀이가 올바르다는 전제에 의존합니다.
- **지원 언어:** Python과 PostgreSQL 기반 SQL을 지원합니다.
- **지원하지 않는 문제:** Special Judge 및 인터랙티브 문제는 지원하지 않습니다.
- **SQL 분석:** SQL은 채점 및 리포트를 제공하지만 Python과 같은 AST 기반 알고리즘·복잡도 분석은 제공하지 않습니다.
- **약점 분석:** 실패 기록은 주제(topic) 단위로 관리하며, 세부적인 실수 유형까지 분류하지는 않습니다.
- **Agent Orchestration:** 도구를 동적으로 선택하는 LLM 기반 Agent Orchestrator는 아직 구현되어 있지 않습니다. 현재 파이프라인은 정해진 순서로 실행됩니다.

## Development

개발 의존성을 설치하고 테스트 및 코드 검사를 실행합니다.

```bash
pip install -r requirements-dev.txt

python -m pytest
ruff check .
```

Docker가 실행 중이지 않으면 일부 샌드박스 테스트가 건너뛰어질 수 있습니다.

코드 구조와 기여 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## License

[MIT](LICENSE) © 2026 ahyun39

연결한 문제 저장소의 문제 설명 및 기타 콘텐츠는 각 콘텐츠에 적용되는 라이선스를 따릅니다.