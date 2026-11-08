---
title: CLEANUP-FOLLOWUPS-R3 리뷰
status: review
updated: 2026-11-08
owner: reviewer
summary: 5bc36e565a83 병합 전 독립 3차 리뷰 보고서. 2차 지적이 모두 해결되어 수락한다. 신규 low 5건
---

# CLEANUP-FOLLOWUPS-R3 리뷰

- 검토자 / CLI / 모델: 독립 리뷰어 세션 `reviewer-535fb45e-acd9-44dd-9ec5-cf1d9f5510fb` / Claude Code / `claude-opus-5-5`. 1·2차와 다른 세션이다. AI 판단이며 OCR 자동 판정이 아니다.
- base SHA / head SHA / merge-base: `0cea3b8b990c` / `5bc36e565a83` / `0cea3b8b990c`
- OCR 버전 / 적용 규칙: open-code-review v1.13.6 / snapshot의 `.fullops-squad/rules/common/`(README와 연결된 세 규칙), `.fullops-squad/review/rule.json`(`34c8f6e8…`). 지시서의 예외는 없다.
- 요구사항·완료 기준 원천: 지시서 `review-brief-r3-final.md`, 2차 리뷰 보고서, `PLANS.md`, `handovers/to_dev.md`
- 전체 변경 / OCR 대상 / 제외 / reviewed / skipped / 범위 차이: 87 / 45 / 42 / 13 / 74. 지시서 범위(2차 이후 변경과 그 호출 경로) 밖 코드 변경은 없다.
- lint(`lint.json`) ERROR / WARNING / 실행 불가와 사유: 0 / 14 / 0. head는 `5bc36e5`다. issue-mode, flow-gate, lint-gate, packaging 통과. jev-route는 경로 불일치로, full(`npm test`)은 `test_level=lite`로 skipped. 경고는 SIZE-001 12건, DEP-001, SIZE-002다.
- SIZE-002: 지시서에 예상 규모가 없다 / 실제 추가 1,563줄(상한 400) / 사용자 결정 D014로 8개 묶음을 한 과제에서 처리했다. 2차 이후 추가는 시험 중심의 약 50줄이다. 수락한다.
- DEP-001: `package.json`은 test 스크립트에 `tests/setup-scope.py`만 더했다. 2차 이후 변경은 없다. 의존성 변경은 없다.
- UI 디자인: 해당 없음. 2차 이후 변경에 UI가 없다.

SIZE-001 경고 12건은 기존 큰 파일의 증가다. 2차와 같이 차단하지 않는다.

## 검토 범위

2차 이후 변경(`git diff 8b32dde..5bc36e5`)을 중심으로 보았다. 코드 변경은 267b1b1 한 커밋이다. 5bc36e5는 기록 문서다.

reviewed 13개:

- 2차 이후 바뀐 원본: `issue_mode.py`, `flow_gate.py`, `lint.py`, `docs/issue-auto-mode.md`, `tests/issue-mode.py`, `tests/flow-gate.py`, `tests/integration-gate.py`, `tests/motion.py`, `PLANS.md`, `CLEANUP-FOLLOWUPS-test/report.md`
- 호출 경로로 읽은 파일: `integration.py`(`record`, `task_list`, `worker_view`, `denial`), `review.py`(`released`의 Orca 읽기), `to_dev.md`(완료 보고 줄)

skipped 74개의 내역과 영향:

- `dist/**` 수정 20개: 원본과 5bc36e5의 git blob ID가 directory·native 모두 같음을 확인했다. 영향 없음.
- `dist/**` 삭제 12개: 원본의 `.gitkeep` 삭제와 대응한다. 영향 없음.
- 1·2차 리뷰 기록 10개, Jev 기록 4개: prepare가 채운 자동 기록이다. 2차 보고서만 대조 대상으로 읽었다.
- 2차 이후 바뀌지 않은 28개(meter, `deps.py`, `search_index.py`, `render.mjs`, 원본 `.gitkeep` 삭제, 그 밖의 시험 등): 2차가 수락을 막지 않는다고 판단했다. 지시서에 따라 다시 보지 않았다. 이 파일의 새 결함은 2차 판단에 의존한다.

## 발견 사항

