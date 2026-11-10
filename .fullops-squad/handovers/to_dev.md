---
title: HARNESS-AUTONOMY — 사람 개입을 줄이는 하네스 개선 1~5단계 구현
status: draft
updated: 2026-11-10
owner: dev
tasks: [HARNESS-AUTONOMY]
summary: 사람 개입을 줄이는 하네스 개선 1~5단계 구현
attempt: 430f4fa9dd5047e98f68301dcda0c6db
base: 6a71d41e552a65fe5454635a465942e0d4a1f75d
subagent_level: lite
test_level: lite
---

# HARNESS-AUTONOMY — 사람 개입을 줄이는 하네스 개선 1~5단계 구현

현재 과제는 이 역할 인박스에서 관리한다. 같은 과제의 후속은 본문에 반영하고 다른 과제는 PLANS.md에 대기시킨다. 완료하면 완료 보고 전문을 채우고 work.py finish로 지시서·결과를 로그에 보존한다.

- 작성일: 2026-11-10
- From / To: 사용자 결정(문제 정의 7건, 개선안 8건) / dev 주 담당 세션
- 상태: running
- 테스트 레벨 / 하위 에이전트 레벨: fullops.json 선택값과 같은 값
- 승인된 범위 / 추가 승인이 필요한 행위: 1~5단계 구현, 표적 검증, 로컬 커밋 / push, PR, 릴리스, 배포, 삭제 명령, 외부 발신, jevpet 수정
- 상위 의도: 없음(묶음 작업이 아니다)
- 담당 repo id / 워크트리 절대경로 / 브랜치: 53ea77e9-1236-434b-bae0-d909cea13d73 / C:/Users/shin/orca/workspaces/Fullops-Squad-plugin/dev / fullops/dev
- 병합 책임자 / 기본 브랜치: 사용자 지시를 받은 dev 주 담당 / main
- 복귀 repo id / 워크트리 / 터미널 핸들 / run id / task id / dispatch id: 없음. dev 직접 작업이라 사용자에게 직접 보고한다

`상태`는 과제 상태다. front matter `status`는 문서 상태(draft/review/approved, lint DOC-003 어휘)라 서로 다른 값이 맞다.

## 현재 상황과 확인 근거

- 목적 기준은 "Orca에서 작업할 때 개발이 알아서 진행된다"다. 실사용 레포의 기록으로 문제를 정의하고 원인을 분석했다. 분석 문서는 `.fullops-squad/local/harness-problem-definition.md`와 `harness-cause-and-plan.md`(gitignore)에 있다.
- 지표는 과제당 사람 턴 수와 사람 없이 이어진 과제 수다. 기준선은 약 0.63턴(하한), 배정 75건 중 33건(상한)이다.
- 사용자 결정(2026-11-10): 되돌릴 수 있는 디자인 선택과 버그 수정 여부는 항상 자율 판단하고 추천안과 되돌리는 방법을 기록한다. 배포, 운영 부하 테스트, backfill, 운영 데이터 정리는 사람 승인이다. ART 시안 선검토는 유지한다. 이슈 모드가 꺼져 있으면 보류 작업의 fencing을 푼다(이 조건에 한정). 탐색 패킷은 필수에서 선택으로 바꾼다. worker가 모델 한도로 끝나면 풀릴 때까지 기다리고 다른 모델로 바꾸지 않는다. 재배정은 과제당 최대 2회다. 비용 우선, 런타임 공유 유지.

## 적용 기준과 예외

공통 기준은 `.fullops-squad/rules/common/README.md` 및 연결된 코딩·테스트·보안 규칙이다. 기준 커밋은 main 6a71d41이다. 사용자가 켠 Workflow로 구현한다. Git 커밋은 부모만 한다.

## 먼저 읽을 문서

- `.fullops-squad/local/harness-cause-and-plan.md`

## 해야 할 일과 파일 소유권

- [x] 1단계 재기와 장부: 사람 턴 기록과 현황판 두 지표, 통합 판정에 원격 기본 브랜치, flow 정산, 후속 파서, 낡은 표시 정리, 레포 적용 버전 알림, 역할 워크트리 거부 문구
- [x] 2단계 질문 줄이기: 스킬·worker 안내 문장, 배포·운영 작업은 사용자 승인 고정
- [x] 3단계 과제 경계: PLANS 상태 어휘, 준비된 대기 과제의 Stop 1회 확인, 세션 시작 안내
- [x] 4단계 기록 비용: 패킷 선택화, 사본 gitignore, 준비 커밋 묶기
- [x] 5단계 회복: 이슈 모드 OFF fencing, 한도 종료 알림과 재배정 규칙, 리뷰 완료·키 재시도 경로, 포트 안내
- [ ] 부모: 단계 묶음마다 반박 리뷰, dist 재생성, 표적 시험, lint, 기록

예상 변경 규모는 약 230줄과 시험이다.

## 완료 기준과 검증

- 단계마다 바뀐 동작의 시험이 하나씩 있고 통과한다.
- 증명 방법: `project.md`의 `작업 검증`. `lint.py --repo . --from 6a71d41` 종료코드 0, `ERROR 0`, `실행 불가 0`.
- verifier: lite 과제라 지정하지 않는다. 묶음마다 반박 리뷰 Workflow를 돌린다.
- `review.py need`가 ask·required면 사용자에게 독립 리뷰 여부를 묻는다.

### UI 작업의 디자인 기준과 검증

해당 없음. 현황판에 숫자 두 개를 더하는 것만 있다.

## 갱신할 산출물

없음. 동작 변경은 `report.md`에 적어 다음 릴리스 노트의 원천으로 삼는다.

## 기대 산출물

코드·시험·스킬 문장, `docs/evaluations/qa-reports/HARNESS-AUTONOMY-test/report.md`, PLANS.md 갱신.

## 제약·협업·후속

- push, PR, 릴리스, 배포, 삭제 명령, 외부 발신은 하지 않는다.
- jevpet은 읽기만 한다. 1.23.0 레포 적용과 사본 정리는 구현 뒤에 대상과 범위를 보고하고 따로 승인받는다.
- 채택하지 않은 안: 결정 등급 코드화, 대기 시간 경과 확정, lint timeout 재실행, Orca 호환 검사.

## 완료 보고

