---
title: "HOOK-SLIM — 관계없는 호출을 일찍 끝내고 무거운 import·git 호출을 줄여 hook 시간을 단축(#132 선행 개선)"
status: draft
updated: 2026-11-07
owner: dev
tasks: [HOOK-SLIM]
summary: "관계없는 호출을 일찍 끝내고 무거운 import·git 호출을 줄여 hook 시간을 단축(#132 선행 개선)"
attempt: 2c6078f0255944a6b7632bed5958de66
base: 0f918bbea336772e1ca0a680bec14dc3897664a8
subagent_level: off
test_level: lite
---

# HOOK-SLIM — 관계없는 호출을 일찍 끝내고 무거운 import·git 호출을 줄여 hook 시간을 단축(#132 선행 개선)

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

- 2026-11-07 12d7f8b 측정: 도구 hook은 호출당 약 1,000ms, git 프로세스 13~14개다. #132의 호출당 0.3초 추정보다 크다.
- 같은 프로세스가 `rev-parse --git-common-dir`를 최대 7회 실행했다. `policy.common_dir`의 캐시를 `integration.directory`가 쓰지 않았다.
- Stop은 `board.issues`로 매번 `gh issue list`를 실행했다.

## 적용 기준과 예외

공통 기준은 `.fullops-squad/rules/common/README.md` 및 연결된 코딩·테스트·보안 규칙이다.
기준 커밋은 0f918bb다. 예외 없음. 사용자 방향(#132): npm 의존을 새로 더하지 않는다.

## 먼저 읽을 문서

- `plugins/fullops-squad/scripts/done_gate.py`, `integration.py`, `policy.py`, `flow_gate.py`, `board.py`

## 해야 할 일과 파일 소유권

- [ ] 저장소 위치 조회를 프로세스당 한 번으로 줄인다.
- [ ] 자동 이슈 상태가 없으면 `issue_mode`를 불러오지 않는다.
- [ ] Stop의 `gh issue list`를 5분 안의 성공 기록으로 재사용한다.
- [ ] 도구 hook에 쓰지 않는 `board_documents` import를 늦춘다.
- [ ] 시험을 더하고 dist를 다시 만든다.


## 완료 기준과 검증

- 도구 hook의 git 프로세스와 시간이 줄고 판정은 그대로다.
- HEAD처럼 바뀌는 값은 캐시하지 않는다. 실패한 조회도 캐시하지 않는다.
- 증명 방법: 같은 레포에서 전후 측정, `npm test` 통과, `lint.py --from 0f918bbea336772e1ca0a680bec14dc3897664a8` ERROR 0.

UI 작업이 아니라 디자인 기준은 해당 없음이다.

## 갱신할 산출물

없음.

## 기대 산출물

`done_gate.py`·`integration.py`·`policy.py`·`flow_gate.py`·`board.py` 수정, 시험, 재생성한 dist, `docs/evaluations/qa-reports/HOOK-SLIM-test/report.md`.

## 제약·협업·후속

파일이 서로 겹치고 측정과 함께 판단해야 하므로 직접 처리한다. 이 과제는 main 병합과 릴리스를 하지 않는다.

## 완료 보고

브랜치 / SHA / 변경 이유 / 검토 필요 / 검증한 것과 못 한 것 / 산출물·로그 링크 / 남은 일.
항목당 1~2줄로 쓰고 상세는 `qa-reports/<과제 키>-test/report.md`(역할별로 나눈 키는 `<키>-DEV` 그대로) 링크로 대신한다. 브랜치와 완료 SHA는 여기에 적는다. worker_done 메시지에만 적지 않는다. worker_done 본문 첫 줄은 `[완료] <과제 키> | 브랜치 <이름> | SHA <브랜치 HEAD>` 한 줄로 쓰고 SHA는 하나만 적는다. `남은 일`에 다른 역할의 후속(예: tester 독립 QA)을 쓰면 `work.py finish`가 PLANS.md `## 완료 보고 후속 요청`에 등재한다.
lint DEP-001이 있으면 파일별 의존성 변경 여부·필요성·표준 라이브러리 대안을 적는다. 의존성 변경이 없으면 그 근거를 적는다.
처리는 `fullops-work`, 회신은 `fullops-orca` 스킬을 따른다.
