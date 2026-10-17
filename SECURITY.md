# Security Policy

## Supported versions

보안 수정은 `main` 브랜치의 최신 버전에만 적용됩니다.

## 취약점 제보

**공개 이슈로 올리지 마세요.** GitHub의 [Private vulnerability reporting](https://github.com/ahyun39/algoreplay/security/advisories/new)으로 제보해 주세요.

다음 정보를 포함해 주시면 빠르게 확인할 수 있습니다.

- 영향 (예: sandbox 밖에서 코드 실행, 토큰 노출)
- 재현 방법 (최소한의 제출 코드 또는 저장소 구성)
- 사용한 OS, Docker 버전, AlgoReplay commit

## 위협 모델

AlgoReplay는 **한 사람이 자기 컴퓨터에서 실행하는 로컬 도구**를 전제로 설계되었습니다.

### 보호하는 것

제출 코드와 과거 풀이는 신뢰하지 않는 코드로 취급하며 항상 Docker container 안에서만 실행합니다.

| 제한 | 설정 |
|---|---|
| 네트워크 | `--network none` |
| 파일 시스템 | `--read-only`, 코드 폴더는 read-only mount, 쓰기는 64MB `tmpfs /tmp`만 |
| 권한 | `--user 65534:65534` (nobody), `--cap-drop ALL`, `--security-opt no-new-privileges` |
| 자원 | `--cpus 1`, `--memory 256m`, `--pids-limit 64`, 테스트당 시간 제한 |
| 수명 | 실행마다 새 container를 만들고 `--rm`으로 폐기, 시간 초과 시 `docker rm -f` |
| 정답 노출 | 테스트의 기대 출력은 디스크에 쓰지 않고 harness의 stdin으로만 전달 |

SQL 문제는 같은 제한(네트워크 차단, read-only, capability 제거, 메모리·pids 제한)을 건 `postgres:16-alpine` container에서 실행합니다. container 안의 `postgres` 사용자로 DB를 띄우고, 제출 SQL은 예제 테이블 권한만 받은 비관리자 role로 실행하며, 문장마다 `statement_timeout`을 겁니다. 기대 결과 표는 container에 넣지 않고 호스트에서 비교합니다.

Docker를 사용할 수 없으면 코드를 실행하지 않고 `SANDBOX_UNAVAILABLE`을 반환합니다. 호스트 interpreter로 대체 실행하는 경로는 없습니다. 호스트에서는 문법 검사를 위해 `ast.parse`만 수행합니다.

문제 설명(README HTML)은 Markdown으로 변환한 뒤 표시하며, HTML을 그대로 렌더링하지 않습니다.

### 보호하지 않는 것 (알려진 한계)

- **Docker 자체의 격리 한계.** container 탈출 취약점은 Docker/커널의 보안 수준에 의존합니다. 신뢰할 수 없는 여러 사용자의 코드를 실행하는 **공개 서비스로 배포하는 것은 지원하지 않습니다.** 그렇게 하려면 gVisor/Firecracker 같은 추가 격리, 인증, rate limit이 필요합니다.
- **인증 없음.** Streamlit 앱에는 로그인 기능이 없습니다. `localhost` 밖으로 포트를 열지 마세요.
- **function 채점의 자기 조작.** function 모드에서는 제출 코드가 harness와 같은 프로세스에서 실행되므로 결과를 조작할 수 있습니다. 자기 학습용 도구이므로 이를 막지 않습니다.
- **로컬 DB는 암호화되지 않습니다.** `algoreplay.db`에는 풀이 기록과 과거 풀이가 평문으로 저장됩니다.

## 외부로 전송되는 데이터

| 대상 | 언제 | 무엇을 |
|---|---|---|
| `api.github.com`, `raw.githubusercontent.com` | GitHub 동기화 시 | 저장소 이름, (설정한 경우) `GITHUB_TOKEN` |
| Anthropic API | `ANTHROPIC_API_KEY`를 설정했을 때만 | 문제 설명, 제출 코드, 과거 풀이, 분석 결과 |

그 외의 곳으로 데이터를 보내지 않으며, 사용 통계 수집(telemetry)도 없습니다. Streamlit의 사용 통계 수집은 `.streamlit/config.toml`에서 기본으로 꺼져 있고(`browser.gatherUsageStats = false`), 서버는 `localhost`에만 바인딩됩니다.

## Secret 관리

- `GITHUB_TOKEN`은 필요한 저장소에 대한 **읽기 권한(Contents: Read-only)만** 가진 fine-grained token을 권장합니다.
- `.env`와 `*.db`는 `.gitignore`에 포함되어 있습니다. 커밋 전에 `git status`로 한 번 더 확인하세요.
- UI의 token 입력칸에 넣은 값은 해당 브라우저 세션 메모리에만 있고 저장되지 않습니다.
