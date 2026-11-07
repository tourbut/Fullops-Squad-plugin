---
title: FLOW-STOP-WAIT 검증 보고
status: draft
updated: 2026-11-07
owner: dev
tasks: [FLOW-STOP-WAIT]
summary: "FLOW-STOP-WAIT 수정의 검사 결과, 호스트 판별 근거, 못 한 검증"
---

# FLOW-STOP-WAIT 검증 보고

대상은 `fullops/dev` 509b9bd다. 기준은 main 0f918bb다. 테스트 레벨은 lite다.

## 통과한 검사

- `lint.py --from 0f918bb`, dev 워크트리, 509b9bd: 종료코드 0, ERROR 0, WARNING 2, 실행 불가 0. issue-mode·flow-gate·packaging이 통과했다.
- `python3 tests/flow-gate.py`, dev 워크트리, 509b9bd의 작업 트리: 종료코드 0.
- `python3 tests/issue-mode.py`, dev 워크트리, 509b9bd의 작업 트리: 종료코드 0.
- 재현 대조: 새 `tests/flow-gate.py`를 수정 전 코드(0f918bb의 `plugins/`)로 실행했다. 종료코드 1이다. `run_in_background` assert에서 포그라운드 안내 문구로 실패했다.

## 호스트 판별 근거

| 호스트 | Stop 입력 | 확인 방법 |
|---|---|---|
| Claude Code 2.1.319 | snake_case `background_tasks`. shell 항목에 `command`가 있다 | `claude -p`와 임시 Stop hook으로 실제 입력을 받았다 |
| Codex 0.165 | 해당 필드가 없다 | `stop.command.input.schema.json`(rust-v0.165.0)을 읽었다 |
| grok 1.0.70 | camelCase `backgroundTasks`만 보낸다 | `~/.grok/docs/user-guide/10-hooks.md`를 읽었다 |

환경 변수는 판별에 쓰지 않았다. grok도 `CLAUDE_PROJECT_DIR`을 설정한다. `CLAUDECODE`는 하위 프로세스에 상속된다.

## 재현 시험의 범위

worker 1개 실행 중에 사용자 메시지 2건과 다른 역할 배정 2건을 넣었다. Stop은 매번 통과했다.
대기가 없으면 Stop을 한 번 막고 백그라운드 대기를 안내한다.
다른 Run의 대기, 잘못된 항목, grok의 camelCase 키, 처리하지 않은 question은 통과시키지 않는다.

## 못 한 검증과 한계

- Orca worker를 실제로 띄운 종단 시험은 하지 않았다. 시험은 가짜 Orca CLI를 쓴다.
- 설치된 Codex는 0.163이다. 스키마는 0.165로 확인했다.
- grok 입력은 문서로만 확인했다. 실제 입력은 캡처하지 않았다.
- `background_tasks`가 없는 이전 Claude Code는 기존처럼 포그라운드 안내를 받는다. 해당 필드가 추가된 버전은 확인하지 못했다.
- 대기 명령의 Run ID를 변수로 넘기면 이 Run의 대기로 인식하지 못한다. 이 경우 Stop을 한 번 막고 다음 Stop은 통과시킨다.
- WARNING 2건은 SIZE-001이다. `flow_gate.py`는 715줄에서 728줄로, `tests/flow-gate.py`는 280줄에서 310줄로 늘었다. 분할은 이 과제 범위가 아니다.