### 2차 지적의 해결 상태(집중 질문 1)

| 2차 항목 | 판정 | 근거 |
|---|---|---|
| high: `Orca.identity`의 `run-current` | 해결 | `issue_mode.py:258`에 `--full`을 더했다. 실제 1.4.251에서 concise는 `{"runId": …}`, full은 `{"run": …}`다. 대역도 같은 형식이다. |
| medium: `dispatch_run`의 `run-show` | 해결 | `issue_mode.py:1108`에 `--full`을 더했다. 실제 `run-show --full`의 `run.coordinator_handle`이 coordinator 핸들(`term_4f8233dd…`)과 같다. |
| medium: 시험 대역 | 해결(잔여 low 2) | `run-current`·`run-show`·`task-list` 대역이 `--full` 없으면 실제처럼 `run`·`spec`·`count`·`page`를 뺀다. check 메시지와 reconcile의 worker-list 대역은 아래 low로 남겼다. |
| medium: meter 시험 근거 | 해결 | 시험 보고서 56줄에 `claude plugin test mods/fullops-meter` 81개 통과, 종료코드 0이 있다. 구현자 기록이며 다시 실행하지 않았다. |
| medium: CI 공백의 사용자 판단 | 해결 | `PLANS.md:59`에 사용자 결정 D017과 재개 조건이 있다. "1차가 판단" 문구도 고쳤다. D014~D016과 같은 인라인 기록 방식이다. 사용자 발화 원문은 확인하지 못했다. |

2차 low 중 SIGHUP, 최소 Orca 버전 문서, `ASSIGN`·`motion.py` 공백은 해결됐다. 나머지(시작 경합, 시험의 SIGINT, history 크기, bare `git push`, meter 캐시, `task_listing` 중복)는 PLANS 후속에 있다.

### 신규 발견

| 심각도 | 파일·줄 | 재현 조건과 영향 | 상태 |
|---|---|---|---|
| low | `integration.py:110-113` | `record`가 `run_id`를 읽는다. 호출자는 모두 concise `check --peek`를 쓰고 concise 메시지에는 `run_id`가 없다. 그래서 `task-list`가 `--run` 없이 호출되어 호출 터미널의 bound Run 목록을 쓴다. bound Run이 메시지의 Run이면 결과가 같다. 아니면 리뷰 worker_done이 병합 대기로 기록되고 다음 dispatch가 막힌다(`integration.py hold`로 해제 가능, 추정). 기준 커밋부터 있던 코드다. | 후속 가능 |
| low | `tests/integration-gate.py:222-228` | 새 시험의 메시지가 실제에 없는 `run_id`를 갖고 대역은 `--run`을 무시한다. 위 차이를 시험이 숨긴다. 이 시험은 lint.json 등록 명령에 없고, 기록된 `npm test`는 7ef2723 기준이다. 267b1b1 이후 통과 기록이 없다. | 후속 가능 |
| low | `orca_wait.py:58-60` | `summarize`가 `from_handle`·`created_at`을 읽지만 concise 메시지에는 `from`만 있다. heartbeat 요약의 키와 시각이 None이 된다. 표시 전용이다. 기준 커밋부터 있던 코드다. | 후속 가능 |
| low | `lint.py:538-540` | SIGHUP을 무조건 `default_int_handler`로 바꾼다. `nohup`처럼 SIG_IGN으로 상속된 lint가 이제 터미널 종료에 중단된다. 결과·stamp를 쓰지 않으므로 데이터 손실은 없다. 코드 읽기 근거다. 수정: `signal.getsignal(SIGHUP) is SIG_IGN`이면 바꾸지 않는다. | 후속 가능 |
| low | `tests/issue-mode.py:984-991` | reconcile의 worker-list 대역은 `--full`을 무시한다. `issue_mode.py:871`의 `--full`을 빼도 시험이 실패하지 않을 수 있다(코드 읽기, 미실행). 빼면 concise에 `page`가 없어 not_dispatched 경로가 막히는 쪽(fail-closed)으로 간다. | 후속 가능 |

### 실제 응답 대조(집중 질문 2)

