---
title: CLEANUP-FOLLOWUPS-R2 리뷰
status: review
updated: 2026-11-08
owner: reviewer
summary: 8b32dde300fa 병합 전 독립 재리뷰 보고서. 미해결 high 1건으로 수락하지 않는다
---

# CLEANUP-FOLLOWUPS-R2 리뷰

- 검토자 / CLI / 모델: 독립 리뷰어 세션 `reviewer-019c7396-9b85-4b65-a85f-692a48ef5481` / Claude Code / `claude-opus-5-5`. `worker-show --full`의 `launch.effective`는 `claude`, `claude-opus-5-5`, `high`다. AI 판단이며 OCR 자동 판정이 아니다.
- base SHA / head SHA / merge-base: `0cea3b8b990c` / `8b32dde300fa` / `0cea3b8b990c`
- OCR 버전 / 적용 규칙: open-code-review v1.13.6 / `fullops-common-0.3.6`(snapshot `.fullops-squad/rules/common/`), `.fullops-squad/review/rule.json`(`34c8f6e8…`). 지시서의 예외는 없다.
- 요구사항·완료 기준 원천: `.fullops-squad/handovers/to_dev.md`, PLANS.md, 1차 리뷰 보고서
- 전체 변경 / OCR 대상 / 제외 / reviewed / skipped / 범위 차이: 79 / 39 / 40 / 40 / 39. 지시서 범위 밖 코드 변경은 없다.
- lint(`lint.json`) ERROR / WARNING / 실행 불가와 사유: 0 / 14 / 0. issue-mode, flow-gate, lint-gate, packaging 통과. jev-route는 경로 불일치로, full은 `test_level=lite`로 skipped. 경고 14건은 SIZE-001 12건, DEP-001, SIZE-002다.
- SIZE-002: 지시서에 예상 규모가 없다 / 실제 추가 1,512줄(상한 400) / 사용자 결정 D014로 8개 묶음을 한 과제에서 처리했다. 그룹별 커밋이 있어 수락한다. 시험 보고서의 "약 1,450줄"은 1차 시점 수치에 가깝다.
- DEP-001: `package.json`은 test 스크립트에 `tests/setup-scope.py`만 더했다. 의존성 변경은 없다. 완료 보고에 기록됐다.
- UI 디자인: 해당 없음. fullops-meter는 터미널 mod이고 지시서가 UI 작업이 아니라고 적었다. 디자인 lint와 테마 전환은 실행하지 않았다.

SIZE-001 경고 12건은 기존 큰 파일의 증가다. 이번 후속 범위에서는 차단하지 않는다.

## 검토 범위

`dist/**`와 하네스 자동 기록을 뺀 34개와 원본 `.gitkeep` 삭제 6개를 reviewed로 기록했다. `issue_mode.py`는 변경 함수와 호출 경로를 읽었다. 시험 파일은 변경분을 모두 읽었다. 1차 보고서는 판단을 옮기지 않고 대조 대상으로만 읽었다. 원본 `.gitkeep`의 경로는 저장소 전체 grep에서 시험 외 참조가 없었다.

생략 39개의 내역과 영향:

- `dist/**` 수정 20개: `plugins/`·`docs/` 원본과 git blob ID가 같음을 확인했다. 영향 없음.
- `dist/**` 삭제 12개: 원본의 `.gitkeep` 삭제와 대응한다. 영향 없음.
- 1차 리뷰 기록 5개와 Jev 기록 2개: prepare가 생략으로 채운 자동 기록이다. 영향 없음.

## 발견 사항

