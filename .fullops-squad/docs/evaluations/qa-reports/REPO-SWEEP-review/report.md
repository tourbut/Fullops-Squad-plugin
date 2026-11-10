---
title: REPO-SWEEP 리뷰
status: review
updated: 2026-11-10
owner: reviewer
summary: 95f0edbe1e47 병합 전 독립 리뷰 보고서
---

# REPO-SWEEP 리뷰

- 검토자 / CLI / 모델: 별도 reviewer 세션 `reviewer-79d4a997-af21-4114-9666-ee2cc6519d2d` / `claude` / `claude-opus-5-5` effort `high`. 선택 tuple은 `docs/evaluations/jev/REPO-SWEEP-model-reviewer.json`(source user)과 같다. 구현자 세션은 `f0726204-9981-4e4d-9372-476f2ff7eca3`이다.
- base SHA / head SHA / merge-base: `10c0695df4f66d6a76e94c1b9c9579eae3d84a4e` / `95f0edbe1e47d07a36570bb7b720d0ac4b98f6ea` / `10c0695df4f66d6a76e94c1b9c9579eae3d84a4e`. 읽기 전용 detached snapshot `C:\Users\shin\orca\workspaces\Fullops-Squad-plugin\.fullops-review-957d5b65c0ba4873a14d5601bced8d83`(HEAD 95f0edb, clean)에서 읽었다.
- OCR 버전 / 적용 규칙: open-code-review v1.13.6 (891df1b). rule_sha256 `34c8f6e8…8657`. OCR의 LLM 판정은 쓰지 않았다. 아래 판단은 AI 검토자의 판단이다.
- 요구사항·완료 기준 원천과 기준별 충족/미달: 원천은 `.fullops-squad/handovers/to_dev.md`의 `완료 기준과 검증`과 `docs/evaluations/qa-reports/REPO-SWEEP-test/report.md`다. dev 직접 작업이라 탐색 패킷은 없다.
  - 확정 47건과 개발 6건: 충족. `.fullops-squad/local/REPO-SWEEP-audit.json`의 confirmed 47건을 파일별로 diff와 대조했다. 46건은 지정 파일이 바뀌었다. `work-task-excerpt-limit-duplicated-literal`은 제안대로 호출자(`jev_context.py`·`jev_find.py`·`jev_packet.py`)의 3500 리터럴을 `task_excerpt(text) != text`로 바꿔 처리했다. 개발 6건(리뷰어 배정 게이트, `task_listing` 삭제, 리뷰 보고서 40줄 안내 제외, `trim.jsonl` command, `direct_check` 기록 커밋 인정, 템플릿 모델 id)은 모두 반영됐다. 사용자 결정 16건은 구현하지 않고 PLANS.md에 남겼다. 건너뛴 3건에 사유가 있다.
  - `npm test` 종료코드 0, meter 시험 통과: 검증 보고의 기록으로 확인했다(eaed03d 트리). eaed03d 뒤 커밋 2개는 기록 파일과 이 레포 `orca-agents.md`만 바꿨다(`git diff --stat eaed03d 95f0edb`). 재실행하지 않았다.
  - 증명 방법(lint ERROR 0, 실행 불가 0): 충족. `lint.json` HEAD 95f0edb.
  - JevPlay Unity 미실행: 못 한 검증으로 기록됐다.
- 전체 변경 / OCR 대상 / 제외 / reviewed / skipped: 112 / 59 / 53 / 59 / 53. 제외 53개는 모두 `dist/`(`scripts/build.py` 생성물)다. 원본과 바이트 비교해 동일함을 확인했다. `dist/directory/fullops-squad/hooks/hooks.json`만 기존 빌드 변환(`run.sh` 경로)으로 다르고 `spawn_subagent` matcher는 반영됐다. 지시서 파일 소유권 A~E 밖의 변경은 이 레포 `orca-agents.md`(사용자 결정, PLANS.md 54행)뿐이다.
- lint(`lint.json`) ERROR / WARNING / 실행 불가: 0 / 8 / 0. 등록 검사 issue-mode·jev-route·flow-gate·lint-gate·packaging 통과(종료코드 0). `full`은 test_level lite라 skipped(고정 사유). WARNING: LINT-001(이 레포 lint.json 변경, 병합 뒤 적용, 내용은 아래 확인), SIZE-001 4건(이미 300줄을 넘는 파일에 2~25줄 추가, 분할은 이번 범위 밖), SIZE-002, DEP-001 2건.
- SIZE-002: 지시서 예상은 30~40개 파일, 순감 약 150줄이다. 실제 lint 대상 56개 파일, 추가 410줄이다. 전체 diff는 dist 포함 818+/676-이고 dist를 빼면 순감이다. 감사 묶음 하나라 나누지 않았다는 보고서 사유를 수락한다. 보고서의 406줄은 d8fd2ae 기준이고 그 뒤 기록 커밋으로 410줄이 됐다.
- DEP-001: `package.json`은 npm script 3개 삭제, JevPlay `package.json`은 버전만 0.1.4로 올렸다. 의존성 선언 변경은 없다. 보고서의 기록과 맞다.
- UI 디자인: 해당 없음. meter 변경은 표시 내용을 바꾸지 않는 내부 정리다(지시서 `UI 작업의 디자인 기준과 검증`).