구현자 주장은 대부분 맞다. 다만 "두 곳 외에는 어긋난 필드가 없다"는 정확하지 않다. `check` 메시지의 필드가 남았다. 둘 다 기준 커밋부터 있던 코드이고 수락을 막지 않는다.

읽기 전용 명령만 썼다. Orca는 1.4.251이다. 이 터미널은 worker라 coordinator 신원의 응답은 직접 보지 못했다.

| 호출 | 읽는 코드 | 결과 |
|---|---|---|
| `status`(concise, `--full` 미지원) | `Orca.identity`의 `caller` | 최상위 `caller`를 `Orca.call`이 합친다. 이 터미널은 `ORCA_AGENT_SESSION_ID`가 없어 `caller`가 없고 native 경로를 탄다. agent 세션의 `caller`는 미확인. |
| `terminal show`(concise) | `identity`, lease | 일치. `handle`, `connected`, `orphaned`, `incarnationId`, `lastOutputAt`가 있다. `--full`이면 이 필드가 없으므로 concise가 맞다. |
| `run-current --full` | `identity` | 일치. concise `{"runId":null}`, full `{"run":null}`. `--from <coordinator>`는 `consumer_fenced`. |
| `run-show --full` | `dispatch_run` | 일치. `run.id`, `run.coordinator_handle`이 있다. concise는 `runId`, `objective`, `removedWork`뿐이다. |
| `task-list --full`, `worker-list --full` | `full_run`, `reconcile`, `worker_job`, flow-gate, integration | 2차 확인과 같다. concise worker-list는 `page`가 없고 `liveness`가 평면 문자열이다. |
| `worker-show`, `worker-list`, `worker-read`(concise) | `worker_view`, `run_state`, `released` | 일치. 평면 `dispatchId`, `taskId`, `runId`, `terminal`, `workspace`, `outcome`, `state`. worker-read는 `projection.workspace`·`resource`가 있다. |
| `worktree show`(concise) | `baseline_denial` | 일치. `worktree.path`가 있다. `--full`은 실패한다. |
| `terminal list`(concise) | `released` | 일치. `terminals[].handle`. |
| `check --peek`(concise) | `integration.record` | **불일치(low)**: `run_id` 없음. `type`, `id`, `body`, `payload.taskId`는 있다. |
| `check --wait`(concise) | `orca_wait.summarize` | **불일치(low)**: `from_handle`, `created_at` 없음. 판정에 쓰는 `type`, `deliveryId`는 있다. |

check 메시지 형식은 `orchestration inbox --terminal run:run_88a80b39c65f`의 concise/full 응답으로 보았다. concise 행은 `id, type, from, to, subject, handled, body, payload(dict)`이고, full 행은 `run_id, from_handle, created_at`과 문자열 `payload`를 갖는다. 이 터미널의 `check --peek`·`--all`은 빈 목록이라 같은 투영이라고 추정했다.

### 시험 대역과 `--full`(집중 질문 3)

- `orca_answers`는 `--full`이 없으면 `{runId, objective}`를 준다. `identity`의 `info`가 비어 `ValueError`가 나고 두 identity assert가 실패한다.
- `dispatch_run` 대역은 `--full`이 없으면 concise를 준다. `coordinator_handle`이 없어 `boundary`가 거부 문구를 돌려 `is None` assert가 실패한다.
- `Listing`, `SettledOrca`, 가짜 task-list(flow-gate), integration-gate의 task-list 대역은 `--full`이 없으면 `spec`을 뺀다. 실제 concise task-list(`id`, `status`, `title`)와 맞다.
- 남은 차이는 위 low 2건(check 메시지의 `run_id`, reconcile worker-list)이다.
- 이 판단은 코드 읽기다. 지시에 따라 시험을 실행하지 않았다. 구현자는 6곳을 하나씩 빼면 모두 실패한다고 기록했다.

### 정상 동작을 막는 새 경로(집중 질문 4)

- Orca 1.4.246 미만: `run-current`·`run-show`의 `--full`이 실패해 이슈 모드 활성화와 하위 Run 배정이 막힌다. 안전 쪽이며 `docs/issue-auto-mode.md`에 최소 버전을 적었다. 1.4.246 이상에서는 2차 이전에도 막혀 있었으므로 새 차단이 아니다.
- SIGHUP: 위 low 1건(nohup 상속)이다.
- `ASSIGN`, `motion.py` 공백: 동작 변화 없음.
- 그 밖의 새 차단 경로를 찾지 못했다.

