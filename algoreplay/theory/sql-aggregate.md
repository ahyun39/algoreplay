# SQL 집계 (GROUP BY)

## 1. 핵심 개념
같은 값을 가진 행을 묶어(`GROUP BY`) 묶음마다 `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` 하나를 계산한다.

## 2. 동작 원리
실행 순서는 `FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY`. `WHERE`는 묶기 전 행을, `HAVING`은 묶은 뒤 그룹을 거른다.

## 3. 시간복잡도
그룹을 해시나 정렬로 만든다. 대략 O(N) ~ O(N log N).

## 4. SQL에서
`SELECT dept, COUNT(*) FROM emp GROUP BY dept HAVING COUNT(*) >= 5`. 조건부 개수는 `SUM(CASE WHEN … THEN 1 ELSE 0 END)` 또는 PostgreSQL의 `COUNT(*) FILTER (WHERE …)`.

## 5. 언제 사용하는가
"~별 개수/합계/평균", "~번 이상인 것", 비율 계산.

## 6. 자주 하는 실수
- `SELECT`에 그룹 키도 집계도 아닌 열을 넣음 (PostgreSQL은 오류, MySQL은 임의 값)
- 정수끼리 나누어 비율이 0이 됨 (`::numeric` 또는 `* 1.0`)
- `COUNT(col)`은 `NULL`을 세지 않음

## 7. 연습 질문
전체 요청 중 'confirmed' 비율을 사용자별로 소수 둘째 자리까지 구하려면 어떤 식을 써야 할까?