## 검토 범위

result.json의 112개 `(path, status)`에 검토 상태와 사유를 기록했다. 세 관점(버그·보안·준수)으로 읽었다.

- 스크립트 25개: diff와 함께 정의·호출자를 직접 읽었다. 확인한 점:
  - `flow_gate.py`: 새 이름 `task_list`·`issue_state_exists`·`settled_in_runtime`·`policy.identity`가 있다. `marked_role(root, '설계')`는 기존 `guide()[1]`과 같은 정규식이다. `lru_cache`는 hook이 이벤트마다 새 프로세스라 실패 None 캐시가 다음 이벤트로 넘어가지 않는다. 리뷰어 기록 우회는 route가 없는 키에만, `Purpose: review`와 `task_key`·`role`이 맞는 기록에만 적용된다(`tests/session-regressions.py` 새 시험).
  - `setup.py`: `settled_in_runtime`는 Orca 조회 실패나 `task` 없는 예전 기록에서 False라 전환을 그대로 막는다. 삭제한 `config["roles"] = assigned`는 235행에 이미 있다.
  - `review.py`: `direct_check`는 `records_only`(RECORDS 경로만, 문서 형식 검사 포함)일 때만 리뷰 SHA를 인정하고 그 SHA로 `check`한다. 코드 커밋이 끼면 막는다(새 시험). `main`의 범위 검사 통합은 이전 분기와 동등하다.
  - `issue_mode.py`: `reconcile`은 `full_run`으로 바뀌었다. `full_run`이 count·page·worker-task 일치 검사를 모두 하므로 삭제된 검사는 옮겨졌다. `question`의 `recovery`는 같은 `store.edit()` 블록에서 읽은 값이다. `wait`은 기록 실패 시 소비한 묶음을 `record_error`와 함께 돌려준다.
  - `lint.py`: `stamp`의 `fullops-gate` 폴더는 바로 앞의 `lint-result.json` 쓰기(`atomic_write`가 mkdir)가 만든다.
  - `deps.py`: 설치 상태 검사를 지연 평가로 바꿨고, 판정은 이전 `valid`와 같다.
  - `done_gate.py`: `diff-tree --stdin`은 줄바꿈으로 끝난 SHA를 받고 빈 목록이면 실행하지 않는다.
  - `jev_*`: `jev_find`의 항목은 이전 `code_map`+`details` 결과와 같다. `jev_observe`의 삭제 대입은 572·573행에서 다시 설정된다. `jev_test_web`의 삭제한 replay 검증은 `run()`이 `test_record.begin` 전에 한다. 그 사이 브라우저 생성자는 프로세스를 띄우지 않는다.
- 시험 19개: 기대값 완화나 검증 삭제는 없다. `tests/deps.py`에서 삭제한 assert는 23행에 같은 검사가 남아 있다. 새 시험은 orca-wait·issue-mode·done-gate·operating-policy·session-regressions·output-trim·search-index·meter 등에 있다.
- 기록·설정·패키징 15개: 위 표와 result.json 사유에 적었다. `.fullops-squad/lint/lint.json`의 flow-gate paths 변경은 `tests/flow-gate.py:316-376`이 `harness_gate`를 실행하고 `hook_runtime`은 실행하지 않는다는 감사 근거와 맞다. 삭제한 npm script 3개는 문서·CI·스크립트에서 참조하지 않는다(grep).
- `--host both` 삭제: `docs/releases/1.8.7.md`가 이 값을 언급하지만 유지 약속은 아니다. 감사가 확정했고 검증 보고의 `동작이 바뀌는 점`에 릴리스 노트 원천으로 적혀 있다.

## 발견 사항