## 검증 및 남은 제약

- 재사용 증거: `lint.json`. attempt `991cf2d7…`, head `5bc36e5`, base `0cea3b8`, `test_level=lite`. 원본 로그는 `D:\workspace\Fullops-Squad-plugin\.git\worktrees\dev\fullops-gate\logs`다. 같은 Windows PC의 dev 체크아웃 결과로 판단했다. 환경 동일성은 자동 판정되지 않는다.
- 2차 이후 코드 변경은 lint 등록 명령 4개로 실행됐다. `tests/integration-gate.py`는 등록 명령 밖이며 267b1b1 이후 실행 기록이 없다(low).
- 실제 Orca 1.4.251 읽기 전용 확인: `status`, `terminal show`, `terminal list`, `worktree show`, `run-current`, `run-show`, `worker-show`, `worker-list`, `worker-read`, `check --peek/--all`, `inbox`, `task-list`. 각 concise·full을 비교했다.
- 지시에 따라 `lint.py`, 전체 시험, 임시 시험, `review.py check`를 실행하지 않았다. 상태를 바꾸는 Orca·GitHub 명령도 실행하지 않았다.
- 미실행: coordinator 터미널의 `run-current --from`(fenced), agent 세션의 `status.caller`, 실제 GitHub, 이슈 자동 모드 전체 흐름, POSIX 실행, meter 시험.
- snapshot은 clean이고 HEAD는 리뷰 SHA 그대로다.

## 대화 미참조 인계 점검

| 확인 항목 | 정본 경로/절 | 결과(확인/미확인/해당 없음) | 누락·오래된 정보·후속 |
|---|---|---|---|
| 현재 요구와 결정 이유 | `PLANS.md` 31줄(D014~D016), 59줄(D017) | 확인 | 없음 |
| 구조와 구현/미완료 상태 | `handovers/to_dev.md` 완료 보고, 시험 보고서 `2차 리뷰 뒤 수정` | 확인 | `to_dev.md`의 검증 줄은 7ef2723 시점이다. 267b1b1 수정은 시험 보고서에만 있다 |
| 실행·검증 방법과 증거 | `CLEANUP-FOLLOWUPS-test/report.md`, `lint.json` | 확인 | integration-gate 실행 기록 없음(low) |
| 운영·복구(해당 시) | `docs/issue-auto-mode.md` 최소 Orca 버전 | 확인 | 없음 |
| 다음 작업·담당·재개 조건 | `PLANS.md` `CLEANUP-FOLLOWUPS 리뷰 후속` | 확인 | 이 리뷰의 low 5건을 PLANS 후속에 더한다 |
| 로컬 링크·절 접근/지원 한계 | `to_dev.md` → 시험 보고서 | 확인 | 깨진 링크 없음 |
| snapshot 정리 후 정본 접근 | 이 리뷰 폴더(기록 체크아웃) | 확인 | 아직 미커밋이다. 병합 책임자가 보존한다 |

## 검토 결론

**수락한다.** 미해결 critical 0, high 0, medium 0, low 5(신규)다.

2차의 high 1건과 medium 4건은 해결됐다. 2차 이후 변경은 좁고, 실제 Orca 1.4.251 응답과 대조한 결과 판정에 쓰는 필드는 모두 맞다. 남은 불일치 2건(`check` 메시지의 `run_id`, `from_handle`·`created_at`)은 기준 커밋부터 있던 코드이고 피해가 조건부·표시 전용이다.

병합 전 필요한 일은 없다. low 5건은 PLANS 후속에 등재한다. `integration.record`의 `run_id`는 다음 integration 변경 때 check에 `--full`을 쓰거나 `to`의 `run:` 접두사를 읽게 고치고 시험 메시지를 concise 형식으로 바꾸는 것이 좋다.

이 판단은 코드 검토와 읽기 전용 조회이며 시험 통과의 증거를 대신하지 않는다. `review.py check` 통과도 이 판단을 자동 보증하지 않는다.
