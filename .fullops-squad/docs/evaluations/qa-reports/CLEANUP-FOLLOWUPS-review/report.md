---
title: CLEANUP-FOLLOWUPS 리뷰
status: review
updated: 2026-11-08
owner: reviewer
summary: 37a3ba002052 병합 전 독립 리뷰 보고서. 미해결 high 2건으로 수락하지 않는다
---

# CLEANUP-FOLLOWUPS 리뷰

- 검토자 / CLI / 모델: 독립 리뷰어 세션 `reviewer-20a9d4ce-2542-4e21-ba55-6530ab55e88d` / Claude Code / `claude-opus-5-5`. AI 판단이며 OCR 자동 판정이 아니다. `launch.effective`는 coordinator 기록을 따른다.
- base SHA / head SHA / merge-base: `0cea3b8b990c` / `37a3ba002052` / `0cea3b8b990c`
- OCR 버전 / 적용 규칙: open-code-review v1.13.6 / `fullops-common-0.3.6`(snapshot `.fullops-squad/rules/common/`), `.fullops-squad/review/rule.json`(`34c8f6e8…`)
- 요구사항·완료 기준 원천: PR #126 본문 `후속으로 남긴 것`, `.fullops-squad/handovers/to_dev.md`
- 전체 변경 / OCR 대상 / 제외 / reviewed / skipped / 범위 차이: 68 / 32 / 36 / 38 / 30(`dist/**`). 지시서 범위 밖 코드 변경은 없다.
- lint(`lint.json`) ERROR / WARNING / 실행 불가와 사유: 0 / 13 / 0. issue-mode·flow-gate·lint-gate·packaging 통과. jev-route는 경로 불일치로, full은 `test_level=lite`로 skipped.
- SIZE-002: 지시서에 예상 규모가 없다 / 실제 추가 1,430줄(상한 400) / 8개 묶음을 한 과제로 처리한 이유가 완료 보고에 없다. 수정 요청한다.
- DEP-001: `package.json`은 test 스크립트에 `tests/setup-scope.py`만 추가했다. 의존성 변경은 없다. 완료 보고의 기록은 없다.
- UI 디자인: 해당 없음. fullops-meter는 터미널 mod이며 지시서가 UI 작업이 아니라고 적었다. 디자인 lint와 테마 전환은 실행하지 않았다.

SIZE-001 경고 11건은 기존 큰 파일의 증가다. 이번 후속 범위에서는 차단하지 않는다. `issue_mode.py`(1401줄)는 분할을 후속으로 검토한다.

## 검토 범위

`dist/**` 외 38개 항목은 직접 읽었다. `issue_mode.py`는 파일 전체를 읽었다. `dist/**` 30개 항목은 원본과 바이트 비교로 같음을 확인하고 파일별 검토를 생략했다. 생략의 영향은 없다. 빌드 대응 관계는 CI의 `git diff --exit-code -- dist`가 PR에서 다시 확인한다.

## 발견 사항

| 심각도 | 파일·줄 | 재현 조건과 영향 | 상태 |
|---|---|---|---|
| high | `issue_mode.py:1043-1060` | Orca 1.4.251의 `task-list --run <id> --json`에는 `spec`이 없다. 실제 이슈 worker도 무관한 worker로 판정되고 기록된다. `boundary`가 push·비밀 파일·gh 병합·이전 epoch 검사를 건너뛴다. | 미해결 |
| high | `issue_mode.py:799-891` | 기본 응답에 `count`·`spec`이 없고 worker-list에 `page`가 없다. `reconcile --not-dispatched`(intent 경로)와 `sync`가 항상 실패한다. worker-start를 쓴 attempt는 끝나지 못하고 다른 이슈의 claim도 막힌다. | 미해결 |
| medium | `tests/issue-mode.py:177-205` | Orca 대역이 현재 CLI와 다른 응답을 돌려줘 위 2건을 찾지 못한다. | 미해결 |
| medium | `handovers/to_dev.md` | `npm test` 결과와 `CLEANUP-FOLLOWUPS-test/report.md`가 없고 완료 보고가 비었다. | 미해결 |
| medium | `lint.py:335,396` | POSIX 병렬 시험에서 Ctrl+C가 자식에게 닿지 않아 최대 1,500초 대기하고, 그룹 종료 시 고아 프로세스가 남는다. 코드 읽기 근거이며 실행 재현은 하지 않았다. | 미해결 |
| medium | `ci.yml:84-88` | Windows 전용 시험과 render 파이프라인, meter 시험이 CI에서 실행되지 않거나 조용히 빠진다. | 미해결 |
| low | `issue_mode.py:1148-1155` | 이전 coor의 bare `git push`, `gh issue comment 2`는 fencing을 통과한다. `complete`의 head SHA 확인으로 피해는 제한적이다. | 후속 가능 |
| low | `flow_gate.py:104-115,521` | 도구 입력 `content`가 list이면 예외로 이 호출의 boundary까지 건너뛴다. 실제 입력 발생 여부는 확인하지 못했다(추정). | 후속 가능 |
| low | `docs/search-index.md:28` | 제거된 `partial` 서술이 남았다. | 후속 가능 |
| low | `register.tsx:303-313` | 일시 읽기 실패로 얻은 경로를 60초 캐시한다. 표시 전용이다. | 후속 가능 |

