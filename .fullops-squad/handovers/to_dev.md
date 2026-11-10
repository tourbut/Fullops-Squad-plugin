---
title: REPO-SWEEP — 감사로 확정한 정리 47건과 하네스 후속 개선 6건을 파일 소유권을 나눠 구현
status: draft
updated: 2026-11-10
owner: dev
tasks: [REPO-SWEEP]
summary: 감사로 확정한 정리 47건과 하네스 후속 개선 6건을 파일 소유권을 나눠 구현
attempt: d4c7a9c2a38d4d5685e9c431c5e2ee7f
base: 10c0695df4f66d6a76e94c1b9c9579eae3d84a4e
subagent_level: lite
test_level: lite
---

# REPO-SWEEP — 감사로 확정한 정리 47건과 하네스 후속 개선 6건을 파일 소유권을 나눠 구현

현재 과제는 이 역할 인박스에서 관리한다. 같은 과제의 후속은 본문에 반영하고 다른 과제는 PLANS.md에 대기시킨다. 완료하면 완료 보고 전문을 채우고 work.py finish로 지시서·결과를 로그에 보존한다.

- 작성일: 2026-11-10
- From / To: 사용자 지시(전반 리팩토링·불필요 로직 정비·신규 개발) / dev 주 담당 세션
- 상태: running
- 테스트 레벨 / 하위 에이전트 레벨: fullops.json 선택값과 같은 값
- 승인된 범위 / 추가 승인이 필요한 행위: `fullops/dev`의 구현·테스트·커밋, 사용자가 켠 Workflow(울트라코드) / main 병합, 릴리스, 독립 리뷰 생략, `사용자 결정이 필요한 것` 16건
- 상위 의도: 없음(묶음 작업이 아니다)
- 담당 repo id / 워크트리 절대경로 / 브랜치: 53ea77e9-1236-434b-bae0-d909cea13d73 / C:/Users/shin/orca/workspaces/Fullops-Squad-plugin/dev / fullops/dev
- 병합 책임자 / 기본 브랜치: 사용자 지시를 받은 dev 주 담당 / main
- 복귀 repo id / 워크트리 / 터미널 핸들 / run id / task id / dispatch id: 없음. dev 직접 작업이라 사용자에게 직접 보고한다

`상태`는 과제 상태다. front matter `status`는 문서 상태(draft/review/approved, lint DOC-003 어휘)라 서로 다른 값이 맞다.

## 현재 상황과 확인 근거

- 전체 정리는 PR #126(213건 중 187건)과 PR #135(후속 8묶음)로 두 번 끝났다. 세 번째는 증거가 있는 것만 고친다.
- 읽기 전용 감사 Workflow(`wf_35efaaec-5a7`, 에이전트 11개, effort medium)가 5개 영역을 탐색하고 영역별 반박 검증을 했다. 결과는 77건 중 확정 47, 반박 14, 사용자 결정 필요 16이다. 전문은 `.fullops-squad/local/REPO-SWEEP-audit.json`(gitignore)이다.
- 신규 개발 후보는 PLANS.md 후속 절에서 재개 조건이 "다음 하네스 수정"인 것만 골랐다. 사용자 결정이 조건인 것은 넣지 않는다.
- 사용자 지시(2026-11-10): 로직 점검은 effort medium, 구현은 high.

## 적용 기준과 예외

공통 기준은 `.fullops-squad/rules/common/README.md` 및 연결된 코딩·테스트·보안 규칙이다.
기준 커밋은 10c0695다. 예외 없음. `rules/delegation.md`의 사용자가 켠 Workflow 예외로 병렬 구현한다. Git 커밋은 부모만 한다.

## 먼저 읽을 문서

- `.fullops-squad/local/REPO-SWEEP-audit.json`
- `.fullops-squad/rules/delegation.md`, `docs/development.md`

## 해야 할 일과 파일 소유권

- [ ] A 이슈·자율: `issue_mode.py`, `autonomy.py`, `decision.py`, `orca_wait.py`, 그 시험, `fullops-orca` 스킬의 `decision.py add` 예시
- [ ] B 게이트·hook: `flow_gate.py`, `harness_gate.py`, `integration.py`, `output_trim.py`, `hooks.json`, 이 레포 `lint.json`, 그 시험. 개발: 리뷰어 배정 게이트(`<키>-model-reviewer.json` 인정), `task_listing` 중복 삭제, 리뷰 보고서의 40줄 안내 제외, `trim.jsonl`에 명령 첫 단어
- [ ] C lint·리뷰·setup: `lint.py`, `review.py`, `setup.py`, `done_gate.py`, `deliverables.py`, 그 시험. 개발: 리뷰 뒤 기록 커밋만 있으면 `direct_check`가 리뷰를 인정
- [ ] D Jev·웹: `jev_*.py`, `test_record.py`, `work.py`, `JevPlay.cs`(0.1.4), 그 시험
- [ ] E meter·패키징: `mods/fullops-meter/`, `deps.py`, `scripts/install.py`, `bin/`, `package.json`, `ci.yml`, 템플릿 `orca-agents.md`의 없는 모델 id, 그 시험
- [ ] 부모: `scripts/build.py`로 dist 재생성, 반박 리뷰(effort medium)와 수정, 시험, lint, 기록

예상 변경 규모는 30~40개 파일, 순감 약 150줄이다.

## 완료 기준과 검증

- 확정 47건과 개발 6건이 구현됐거나, 뺀 항목에 사유가 있다.
- `npm test` 종료코드 0, meter 시험 통과.
- 증명 방법: `project.md`의 `작업 검증`. `python3 plugins/fullops-squad/scripts/lint.py --repo . --from 10c0695` 종료코드 0, `ERROR 0`, `실행 불가 0`.
- verifier: lite 과제라 지정하지 않는다. 대신 구현 뒤 반박 리뷰 Workflow를 돌린다.
- `review.py need`가 ask·required면 사용자에게 독립 리뷰 여부를 묻는다.
- JevPlay C# 변경은 Unity에서 실행하지 못한다. 못 한 검증으로 적는다.

### UI 작업의 디자인 기준과 검증

해당 없음. meter 변경은 표시 내용을 바꾸지 않는 정리다.

## 갱신할 산출물

없음. 동작이 바뀌는 점은 `report.md`와 PR 본문에 적어 다음 릴리스 노트의 원천으로 삼는다.

## 기대 산출물

코드·시험 변경, `docs/evaluations/qa-reports/REPO-SWEEP-test/report.md`, PLANS.md 갱신.

## 제약·협업·후속

- 사용자 결정이 필요한 16건(릴리스 노트가 유지를 약속한 CLI 옵션, 문서화된 설정 키, 런타임 스냅샷 정리, 이 레포 `lint.json` 경로 정책 등)은 구현하지 않고 보고한다.
- 이 레포의 모델 후보(`orca-agents.md`)를 `claude-fable-5-2`로 바꿀지는 사용자 결정이다.
- 릴리스는 하지 않는다.

## 완료 보고

