---
title: "FLOW-STOP-WAIT — Claude Code coordinator가 worker 실행 중 Stop 훅에 막혀 포그라운드 대기로 묶이지 않게 수정(#112)"
status: draft
updated: 2026-11-07
owner: dev
tasks: [FLOW-STOP-WAIT]
summary: "Claude Code coordinator가 worker 실행 중 Stop 훅에 막혀 포그라운드 대기로 묶이지 않게 수정(#112)"
attempt: a49b1e0fb43f4062a09550870f6b9bb3
base: 5161d7a5ca5b664634ef2797291f4faf1aff3687
subagent_level: off
test_level: lite
---

# FLOW-STOP-WAIT — Claude Code coordinator가 worker 실행 중 Stop 훅에 막혀 포그라운드 대기로 묶이지 않게 수정(#112)

현재 과제는 이 역할 인박스에서 관리한다. 같은 과제의 후속은 본문에 반영하고 다른 과제는 PLANS.md에 대기시킨다. 완료하면 완료 보고 전문을 채우고 work.py finish로 지시서·결과를 로그에 보존한다.

- 작성일: 2026-11-07
- From / To: main 체크아웃 세션 / dev 주 담당 세션
- 상태: ready
- 테스트 레벨 / 하위 에이전트 레벨: fullops.json 선택값과 같은 값
- 승인된 범위 / 추가 승인이 필요한 행위: `fullops/dev`의 구현·테스트·커밋 / push, PR, main 병합, 이슈 종료, 릴리스, `npm ci`, `core.longpaths` 변경, 독립 리뷰 생략
- 상위 의도: `docs/planning/intents/<묶음 키>.md` — 맡는 성공 기준 ID(묶음 작업이 아니면 없음)
- 담당 repo id / 워크트리 절대경로 / 브랜치: 53ea77e9-1236-434b-bae0-d909cea13d73 / C:/Users/shin/orca/workspaces/Fullops-Squad-plugin/dev / fullops/dev
- 병합 책임자 / 기본 브랜치: 사용자 지시를 받은 dev 주 담당 / main
- 복귀 repo id / 워크트리 / 터미널 핸들 / run id / task id / dispatch id: 없음. dev 직접 작업이라 사용자에게 직접 보고한다

`상태`는 과제 상태다. front matter `status`는 문서 상태(draft/review/approved, lint DOC-003 어휘)라 서로 다른 값이 맞다.

## 현재 상황과 확인 근거

- 이슈: https://github.com/tourbut/Fullops-Squad-plugin/issues/112 (제안 4개와 완료 기준을 먼저 읽는다)
- `plugins/fullops-squad/scripts/flow_gate.py:779`: worker가 실행 중이면 첫 Stop을 `decision: block`으로 막고 포그라운드 `orca_wait.py`를 요구한다. 2026-11-07 main 5161d7a에서 확인했다.
- 같은 위치에 "다른 일을 해야 하면 이유를 말하고 다시 끝내면 된다"는 안내가 있다. 이슈의 재현은 아직 유효하다.
- 이슈의 "함께 본 작은 문제" 3건은 이 과제 범위가 아니다. PLANS.md 대기 목록의 ISSUE112-SIDE에 있다.

## 적용 기준과 예외

공통 기준은 `.fullops-squad/rules/common/README.md`와 연결된 코딩·테스트·보안 규칙이다. 기준 커밋은 5161d7a다. 예외 없음.
사용자 방향(#132): 설치와 내부 로직에 npm 의존을 새로 더하지 않는다.

## 먼저 읽을 문서

- `plugins/fullops-squad/scripts/flow_gate.py` (Stop 처리)
- `plugins/fullops-squad/scripts/orca_wait.py`
- `plugins/fullops-squad/skills/fullops-orca/SKILL.md` (`## 대기 — coordinator`)
- `tests/flow-gate.py`
- `docs/flow-graph.md`

## 해야 할 일과 파일 소유권

- [ ] 호스트 판별 방법을 코드에서 확인하고 이슈 제안 중 적용할 방식을 정한다. 호스트를 판별할 수 없으면 Codex·grok의 대기 보장을 줄이지 않는 방식을 고른다.
- [ ] `flow_gate.py`와 필요한 경우 `orca_wait.py`·`fullops-orca` 스킬을 고친다.
- [ ] `tests/flow-gate.py`에 재현 시험을 더한다. worker 1개 실행 중 사용자 메시지 2건과 다른 역할 배정 2건을 포함한다.
- [ ] 스크립트·스킬이 바뀌면 `python3 scripts/build.py`로 dist를 다시 만든다.
- [ ] 릴리스 노트는 쓰지 않는다. 릴리스는 사용자 요청 때 한다.

## 완료 기준과 검증

UI 작업이 아니라 디자인 기준은 해당 없음이다.

- Claude Code coordinator가 worker 실행 중에도 포그라운드 대기 없이 사용자 메시지와 다른 역할 배정을 받는다. 완료 알림은 백그라운드 대기의 `task-notification`으로 받는다.
- Codex·grok의 기존 대기 동작은 그대로다.
- 증명 방법: `python3 tests/flow-gate.py`, `python3 tests/issue-mode.py` 통과, `lint.py --from 5161d7a5ca5b664634ef2797291f4faf1aff3687` ERROR 0.
- `plugins/**`가 바뀌면 lint의 `packaging`(`node tests/standard.cjs`)이 돈다. 이 워크트리에 `node_modules`가 없어 실패하면 원인을 적고 사용자에게 `npm ci` 승인을 묻는다.
- `review.py need`가 `ask`이면 사용자에게 묻는다. 스스로 생략하지 않는다.

## 갱신할 산출물

없음. `docs/flow-graph.md`의 게이트 표가 바뀌면 함께 고친다.

## 기대 산출물

`flow_gate.py` 수정과 재현 시험, 필요한 스킬 문구, 재생성한 dist, `docs/evaluations/qa-reports/FLOW-STOP-WAIT-test/report.md`.

## 제약·협업·후속

`subagent_level`은 off다. 직접 작업한다. 사용자가 켠 Workflow는 `rules/delegation.md`를 따른다.
끝나면 `work.py finish`로 인박스를 비우고 PLANS.md 대기 목록의 다음 과제를 연다.
이슈 #112는 사용자 승인 뒤 닫는다.

## 완료 보고

브랜치 / SHA / 변경 이유 / 검토 필요 / 검증한 것과 못 한 것 / 산출물·로그 링크 / 남은 일.
항목당 1~2줄로 쓰고 상세는 `qa-reports/<과제 키>-test/report.md`(역할별로 나눈 키는 `<키>-DEV` 그대로) 링크로 대신한다. 브랜치와 완료 SHA는 여기에 적는다. worker_done 메시지에만 적지 않는다. worker_done 본문 첫 줄은 `[완료] <과제 키> | 브랜치 <이름> | SHA <브랜치 HEAD>` 한 줄로 쓰고 SHA는 하나만 적는다. `남은 일`에 다른 역할의 후속(예: tester 독립 QA)을 쓰면 `work.py finish`가 PLANS.md `## 완료 보고 후속 요청`에 등재한다.
lint DEP-001이 있으면 파일별 의존성 변경 여부·필요성·표준 라이브러리 대안을 적는다. 의존성 변경이 없으면 그 근거를 적는다.
처리는 `fullops-work`, 회신은 `fullops-orca` 스킬을 따른다.
