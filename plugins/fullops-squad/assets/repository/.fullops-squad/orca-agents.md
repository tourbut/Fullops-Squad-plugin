# Orca 역할 배정

역할·워크트리·브랜치는 1:1:1로 관리한다. 이름은 기본값이며 기존 레포에 맞게 바꾼다.
실제 repo id·경로·터미널 핸들은 전달 직전에 조회해 지시서에 기록한다.

| 역할 | 워크트리 이름 | 브랜치 | CLI | 기동 방식 |
|---|---|---|---|---|
| coordinator / 병합 책임자 | 기존 체크아웃 | 기본 브랜치 조회 | 현재 세션 | 기존 세션 |
| architect | architect | architect | 미정 | 미정 |
| backend_dev | backend | backend | 미정 | 미정 |
| frontend_dev | frontend | frontend | 미정 | 미정 |
| devops | devops | devops | 미정 | 미정 |
| qa_tester | qa | qa | 미정 | 미정 |
| docs | docs | docs | 미정 | 미정 |

Orca가 지원하는 에이전트는 해당 버전의 agent 옵션을 사용한다. 별도 모델 옵션이나 미지원 CLI는 command 방식으로 기동한다. 같은 worker에 두 터미널을 중복 기동하지 않는다.
미정인 배정은 사용자가 정한 뒤 실행한다. 진행 중인 worker를 재사용하려면 현재 작업 종료와 세션 분리를 확인한다.
