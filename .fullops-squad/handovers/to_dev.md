---
title: "CLEANUP-FOLLOWUPS — PR #126 후속 8개 항목을 파일 소유권을 나눠 병렬로 처리"
status: draft
updated: 2026-11-07
owner: dev
tasks: [CLEANUP-FOLLOWUPS]
summary: "PR #126 후속 8개 항목을 파일 소유권을 나눠 병렬로 처리"
attempt: 9cc18decacfd44e09e22e22c9eb7c95b
base: 0cea3b8b990c2f40fc549a36772b1b6381a007f5
subagent_level: off
test_level: lite
---

# CLEANUP-FOLLOWUPS — PR #126 후속 8개 항목을 파일 소유권을 나눠 병렬로 처리

현재 과제는 이 역할 인박스에서 관리한다. 같은 과제의 후속은 본문에 반영하고 다른 과제는 PLANS.md에 대기시킨다. 완료하면 완료 보고 전문을 채우고 work.py finish로 지시서·결과를 로그에 보존한다.

- 작성일: 2026-11-07
- From / To: 대기 목록(PLANS.md) / dev 주 담당 세션
- 상태: running
- 테스트 레벨 / 하위 에이전트 레벨: fullops.json 선택값과 같은 값
- 승인된 범위 / 추가 승인이 필요한 행위: `fullops/dev`의 구현·테스트·커밋, 사용자가 켠 Workflow / push, PR, main 병합, 이슈 종료, 릴리스, `core.longpaths` 변경, 독립 리뷰 생략
- 상위 의도: 없음(묶음 작업이 아니다)
- 담당 repo id / 워크트리 절대경로 / 브랜치: 53ea77e9-1236-434b-bae0-d909cea13d73 / C:/Users/shin/orca/workspaces/Fullops-Squad-plugin/dev / fullops/dev
- 병합 책임자 / 기본 브랜치: 사용자 지시를 받은 dev 주 담당 / main
- 복귀 repo id / 워크트리 / 터미널 핸들 / run id / task id / dispatch id: 없음. dev 직접 작업이라 사용자에게 직접 보고한다

`상태`는 과제 상태다. front matter `status`는 문서 상태(draft/review/approved, lint DOC-003 어휘)라 서로 다른 값이 맞다.

## 현재 상황과 확인 근거

- PR #126 "후속으로 남긴 것" 8개 묶음을 사용자 결정 D014(이슈 모드까지 전부)로 진행한다.
- 사용자가 2026-11-07 울트라코드 병렬 작업을 켰다. `rules/delegation.md`의 사용자가 켠 Workflow 예외를 따른다.
- 기준은 main 0cea3b8이다.

## 적용 기준과 예외

공통 기준은 `.fullops-squad/rules/common/README.md` 및 연결된 코딩·테스트·보안 규칙이다.
기준 커밋은 0f918bb다. 예외 없음. 사용자 방향(#132): npm 의존을 새로 더하지 않는다.

## 먼저 읽을 문서

- PR #126 본문의 `후속으로 남긴 것`
- `.fullops-squad/rules/delegation.md`

## 해야 할 일과 파일 소유권

- [x] A lint 서브모듈 gitlink, Windows 자식 프로세스 timeout (`lint.py`, `tests/lint.py`)
- [x] B 리뷰 해시 autocrlf, Windows 리뷰 경로 시험 (`review.py`, `tests/review-check.py`)
- [x] C Jev 콜드 메타데이터, 캐시 필드 (`search_index.py`, `tests/search-index.py`)
- [x] D 이슈 모드 fencing·잠금·intent·조회 비용 (`issue_mode.py`, `issue_github.py`, `tests/issue-mode.py`)
- [x] E flow-gate patch·Write 내용 해석 (`flow_gate.py`, `tests/flow-gate.py`)
- [x] F setup 범위·스킬 경로·빈 폴더 (`setup.py`, setup 자산과 시험)
- [x] G fullops-meter 정리 (`mods/fullops-meter/`)
- [x] H 큰 시험 2건: `render.mjs` 파이프라인, 설치기 Codex 분기 (`tests/motion*.py`, `tests/npm-installer.cjs`)
- [x] 부모가 결과를 확인하고 dist를 다시 만들고 커밋한다.


## 완료 기준과 검증

- 각 항목은 고쳐졌거나, 고치지 않은 이유와 필요한 결정을 기록한다.
- 하위 작업은 커밋과 브랜치 변경을 하지 않는다. 부모가 변경 파일과 시험 결과를 확인한다.
- `review.py need`가 `ask`이면 사용자에게 묻는다.
- 증명 방법: 항목별 시험, `npm test` 통과, `lint.py --from 0cea3b8` ERROR 0.

UI 작업이 아니라 디자인 기준은 해당 없음이다.

## 갱신할 산출물

없음.

## 기대 산출물

항목별 수정과 시험, 재생성한 dist, `docs/evaluations/qa-reports/CLEANUP-FOLLOWUPS-test/report.md`.

## 제약·협업·후속

하위 지시에 `Purpose: implementation`, 과제 키, 파일 소유권, 완료 조건을 적는다. 커밋·push·PR·병합·이슈 종료·릴리스·`core.longpaths` 변경은 하위 작업에 맡기지 않는다. 의존성을 새로 더하지 않는다.

## 완료 보고

- 브랜치 / 구현 SHA: `fullops/dev` / 7ef2723
- 변경 이유: PR #126에서 후속으로 남긴 8개 묶음을 처리한다(결정 D014).
- 판단: Workflow로 파일 소유권을 나눠 병렬 구현했다. 부모가 `deps.py` 패치, 시험 등록, 문서, dist를 맡고 결과를 대조했다. 캐시 status·statuses는 결정 D016으로 제거했다.
- 검토 필요: `review.py need`는 ask다(결정 D015로 독립 리뷰). 1차는 수락 불가였고 7ef2723에서 고쳤다.
- 검증한 것: `npm test` 통과, 실제 Orca 1.4.251 조회 확인, Linux 시험. 상세는 [report.md](../docs/evaluations/qa-reports/CLEANUP-FOLLOWUPS-test/report.md)에 있다.
- 못 한 것: 실제 GitHub·이슈 자동 모드 전체 흐름, macOS, 실제 agy 세션.
- DEP-001: `package.json`은 test 스크립트만 바뀌었다. 의존성 변경은 없다.
- SIZE-002: 8개 묶음을 한 과제에서 처리해 상한을 넘었다. 그룹별 커밋으로 나눴다.
- 남은 일: 재리뷰, main 병합 승인. 리뷰 후속은 PLANS.md에 있다.