### high 2건의 재현

이 세션의 실제 CLI에서 읽기 전용으로 확인했다. 임시 시험은 만들지 않았다.

- `orca --version`: 1.4.251
- `orca orchestration task-list --run run_88a80b39c65f --json`: 결과 키 `tasks, runId`, 행 키 `assignee, dispatchId, id, status, title`. `count`·`spec`이 없다.
- 같은 명령에 `--full`: 결과에 `count`, 행에 `spec`이 있다.
- `orca orchestration worker-list --run run_88a80b39c65f --json`: 결과 키 `scope, workers`. `page`가 없다. 도움말은 최대 100행과 `nextCursor`를 설명한다.
- `task-list --help`: "--full adds each spec and result". `mods/fullops-meter/hooks/register.tsx:223`도 1.4.246부터의 이 변화를 적었다.

한계: 호출자는 worker에 묶인 터미널이고 task 1건이다. coordinator에 묶인 호출에서 응답이 다른지는 확인하지 못했다. 도움말이 호출자 구분을 말하지 않아 같다고 판단했다.

`--full` 누락은 기준 커밋에도 있다. 다만 이번 변경은 그 전제 위에 복구 경로와 음성 기록을 새로 얹었고, 이번 과제의 완료 목표가 이 전제 때문에 달성되지 않는다. 그래서 high로 둔다.

## 집중 위험 답변

1. **`issue_mode.py`**
   - 인계 중 질문 게시: 게시 직전 소유자·상태·attempt 재확인이 있다. 재게시와 답변 유실 경로는 찾지 못했다. POST와 재확인 사이의 구간은 문서대로 막을 수 없다.
   - 재검증: `question`·`resolve_answers`·`complete`는 잠금 밖 조회 뒤 잠금 안에서 digest·attempt·허용 작성자를 다시 본다. 잠금 안의 GitHub 호출은 남아 있지 않다.
   - `--not-dispatched`: 코드 논리는 안전 쪽이지만 현재 Orca에서는 항상 실패한다(high). 다른 이슈가 계속 막힌다.
   - `worker_job` 생략: 수정 필요. `unrelated_workers`는 실제 이슈 worker의 범위 검사를 건너뛰게 만든다(high). `spec`을 고친 뒤에도 task를 찾지 못한 경우를 기록하면 안 된다.
   - 잘못된 소유자: bare 명령의 fencing 누락(low). 중복 배정 경로는 문서화된 shortcut(유예 뒤 승인된 worker-start)뿐이다. 이 worker는 이전 attempt 키라 무관한 worker로 판정된다.
2. **`flow_gate.py`**: Edit·MultiEdit·search_replace·apply_patch의 인박스 검사는 맞다. 편집 조각을 찾지 못하면 건너뛰므로 apply_patch의 공백 유연 일치나 CRLF `old_string`에서는 놓칠 수 있다. 이는 fail-open 원칙의 범위다. 오탐은 찾지 못했다. 예외는 `run_hook`이 받아 hook이 깨지지 않지만 list `content`에서 boundary까지 건너뛴다(low).
3. **`lint.py`**: 핸들 유출, 정상 종료 부작용(KILL_ON_JOB_CLOSE 없음), 출력 유실, 32비트 포인터 문제는 찾지 못했다. `ctypes.WinDLL` 별도 인스턴스라 전역 설정을 바꾸지 않는다. POSIX의 새 세션은 병렬 중단에 회귀가 있다(medium). gitlink는 모드로만 건너뛰고 파일로 되돌린 항목은 읽으므로 우회가 아니다.
4. **`review.py`**: 정규화가 약화하는 범위는 CRLF와 LF의 차이뿐이다. 내용 변경, 이진 파일(NUL 포함), 파일 추가는 거부한다. NUL 없는 이진 파일의 CRLF 차이는 탐지되지 않지만 실질 위험이 낮다. 기존 기록은 원본·LF·CRLF 3형식으로 호환된다. 줄끝이 섞인 기존 기록은 거부되어 안전 쪽이다. 비교 지점은 grep으로 전부 확인했다.
5. **`search_index.py`**: 요청 하나씩 응답 끝까지 읽어 교착이 없다. 없는 객체는 스트림을 유지하고 git 사망은 새 프로세스로 복구한다. 메모리는 64KB 단위다. 초대형 blob은 끝까지 읽는 시간이 든다(문서화된 shortcut). 제거 필드의 소비자는 없다. `jev_find.py`의 `partial`은 다른 결과 필드다. 문서 1줄만 남았다(low).
6. **`deps.py`·`fullops-meter`**: `--no-refresh`는 호스트 전용 스킬만 다시 갱신하며 맞다. agy 경로는 Context7 `/vercel-labs/skills`의 `~/.gemini/antigravity-cli/skills/`와 일치한다. `~/.gemini/config/skills`와 코드 주석의 antigravity 문서는 직접 확인하지 못했다. 이전 agy 설치는 `--check`가 미완료로 보고해 재설치로 복구된다. `grok_trust.py`는 `GROK_HOME`을 보지 않는다. 신뢰 파일 위치의 정본은 확인하지 못해 finding으로 두지 않았다. meter는 15초 주기로 목록을 읽으므로 기록 변경은 다음 주기에 보인다. 크기와 시각이 모두 같은 덮어쓰기만 남는다. checkout 위치는 최대 60초 오래될 수 있다.
7. **시험**: 실제 동작을 검증한다: lint 프로세스 트리·gitlink, search-index 손상 객체, review 줄바꿈 체크아웃, 설치기 launcher, 이슈 모드 SQLite·경계. 대역이 틀렸다: 이슈 모드 Orca 응답(medium). 조용히 빠진다: `windows_paths`, Windows의 `tests/lint.py`, render 파이프라인, meter 시험(medium). `setup-scope.py`의 `no_refresh_scope`는 mock으로 격리하지만 판정 대상인 명령 선택은 실제 코드다.