| 심각도 | 파일·줄 | 재현 조건과 영향 | 상태 |
|---|---|---|---|
| high | `issue_mode.py:258` | `Orca.identity`가 `run-current`를 `--full` 없이 읽고 `.get('run')`을 본다. 현재 응답 키는 `runId`다. `enable`과 token을 쓰는 모든 명령(`sync`, `reconcile`, `claim`, `wait` 등)이 신원 확인에서 실패한다. | 미해결 |
| medium | `issue_mode.py:1108` | `dispatch_run`이 `run-show`를 `--full` 없이 읽는다. 현재 응답에 `run.coordinator_handle`이 없어 `subagent_level`이 off가 아니면 worker의 하위 Run 배정이 항상 거부된다. | 미해결 |
| medium | `tests/issue-mode.py:281-283,599` | 대역이 `run-current`·`run-show`를 `{'run': …}`로 돌려주고 `--full` 없는 인자를 assert한다. 위 2건을 시험이 숨긴다. `reconcile` 본문, `flow_gate.task_listing`, `integration.record`의 `--full`은 빼도 시험이 실패하지 않는다. | 일부 해결 |
| medium | `CLEANUP-FOLLOWUPS-test/report.md:39` | 시험 보고서·완료 보고·lint 어디에도 `mods/fullops-meter` 시험의 실행 결과가 없다. meter 시험은 `npm test`와 CI에 없다. `register.tsx`·`flow.ts` 변경의 실행 근거가 없다. | 미해결 |
| medium | `PLANS.md:59` | CI 공백이 그대로다. PLANS는 "1차가 후속으로 넘겨도 된다고 판단"이라 적었지만 1차는 "고치거나 사용자 판단으로 등재"를 요구했다. 사용자 판단 기록이 없다. | 미해결 |
| low | `lint.py:407` | 스레드가 `RUNNING`에 넣기 전에 중단되면 그 프로세스는 timeout까지 남는다. 병렬 시작 직후의 짧은 구간이다. | 후속 가능 |
| low | `lint.py:539` | POSIX에서 SIGTERM만 정리한다. 터미널 종료(SIGHUP)면 lint만 죽고 새 세션의 시험 프로세스가 timeout까지 남는다. 코드 읽기 근거다. | 후속 가능 |
| low | `tests/lint.py:566` | SIGINT가 무시된 채 상속되면(스크립트의 `… &`) 신호가 듣지 않아 60초 뒤 시험이 실패한다. 코드 읽기 근거다. | 후속 가능 |
| low | `issue_mode.py:931` | `sync`마다 Run 전체 `--full` worker 목록을 잘라내지 않고 history에 쌓는다. 실측 행당 약 2KB라 100행이면 호출당 약 200KB다. 모든 hook이 이 JSON을 읽는다. | 후속 가능 |
| low | `issue_mode.py:1158` | 1차 지적 그대로다. 이전 coor의 bare `git push`, `gh issue comment 2`는 fencing을 통과한다. PLANS에 있다. | 후속 가능 |
| low | `docs/issue-auto-mode.md:33` | Python 코드가 `--full`을 요구하지만 최소 Orca 버전(1.4.246)이 문서에 없다. 70줄의 실제 검증 기록은 1.4.222다. | 후속 가능 |
| low | `register.tsx:303` | 1차 지적 그대로다. 일시 읽기 실패로 얻은 경로를 60초 캐시한다. 표시 전용이다. PLANS에 있다. | 후속 가능 |
| low | `flow_gate.py:119,408` | `ASSIGN =re.compile` 공백 오류가 들어왔다. `tests/motion.py`의 `small ={`, `templates =(`도 같다. `task_listing`은 `integration.task_list`와 중복이다. | 후속 가능 |

### high와 run-show의 재현

읽기 전용 명령만 썼다. Orca는 1.4.251이다. 임시 시험은 만들지 않았다.

```
orca orchestration run-show --id run_88a80b39c65f --json
  → result 키: runId, objective, removedWork. run 없음
orca orchestration run-show --id run_88a80b39c65f --full --json
  → result.run.coordinator_handle 있음
orca orchestration run-current --json
  → {"ok":true,"result":{"runId":null}}
orca orchestration run-current --full --json
  → result: {"run":null}
```

`Orca.identity`의 판정은 `info.get('id') != run`이고 `info`는 `.get('run') or {}`다. `main`은 `--token` 명령마다 `owner_identity`를 먼저 부른다(`issue_mode.py:1511-1515`).

**한계**: `run-current`의 비어 있지 않은 응답은 직접 보지 못했다. 이 터미널은 worker라 `--from <coordinator>`가 `consumer_fenced`로 거부됐다. 키 이름이 concise `runId`, full `run`으로 갈리는 점과 `run-show`의 같은 차이로 판단했다. coordinator 터미널에서 다음 한 줄로 확정한다.

```
orca orchestration run-current --from <coordinator handle> --json
```

결과에 `run.id`가 있으면 이 high는 철회한다. 수정은 258줄과 1108줄에 `--full`을 더하고 대역을 실제 응답 형식으로 바꾸는 것이다.

