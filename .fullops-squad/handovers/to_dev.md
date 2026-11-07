---
title: "ISSUE112-SIDE — orca_wait --ack 동시 실행 JSON 오류, 인박스 첫 줄 검사 시점, worker_done 형식 처리(#112 함께 본 작은 문제)"
status: draft
updated: 2026-11-07
owner: dev
tasks: [ISSUE112-SIDE]
summary: "orca_wait --ack 동시 실행 JSON 오류, 인박스 첫 줄 검사 시점, worker_done 형식 처리(#112 함께 본 작은 문제)"
attempt: b92a38045dab45b2b0fecc96a4c11cfa
base: 0f918bbea336772e1ca0a680bec14dc3897664a8
subagent_level: off
test_level: lite
---

# ISSUE112-SIDE — orca_wait --ack 동시 실행 JSON 오류, 인박스 첫 줄 검사 시점, worker_done 형식 처리(#112 함께 본 작은 문제)

현재 과제는 이 역할 인박스에서 관리한다. 같은 과제의 후속은 본문에 반영하고 다른 과제는 PLANS.md에 대기시킨다. 완료하면 완료 보고 전문을 채우고 work.py finish로 지시서·결과를 로그에 보존한다.

- 작성일: 2026-11-07
- From / To: 대기 목록(PLANS.md) / dev 주 담당 세션
- 상태: running
- 테스트 레벨 / 하위 에이전트 레벨: fullops.json 선택값과 같은 값
- 승인된 범위 / 추가 승인이 필요한 행위: `fullops/dev`의 구현·테스트·커밋, 사용자가 켠 Workflow / push, PR, main 병합, 이슈 종료, 릴리스, `core.longpaths` 변경, 독립 리뷰 생략
- 상위 의도: 없음(묶음 작업이 아니다)
- 담당 repo id / 워크트리 절대경로 / 브랜치: 53ea77e9-1236-434b-bae0-d909cea13d73 / C:/Users/shin/orca/workspaces/Fullops-Squad-plugin/dev / fullops/dev
- 병합 책임자 / 기본 브랜치: 사용자 지시를 받은 dev 주 담당 / main
- 복귀 repo id / 워크트리 / 터미널 핸들 / run id / task id / dispatch id: 없음. dev 직접 작업이라 사용자에게 직접 보고한다

`상태`는 과제 상태다. front matter `status`는 문서 상태(draft/review/approved, lint DOC-003 어휘)라 서로 다른 값이 맞다.

## 현재 상황과 확인 근거

- #112 "함께 본 작은 문제" 3건을 2026-11-07 9efee6b에서 확인했다.
- `integration.record`는 `open('x')`로 쓰고 다른 프로세스가 빈 파일을 읽을 수 있다.
- `integration.py:346`의 배정 검사는 PreToolUse에서 명령 실행 전 파일을 본다.
- 본문에서 SHA를 읽지 못한 완료 기록은 `pending`에 계속 남아 hold로만 지울 수 있다.

## 적용 기준과 예외

공통 기준은 `.fullops-squad/rules/common/README.md` 및 연결된 코딩·테스트·보안 규칙이다.
기준 커밋은 0f918bb다. 예외 없음. 사용자 방향(#132): npm 의존을 새로 더하지 않는다.

## 먼저 읽을 문서

- `plugins/fullops-squad/scripts/integration.py`
- `tests/integration-gate.py`
- `plugins/fullops-squad/skills/fullops-orca/SKILL.md`

## 해야 할 일과 파일 소유권

- [ ] `record`를 원자적 쓰기로 바꾸고 빈 파일과 Windows 경합을 처리한다.
- [ ] 배정 검사 실패 안내와 스킬에 명령 분리 순서를 적는다.
- [ ] `integration.py set-sha`를 추가한다.
- [ ] 시험을 더하고 dist를 다시 만든다.


## 완료 기준과 검증

- 동시 `record`가 JSON 오류로 죽지 않는다.
- 안전 검사는 그대로 두고 실패 안내가 해결 순서를 알려 준다.
- SHA를 직접 기록하면 hold 없이 통합 추적이 이어지고, 없는 커밋은 거부한다.
- 증명 방법: `python3 tests/integration-gate.py`, `python3 tests/orca-wait.py`, 경합 반복 실행, `lint.py --from 0f918bbea336772e1ca0a680bec14dc3897664a8` ERROR 0.

UI 작업이 아니라 디자인 기준은 해당 없음이다.

## 갱신할 산출물

없음.

## 기대 산출물

`integration.py` 수정, `fullops-orca` 스킬, `tests/integration-gate.py`, 재생성한 dist, `docs/evaluations/qa-reports/ISSUE112-SIDE-test/report.md`.

## 제약·협업·후속

세 항목이 `integration.py`에 모여 있어 직접 처리한다. 이 과제는 main 병합, 이슈 종료, 릴리스를 하지 않는다.

## 완료 보고

브랜치 / SHA / 변경 이유 / 검토 필요 / 검증한 것과 못 한 것 / 산출물·로그 링크 / 남은 일.
항목당 1~2줄로 쓰고 상세는 `qa-reports/<과제 키>-test/report.md`(역할별로 나눈 키는 `<키>-DEV` 그대로) 링크로 대신한다. 브랜치와 완료 SHA는 여기에 적는다. worker_done 메시지에만 적지 않는다. worker_done 본문 첫 줄은 `[완료] <과제 키> | 브랜치 <이름> | SHA <브랜치 HEAD>` 한 줄로 쓰고 SHA는 하나만 적는다. `남은 일`에 다른 역할의 후속(예: tester 독립 QA)을 쓰면 `work.py finish`가 PLANS.md `## 완료 보고 후속 요청`에 등재한다.
lint DEP-001이 있으면 파일별 의존성 변경 여부·필요성·표준 라이브러리 대안을 적는다. 의존성 변경이 없으면 그 근거를 적는다.
처리는 `fullops-work`, 회신은 `fullops-orca` 스킬을 따른다.