## 검증 및 남은 제약

- 재사용 증거: `lint.json`. 원본은 prepare가 복사한 lint 결과이고 attempt `a9977e6b…`, head `37a3ba0`, 기준 설정 해시가 기록과 같다. 환경 동일성은 자동 판정되지 않으며 Windows 구현 체크아웃으로 판단한다.
- 지시에 따라 `lint.py`, 전체 시험, 임시 시험을 실행하지 않았다. 표에 적은 `medium` 중 POSIX 건은 코드 읽기 근거다.
- 시험 삭제·완화: 제거된 assert는 삭제된 필드(`status`, `statuses`, `links`, `parser`, `partial`, `line_start`) 대상이고 대체 assert가 있다. 하위 Run 오류 문구의 기대값은 `full_run` 공통화로 `전체`로 바뀌었다. 검증 무력화는 아니다.
- `review.py check`는 실행하지 않았다. 병합 책임자 몫이며 미해결 high로 실패하는 것이 정상이다.

## 대화 미참조 인계 점검

| 확인 항목 | 정본 경로/절 | 결과(확인/미확인/해당 없음) | 누락·오래된 정보·후속 |
|---|---|---|---|
| 현재 요구와 결정 이유 | `handovers/to_dev.md` 현재 상황, `PLANS.md` 42줄(D014) | 확인 | 없음 |
| 구조와 구현/미완료 상태 | `handovers/to_dev.md` 해야 할 일·완료 보고 | 미확인 | 체크 항목과 완료 보고가 비었다 |
| 실행·검증 방법과 증거 | `lint.json`, `qa-reports/CLEANUP-FOLLOWUPS-test/report.md` | 미확인 | lint만 있다. 시험 보고서가 없다 |
| 운영·복구(해당 시) | `docs/issue-auto-mode.md` 인계 뒤 fencing과 미시작 dispatch | 확인 | 절차가 현재 Orca에서 동작하지 않는다(high) |
| 다음 작업·담당·재개 조건 | `PLANS.md` 42줄, 이 보고서 결론 | 확인 | 상태가 `진행 중`이다. high 수정 뒤 새 SHA 재리뷰 |
| 로컬 링크·절 접근/지원 한계 | `mods/fullops-meter/README.md` → `docs/flow-graph.md` | 확인 | 변경분의 그 밖의 로컬 링크는 추가되지 않았다 |
| snapshot 정리 후 정본 접근 | 이 리뷰 폴더(기록 체크아웃) | 확인 | 아직 미커밋이다. 병합 책임자가 보존한다 |

## 검토 결론

**수락하지 않는다.** 미해결 critical 0, high 2, medium 4, low 4다.

수락 전에 다음이 필요하다. high 2건을 고치고 대역을 현재 Orca 응답에 맞춘다. 완료 보고와 시험 근거를 채운다. 새 SHA와 새 리뷰 키로 재리뷰한다. POSIX 병렬 중단과 CI 공백도 이 차수에서 고치거나, 사용자 판단으로 PLANS.md 후속에 등재한다. low 4건은 PLANS.md 후속으로 넘겨도 된다.

그 밖의 변경(`review.py`, `search_index.py`, `deps.py`, `render.mjs`, `flow_gate.py`, Job Object, gitlink, fullops-meter)에서는 수락을 막는 결함을 찾지 못했다. 이 판단은 코드 검토이며 해당 시험의 통과 증거를 대신하지 않는다.
