---
title: "LINT-BATCH-READ — lint.py가 파일 내용을 git cat-file --batch 한 번으로 읽게 변경(#132 선행 개선)"
status: draft
updated: 2026-11-07
owner: dev
tasks: [LINT-BATCH-READ]
summary: "lint.py가 파일 내용을 git cat-file --batch 한 번으로 읽게 변경(#132 선행 개선)"
attempt: a39eddbcb507433aa3e1a2ee9c57dbd1
base: 0f918bbea336772e1ca0a680bec14dc3897664a8
subagent_level: off
test_level: lite
---

# LINT-BATCH-READ — lint.py가 파일 내용을 git cat-file --batch 한 번으로 읽게 변경(#132 선행 개선)

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

- #132 측정: `99e7b50..446856f`(경로 1,551개)에서 파일별 `git cat-file`은 git 호출 944회에 49.2초, `--batch` 1회는 0.9초다.
- 2026-11-07 fullops/dev dd27b7b에서 `lint.py`의 `blob()` 호출 4곳을 확인했다. `blob()`은 `lint()` 안에서만 쓴다.

## 적용 기준과 예외

공통 기준은 `.fullops-squad/rules/common/README.md` 및 연결된 코딩·테스트·보안 규칙이다.
기준 커밋은 0f918bb다. 예외 없음. 사용자 방향(#132): npm 의존을 새로 더하지 않는다.

## 먼저 읽을 문서

- `plugins/fullops-squad/scripts/lint.py`
- `tests/lint.py`

## 해야 할 일과 파일 소유권

- [ ] `lint.py`의 `blob()`을 `read_blobs()` 일괄 읽기로 바꾼다.
- [ ] `tests/lint.py`에 내용·바이너리·없는 경로 시험을 더한다.
- [ ] 측정 범위에서 이전 방식과 내용이 같은지, 시간이 줄었는지 확인한다.
- [ ] `python3 scripts/build.py`로 dist를 다시 만든다.


## 완료 기준과 검증

- `lint()`의 파일 읽기 프로세스가 `cat-file --batch` 1회로 줄고 검사 결과는 같다.
- 없는 경로는 lint 실패로 끝난다. 빈 내용으로 읽지 않는다.
- 증명 방법: `python3 tests/lint.py` 통과, 측정 범위 내용 비교, `lint.py --from 0f918bbea336772e1ca0a680bec14dc3897664a8` ERROR 0.

UI 작업이 아니라 디자인 기준은 해당 없음이다.

## 갱신할 산출물

없음.

## 기대 산출물

`lint.py` 수정과 시험, 재생성한 dist, `docs/evaluations/qa-reports/LINT-BATCH-READ-test/report.md`.

## 제약·협업·후속

단일 파일 수정이라 위임 규칙 1에 따라 직접 처리한다. 이 과제는 main 병합과 릴리스를 하지 않는다.

## 완료 보고

브랜치 / SHA / 변경 이유 / 검토 필요 / 검증한 것과 못 한 것 / 산출물·로그 링크 / 남은 일.
항목당 1~2줄로 쓰고 상세는 `qa-reports/<과제 키>-test/report.md`(역할별로 나눈 키는 `<키>-DEV` 그대로) 링크로 대신한다. 브랜치와 완료 SHA는 여기에 적는다. worker_done 메시지에만 적지 않는다. worker_done 본문 첫 줄은 `[완료] <과제 키> | 브랜치 <이름> | SHA <브랜치 HEAD>` 한 줄로 쓰고 SHA는 하나만 적는다. `남은 일`에 다른 역할의 후속(예: tester 독립 QA)을 쓰면 `work.py finish`가 PLANS.md `## 완료 보고 후속 요청`에 등재한다.
lint DEP-001이 있으면 파일별 의존성 변경 여부·필요성·표준 라이브러리 대안을 적는다. 의존성 변경이 없으면 그 근거를 적는다.
처리는 `fullops-work`, 회신은 `fullops-orca` 스킬을 따른다.