심각도 근거: 안전 쪽으로 막히므로 데이터 손실은 없다. 다만 이슈 자동 모드 전체를 켤 수 없고, 이번 과제 묶음 D의 동작(fencing, intent 복구, sync)이 실제로 실행되지 않는다. 기준 커밋에도 있던 결함이지만 1차 high와 근본 원인이 같고, 시험 보고서가 근본 원인을 고쳤다고 적었다.

## 집중 질문 답변

### 1. 1차 high 2건과 medium 4건

| 1차 항목 | 판정 | 근거 |
|---|---|---|
| high: worker가 무관하게 판정되어 boundary 생략 | 해결 | `integration.task_list`가 `--full`을 쓰고, 이슈의 Run에서 spec을 못 읽으면 fail-closed다. 실제 행의 `spec`을 확인했다. |
| high: `sync`·`reconcile --not-dispatched` 항상 실패 | 호출은 해결, 실행은 미해결 | `full_run`과 `reconcile`의 읽기는 실제 응답과 맞는다. 그러나 `--token` 명령은 그 앞의 `identity`에서 실패한다. 근본 원인(concise 응답)이 2개 호출에 남았다. |
| medium: 대역이 CLI와 다름 | 일부 해결 | `Listing`만 실제 형식이다. `NestedOrca`는 `--full`을 무시하고, `run-current`·`run-show` 대역은 틀렸다. |
| medium: `npm test` 결과·보고서·완료 보고 없음 | 해결 | 7ef2723 기준 기록이 있다. 8b32dde의 추가 변경은 문서 3개뿐이다. meter 시험 근거만 빠졌다(별도 finding). |
| medium: POSIX 중단 | 해결 | `RUNNING` 정리와 SIGTERM 변환으로 고쳤다. 남은 경계는 low 3건이다. |
| medium: CI 공백 | 미해결 | `ci.yml`은 바뀌지 않았다. 후속 등재의 사용자 판단 기록이 없다. |

### 2. `worker_job`

- **범위 검사를 건너뛰는 경로**: 이슈 Run의 worker에서 spec을 못 읽는 경로는 닫혔다. 남은 경로는 다음과 같다.
  - 문서화된 shortcut: 유예 뒤 늦게 시작한 worker. spec이 이전 task key라 무관한 worker로 판정된다.
  - 끝난 attempt의 미연결 worker: 새 attempt에서 같은 판정을 받는다. attempt 전환이 확정 종료를 요구하므로 실제로는 위 shortcut과 같다.
  - `worker-start`의 인자에는 key가 있지만 실제 spec에는 없는 경우: `dispatch_run`은 명령 문자열만 본다. coor 자신이 만들어야 하므로 위협이 낮다(추정).
- **정상 worker를 잘못 막는 경로**: `task_list`가 실패하면 그 호출을 막지만 기준 커밋도 같았다. 다음 호출이 다시 조회하고 생략 기록을 남기지 않는다. Orca 1.4.246 미만은 항상 막힌다(구현자가 공개한 한계).
- **Run이 다른 worker의 기록**: 안전하다. 조건은 다음과 같다.
  - 판정 근거가 `child_runs` 등록이고, 등록되면 `scope`가 바뀌어 기록이 무효가 된다.
  - 등록은 `worker-start` 전에 `reserve_dispatch`가 한다. 판정 결과는 기준 커밋과 같고 기록은 조회만 줄인다.
  - hook을 거치지 않은 배정은 원래 이 검사 밖이다.

### 3. `--full` 응답

| 호출 | 읽는 코드 | 실제 응답과 일치 |
|---|---|---|
| `task-list --full` | `full_run`, `reconcile`, `worker_job`, `abandon_intents`, `flow_gate`, `integration.record` | 일치. `spec`, `count`가 있고 `page`는 없으며 코드가 허용한다. |
| `worker-list --full` | `full_run`, `reconcile` | 일치. `page.total`·`hasMore`, 행의 `taskId`, `projection.liveness.verdict`. 해제된 worker의 verdict는 `exited`다. |
| `worker-list`(concise) | `flow_gate.run_state` | 일치. `outcome`이 없으면 `state`로 읽는다. |
| `worker-show`(concise) | `worker_job`, `settled_in_runtime` | 일치. 평면 `terminal`, `workspace`, `runId`. |
| `worker-read`(concise) | `review.py:316` | 일치. `projection.workspace`가 있다. |
| `task-list --brief --full`, `worker-list --full`, `run-current --full` | meter | 일치. spec이 160자로 잘리고 `parseRows`·`parseRunId`가 읽는다. |
| `run-current`(concise) | `Orca.identity` | **불일치(high)** |
| `run-show`(concise) | `dispatch_run` | **불일치(medium)** |

