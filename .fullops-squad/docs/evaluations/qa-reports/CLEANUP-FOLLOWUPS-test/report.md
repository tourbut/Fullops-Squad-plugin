---
title: CLEANUP-FOLLOWUPS 검증 보고
status: draft
updated: 2026-11-08
owner: dev
tasks: [CLEANUP-FOLLOWUPS]
summary: "PR #126 후속 8개 묶음의 검사 결과, 실패 확인, 측정, 한계"
---

# CLEANUP-FOLLOWUPS 검증 보고

구현 대상은 `fullops/dev` 7ef2723이다. 기준은 main 0cea3b8이다. 테스트 레벨은 lite다.

## 통과한 검사

- `npm test`, dev 워크트리, 7ef2723: 종료코드 0.
- `python3 tests/lint.py`, Linux 컨테이너(alpine:3.23), 7ef2723과 같은 작업 트리: 종료코드 0.
- 실제 Orca 1.4.251 읽기 전용 확인: `full_run`, `task_list`, `worker_view`가 `--full` 응답을 읽었다. 대상은 run_88a80b39c65f다.

## 수정 전 실패 확인

| 시험 | 수정 전 결과 |
|---|---|
| `gitlink_diff` | ValueError로 실패 |
| `timeout_ends_tree` | 5초 timeout에 30.1초 걸려 실패 |
| `interrupt_ends_parallel_tests`(Linux) | 시간 상한 assert로 실패 |
| `tests/issue-mode.py` 인계 시험 | 변경 묶음을 하나씩 뺀 7개 변형에서 모두 실패 |
| `tests/flow-gate.py` 새 assert | 수정 전 실패 |
| `tests/search-index.py` 일괄 읽기 | cat-file 프로세스 6개로 실패 |

## 측정

`search_index.py` 콜드 빌드는 이 저장소에서 코드 범위 25.77초가 1.02초로, 문서 범위 16.16초가 0.43초로 줄었다. 다른 에이전트가 함께 도는 동안의 1회 측정이다. PR #126의 426초는 재현하지 못했다.

## 독립 리뷰

1차 리뷰(`CLEANUP-FOLLOWUPS`, 37a3ba0)는 수락하지 않았다. 미해결 high 2건의 원인은 Orca `--full` 누락이었다. 시험 대역이 현재 CLI와 달라 시험으로 찾지 못했다. 7ef2723에서 고치고 대역을 맞췄다.

## 못 한 검증과 한계

- 실제 GitHub API와 실제 이슈 자동 모드 전체 흐름은 실행하지 않았다.
- `--full`이 없는 Orca(1.4.246 미만)는 시험하지 않았다. 이슈 모드는 조회 실패로 막힌다. flow-gate의 저장된 task 조회는 막지 않는다.
- macOS는 실행하지 않았다. POSIX 동작은 Linux 컨테이너로만 확인했다.
- `render.mjs` 파이프라인 시험은 Playwright가 없으면 `not_run`으로 넘어간다. 이 PC에서는 다른 작업 공간의 패키지로 한 번 통과했다.
- agy 경로 중 `~/.gemini/config/skills`는 공식 문서와 skills CLI 소스로만 확인했다. 실제 agy 세션은 실행하지 않았다.
- SIZE-002(추가 약 1,450줄): 사용자 결정 D014로 8개 묶음을 한 과제에서 처리했다. 그룹별 커밋으로 나눠 되돌리기 쉽게 했다.
- DEP-001(`package.json`): test 스크립트에 시험 1개를 더했다. 의존성 변경은 없다.

## 2차 리뷰 뒤 수정

2차 리뷰(`CLEANUP-FOLLOWUPS-R2`, 8b32dde)도 수락하지 않았다. 같은 원인이 `run-current`(신원 확인)와 `run-show`(하위 Run 권한)에 남아 있었다. 이번에는 스크립트의 Orca 호출 전체를 실제 1.4.251 응답과 대조했다. 이 두 곳 외에 읽는 필드가 어긋난 호출은 없었다.

- 시험 대역은 `--full`이 없으면 실제 CLI처럼 `run`·`spec`을 빼고 돌려준다.
- `--full` 6곳을 하나씩 빼면 시험이 모두 실패한다(issue-mode 4곳, flow-gate 1곳, integration-gate 1곳).
- 실제 Orca 1.4.251에서 coordinator 터미널로 `Orca.identity`와 `run-show --full`의 coordinator 일치를 확인했다.
- `claude plugin test mods/fullops-meter`: 81개 통과, 종료코드 0.
- CI 공백은 사용자 결정 D017로 PLANS.md 후속에 등재했다.
