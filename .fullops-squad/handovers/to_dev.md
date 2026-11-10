---
title: SWEEP-DECISIONS — REPO-SWEEP 감사의 사용자 결정 8건 반영
status: draft
updated: 2026-11-10
owner: dev
tasks: [SWEEP-DECISIONS]
summary: REPO-SWEEP 감사의 사용자 결정 8건 반영
attempt: b849c78461e849d583c756dde66ee495
base: c2ec335523f5081d593b6024483945ae6d0e59c3
subagent_level: lite
test_level: lite
---

# SWEEP-DECISIONS — REPO-SWEEP 감사의 사용자 결정 8건 반영

현재 과제는 이 역할 인박스에서 관리한다. 같은 과제의 후속은 본문에 반영하고 다른 과제는 PLANS.md에 대기시킨다. 완료하면 완료 보고 전문을 채우고 work.py finish로 지시서·결과를 로그에 보존한다.

- 작성일: 2026-11-10
- From / To: 사용자 결정(REPO-SWEEP 감사의 결정 항목) / dev 주 담당 세션
- 상태: running
- 테스트 레벨 / 하위 에이전트 레벨: fullops.json 선택값과 같은 값
- 승인된 범위 / 추가 승인이 필요한 행위: 아래 8건의 구현·시험·커밋·PR·병합 / 릴리스, 유지·보류로 정한 7건
- 상위 의도: 없음(묶음 작업이 아니다)
- 담당 repo id / 워크트리 절대경로 / 브랜치: 53ea77e9-1236-434b-bae0-d909cea13d73 / C:/Users/shin/orca/workspaces/Fullops-Squad-plugin/dev / fullops/dev
- 병합 책임자 / 기본 브랜치: 사용자 지시를 받은 dev 주 담당 / main
- 복귀 repo id / 워크트리 / 터미널 핸들 / run id / task id / dispatch id: 없음. dev 직접 작업이라 사용자에게 직접 보고한다

`상태`는 과제 상태다. front matter `status`는 문서 상태(draft/review/approved, lint DOC-003 어휘)라 서로 다른 값이 맞다.

## 현재 상황과 확인 근거

- REPO-SWEEP 감사가 사용자 결정으로 넘긴 16건(중복 1건을 빼면 15건)을 2026-11-10에 사용자가 항목별로 정했다. 진행 8건, 유지·보류 7건이다.
- 근거 전문은 `.fullops-squad/local/REPO-SWEEP-audit.json`(gitignore)의 `needs_user`다. 기준은 main c2ec335다.

## 적용 기준과 예외

공통 기준은 `.fullops-squad/rules/common/README.md` 및 연결된 코딩·테스트·보안 규칙이다. 예외 없음. 하위 에이전트는 주간 사용량 한도 때문에 쓰지 않고 직접 구현한다.

## 먼저 읽을 문서

- PLANS.md `REPO-SWEEP 후속`

## 해야 할 일과 파일 소유권

- [x] `issue_mode.py`의 argv `--token` 삭제(`--token-file`만), `docs/issue-auto-mode.md`
- [x] `jev_find.py`·`jev_context.py`의 `--handover`와 `work.instruction`의 인자 삭제, README·`fullops-work` 스킬, 시험 2개
- [x] `tests/handover-audit.py` 삭제
- [x] 이 레포 `lint.json`: issue-mode 경로에 `integration.py`·`orca_wait.py` 추가, packaging 경로를 `tests/standard.cjs`가 읽는 범위로 좁힘
- [x] `claude-code-review.yml` 경로에 `dependencies.json`·`package.json` 추가
- [x] `deps.py --prune-runtime`(`hook_runtime.prune`): 현재 사본만 남기는 명시적 정리, `docs/development.md`, 시험
- [x] `autonomy_policy.delay_minutes`·`approval_hours` 기본값과 검증 삭제, `docs/events.md`

## 완료 기준과 검증

- 8건이 구현되고 해당 시험이 통과한다.
- 증명 방법: `project.md`의 `작업 검증`. `lint.py --repo . --from c2ec335` 종료코드 0, `ERROR 0`, `실행 불가 0`.
- verifier: lite 과제라 지정하지 않는다.

### UI 작업의 디자인 기준과 검증

해당 없음. UI 변경이 없다.

## 갱신할 산출물

없음.

## 기대 산출물

코드·시험·문서 변경, `docs/evaluations/qa-reports/SWEEP-DECISIONS-test/report.md`, PLANS.md 갱신.

## 제약·협업·후속

- 유지: `checkpoint --receipt`, `env_link.py --worktree`, `frontend.py --dry-run`, find의 `rerank`·`hierarchical`, observe의 claims 경로.
- 보류: coor 세션의 이슈 상태 재기록, meter의 구버전 Orca `--full` 재시도.
- 런타임 사본은 자동으로 지우지 않는다. 오래된 세션이 자기 사본의 `lint.py` 경로를 기억하기 때문이다.
- packaging 경로를 좁혀도 `adapters/`·`scripts/build.py` 변경의 dist 일치 검사는 CI에만 있다. 로컬 검사 추가는 범위 밖이다.

## 완료 보고