history 크기: 위 low 참고. 민감 정보는 새 노출 경로가 없다.

- `reconciled` 기록은 `redact`를 재귀로 거친다. 저장 위치는 token이 이미 있는 로컬 `state.sqlite`다. `status.json`은 필드를 골라 쓰므로 history가 나가지 않는다.
- `--full` 행의 터미널 핸들과 경로는 로컬 식별자다. 응답에서 자격 증명 필드를 보지 못했다. `spec`·`result`의 임의 형식 비밀은 `redact`가 패턴으로만 잡는다.
- `reconciled_not_dispatched` 기록은 `redact` 없이 저장하지만 task·worker가 0건일 때만 쓴다.

### 4. `lint.py`

- 경합: 위 low 1건. 프로세스가 끝난 직후의 `killpg`는 `OSError`로 넘어가고, Windows의 닫힌 job 핸들은 `TerminateJobObject`가 실패로 끝난다. Windows는 자식이 같은 콘솔에서 Ctrl+C를 직접 받는다.
- 회귀: 중단하면 결과 파일·stamp를 쓰지 않고 `finally`가 lock을 지운다. SIGTERM 종료코드는 143에서 KeyboardInterrupt 종료로 바뀐다. 이 코드에 의존하는 호출자를 찾지 못했다.
- import 부작용: `signal.signal`은 `main()` 안에만 있고 `main`을 부르는 다른 코드는 없다. Windows의 `ctypes.WinDLL`은 별도 인스턴스라 전역 설정을 바꾸지 않는다. `done_gate`를 거치는 hook의 import 비용이 약 13ms 늘어난다(`-X importtime` 1회). 차단하지 않는다.

### 5. 1차가 놓친 결함

위 표의 high 1건, medium 2건(`run-show`, meter 근거), low 6건(시작 경합, SIGHUP, 시험의 SIGINT, history, 최소 버전 문서, `flow_gate.py` 표기·중복)이다. 그 밖의 확인 결과는 다음과 같다.

- `flow_gate.py`: 부분 편집 해석과 `hunk_edits`는 맞다. `board.read`가 읽기 오류를 빈 문자열로 돌려 boundary를 건너뛰는 새 예외 경로를 찾지 못했다.
- `review.py`: 비교 지점이 모두 `hash_matches`로 바뀌었다. 약화 범위는 CRLF/LF뿐이다. `Path('').resolve()`가 현재 폴더가 되는 빈 경로는 세션 ID 비교와 `check`가 함께 막는다.
- `search_index.py`: 응답을 끝까지 읽어 어긋남이 없고 손상 blob을 격리한다. 제거한 필드의 소비자는 `jev_*`에 없다.
- `deps.py`: `skill_source`가 `s['source']`와 같고 npx 명령은 `command[4]`를 항상 가진다.
- `integration.py`: `worker_view`는 평면·중첩 형식을 모두 읽는다.
- `fullops-meter`: `taskOf`는 `flow_state.task_of`와 같은 규칙에 `baseKey`를 더했다. `readRecords`는 `fs.list`의 `size`·`mtimeMs`에 의존한다. 없으면 첫 읽기에서 예외가 난다. 실제 host로 확인하지 못했고 시험 대역에는 있다(meter 근거 finding에 포함).
- 시험: 삭제된 assert는 삭제 필드 대상이고 대체 assert가 있다. 하위 Run 오류 문구의 기대값 변경은 `full_run` 공통화 때문이다. 검증 무력화는 아니다. lint 프로세스 트리·gitlink, review 줄끝 위조, render 파이프라인, 설치기 launcher 시험은 실제 동작을 본다. 다만 `windows_paths`와 render는 환경에 따라 조용히 빠지며 이는 CI 공백 finding에 포함된다.

### 6. PLANS 후속 중 병합 전 항목

- CI 공백: 코드 수정은 병합 전에 필요하지 않다. 사용자 판단을 받아 기록하고 PLANS의 "1차가 판단" 문구를 고쳐야 한다.
- bare `git push`, meter 60초 캐시, `issue_mode.py` 분할, grok auto-wake: 병합 뒤에 해도 된다.
- PLANS에 없는 `run-current`·`run-show`의 `--full`은 병합 전에 고친다.

