---
title: ISSUE112-SIDE 검증 보고
status: draft
updated: 2026-11-07
owner: dev
tasks: [ISSUE112-SIDE]
summary: "#112 작은 문제 3건의 판단, 검사 결과, 경합 반복 결과, 한계"
---

# ISSUE112-SIDE 검증 보고

대상은 `fullops/dev` 505d579다. 기준은 main 0f918bb다. 테스트 레벨은 lite다.

## 통과한 검사

- `lint.py --from 0f918bb`, dev 워크트리, 505d579: 종료코드 0, ERROR 0, WARNING 5, 실행 불가 0.
- `python3 tests/integration-gate.py`, 505d579와 같은 작업 트리, 3회: 종료코드 0.
- `python3 tests/orca-wait.py`, 505d579와 같은 작업 트리: 종료코드 0.
- `record` 경합 반복: 8스레드, 메시지 3건, 50회. 예외 0건, 기록 150개, 잘못된 기록 0개, 남은 임시 파일 0개.

## 항목별 판단

| 항목 | 판단 | 근거 |
|---|---|---|
| `--ack` 동시 실행 JSON 오류 | 고침 | `record`를 원자적 쓰기로 바꿨다. 첫 시험에서 Windows `PermissionError`를 발견해 함께 처리했다. |
| 인박스 첫 줄 검사 시점 | 안내만 고침 | PreToolUse는 명령 결과를 볼 수 없다. 검사를 건너뛰면 잘못된 인박스로 worker가 시작된다. |
| `worker_done` 형식 처리 | 고침 | `integration.py set-sha`로 hold 없이 SHA를 기록한다. 없는 커밋은 거부한다. |

## 못 한 검증과 한계

- 경합은 한 프로세스의 스레드로 재현했다. 여러 `orca_wait` 프로세스의 실제 동시 실행은 하지 않았다.
- 파일이 있으면 Windows 공유 오류를 무시한다. 다른 쓰기가 필드를 보태는 중이면 그 값만 남는다. 다음 조회에서 다시 합친다.
- 배정 절차를 한 명령으로 줄이지는 못했다. 인박스 작성과 `worker-start`는 계속 별도 명령이다.
- WARNING 5건은 SIZE-001이다. 분할은 이 과제 범위가 아니다.