| 태그 | 심각도 | 파일·줄 | 재현 조건 | 영향 | 수정 상태 | 검증 근거 |
|---|---|---|---|---|---|---|
| [준수] | low | `.fullops-squad/PLANS.md:135` | REPO-SWEEP 후속에 "이 레포 모델 후보를 `claude-fable-5-2`로 바꿀지. 재개 조건: 사용자 결정."이 남아 있다 | 같은 커밋이 54행에 2026-11-10 결정을 적고 `orca-agents.md`를 이미 바꿨다. 다음 세션이 끝난 결정을 대기로 읽는다 | 미해결. 병합 전 기록 커밋이나 PLANS.md 후속에서 그 줄을 지운다 | `grep -n fable .fullops-squad/PLANS.md` → 54·135행 |

critical·high·medium은 없다. nit은 0건이다.

## 검증 및 남은 제약

- 지시에 따라 lint.py와 전체 시험을 다시 실행하지 않았다. 고정 SHA snapshot, `lint.json`, 검증 보고, 감사 JSON만 읽었다.
- `lint.json`: prepare가 기록 체크아웃의 `<git dir>/fullops-gate/lint-result.json`에서 복사했다. base 10c0695, head 95f0edb, merge_base 10c0695, test_level lite다. 등록 검사 5개는 이 HEAD에서 종료코드 0이다.
- `npm test`(42묶음, 종료코드 0)와 meter 82 pass는 검증 보고의 기록이다. 원시 로그는 커밋하지 않았다. eaed03d 뒤에는 코드 변경이 없다.
- 미실행 범위(보고서 기재): JevPlay Unity 컴파일·실행, grok 실제 세션의 `spawn_subagent` matcher, 실제 Orca 응답, Playwright 브라우저 경로, meter의 실제 Claude Code 로드. 각각 PLANS.md 후속에 재개 조건이 있다.
- 구현 Workflow의 반박 리뷰 5개가 사용량 한도로 실패했다. 이 독립 리뷰가 그 공백을 대신한다.
- 테스트 삭제·기대값 완화: 없음. 시험 정리는 import 방식·헬퍼 중복 제거이며 검사 대상은 같다.

## 대화 미참조 인계 점검

| 확인 항목 | 정본 경로/절 | 결과(확인/미확인/해당 없음) | 누락·오래된 정보·후속 |
|---|---|---|---|
| 현재 요구와 결정 이유 | `handovers/to_dev.md` `현재 상황과 확인 근거`·`제약·협업·후속`, `PLANS.md` REPO-SWEEP 행 | 확인 | 모델 후보 결정은 PLANS.md 54행에 있으나 135행이 오래됐다(finding) |
| 구조와 구현/미완료 상태 | `qa-reports/REPO-SWEEP-test/report.md` `결과`·`동작이 바뀌는 점`, `PLANS.md` `REPO-SWEEP 후속` | 확인 | 사용자 결정 16건이 항목별로 나열됨 |
| 실행·검증 방법과 증거 | 같은 보고서 결과 표, `REPO-SWEEP-review/lint.json` | 확인 | npm test 원시 로그는 없다(lite 보고 형식) |
| 운영·복구(해당 시) | 보고서 `동작이 바뀌는 점`(JevPlay `unity_bridge.py install` 뒤 재빌드) | 확인 | 해당 범위만 |
| 다음 작업·담당·재개 조건 | `PLANS.md` `REPO-SWEEP 후속` | 확인 | 담당 dev, 항목별 재개 조건 있음 |
| 로컬 링크·절 접근/지원 한계 | `PLANS.md`의 `[보고서](docs/evaluations/qa-reports/REPO-SWEEP-test/report.md)` | 확인 | 감사 전문 `.fullops-squad/local/REPO-SWEEP-audit.json`은 gitignore라 다른 체크아웃에서는 읽을 수 없다. 요약은 보고서에 있다 |
| snapshot 정리 후 정본 접근 | 기록 체크아웃 `qa-reports/REPO-SWEEP-review/` | 확인 | result.json·report.md·lint.json은 snapshot 밖에 있다 |

## 검토 결론

수락한다. critical 0, high 0, medium 0, low 1이다.

- 감사 확정 47건과 개발 6건이 diff에 반영됐다. 바꾼 함수의 호출자와 시험을 대조했고 회귀를 찾지 못했다.
- lint ERROR 0, 실행 불가 0이다. WARNING 8건은 위 판단대로 수락한다.
- 미해결 low 1건(PLANS.md 135행)은 병합 전 기록 커밋이나 PLANS.md 후속으로 정리한다. 병합을 막지 않는다.
- `review.py check` 통과는 기록 검사다. 시험 성공과 내용의 정확성을 자동으로 보증하지 않는다.