## 검증 및 남은 제약

- 재사용 증거: `lint.json`. attempt `dfd09a3e…`, head `8b32dde`, 원본은 prepare가 복사한 `fullops/dev` 체크아웃의 결과다. 환경 동일성은 자동 판정되지 않으며 같은 Windows PC의 체크아웃으로 판단한다.
- 구현자의 `npm test`는 7ef2723 기준이다. 8b32dde의 차이는 PLANS, 시험 보고서, `to_dev.md`뿐이라 재사용할 수 있다. 통과 여부는 기록으로만 확인했다.
- 지시에 따라 `lint.py`, 전체 시험, 임시 시험, `review.py check`를 실행하지 않았다. 상태를 바꾸는 Orca·GitHub 명령도 실행하지 않았다. `check --peek`은 읽음 처리를 하지 않는다.
- 미실행: 실제 GitHub, 이슈 자동 모드 전체 흐름, coordinator 터미널의 `run-current`, POSIX 실행, meter 시험. low 항목의 POSIX 건은 코드 읽기 근거다.
- snapshot은 clean이고 HEAD는 리뷰 SHA 그대로다.

## 대화 미참조 인계 점검

| 확인 항목 | 정본 경로/절 | 결과(확인/미확인/해당 없음) | 누락·오래된 정보·후속 |
|---|---|---|---|
| 현재 요구와 결정 이유 | `handovers/to_dev.md` 현재 상황, `PLANS.md` 31줄(D014~D016) | 확인 | 없음 |
| 구조와 구현/미완료 상태 | `handovers/to_dev.md` 해야 할 일·완료 보고 | 확인 | 묶음 F의 `setup.py`는 바뀌지 않았다. 폴더 삭제와 `deps.py`로 처리했고 시험이 있다 |
| 실행·검증 방법과 증거 | `CLEANUP-FOLLOWUPS-test/report.md`, `lint.json` | 확인 | meter 시험 실행 근거가 없다(medium) |
| 운영·복구(해당 시) | `docs/issue-auto-mode.md` 인계 뒤 fencing과 미시작 dispatch | 확인 | 절차 앞의 신원 확인이 현재 Orca에서 실패한다(high). 최소 Orca 버전 누락(low) |
| 다음 작업·담당·재개 조건 | `PLANS.md` 31·59줄, 이 보고서 결론 | 확인 | `--full` 잔여 2건은 아직 PLANS에 없다. 수정 뒤 새 SHA 재리뷰 |
| 로컬 링크·절 접근/지원 한계 | `to_dev.md` → 시험 보고서, `mods/fullops-meter/README.md` → `docs/flow-graph.md` | 확인 | 깨진 링크 없음 |
| snapshot 정리 후 정본 접근 | 이 리뷰 폴더(기록 체크아웃) | 확인 | 아직 미커밋이다. 병합 책임자가 보존한다 |

## 검토 결론

**수락하지 않는다.** 미해결 critical 0, high 1, medium 4, low 8이다.

수락 전에 필요한 일:

1. coordinator 터미널에서 `run-current --from <handle> --json`을 확인한다.
2. `issue_mode.py:258`·`:1108`에 `--full`을 더하고 대역을 실제 응답으로 바꾼다.
3. `reconcile` 본문, `flow_gate.task_listing`, `integration.record`의 `--full`을 시험으로 고정한다.
4. `claude plugin test mods/fullops-meter` 결과를 시험 보고서에 남긴다.
5. CI 공백의 후속 처리를 사용자에게 확인하고 PLANS를 고친다.
6. 새 SHA와 새 리뷰 키로 재리뷰한다. 수정 범위가 좁으므로 재리뷰도 이 변경분 중심으로 하면 된다.

low 8건은 PLANS 후속으로 넘겨도 된다.

그 밖의 변경(`review.py`, `search_index.py`, `deps.py`, `render.mjs`, `lint.py`의 gitlink·Job Object, `flow_gate.py`의 부분 편집, `worker_job` 판정)에서는 수락을 막는 결함을 찾지 못했다. 이 판단은 코드 검토이며 시험 통과의 증거를 대신하지 않는다. `review.py check` 통과도 이 판단을 자동 보증하지 않는다.
