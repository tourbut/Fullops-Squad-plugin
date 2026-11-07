---
title: 현재 작업
status: draft
updated: 2026-11-07
owner: dev
summary: 현재 작업
---

# 현재 작업

진행 상태와 우선순위의 정본이다. 작업 명세는 handovers, 상세 이력은 logs에 둔다.

| 과제 키 | 목표 | 담당 | 상태 | 지시서·원천 링크 |
|---|---|---|---|---|
| ISSUE-SLASH-SIDEBAR | 이슈 자동 모드 슬래시 명령 인자, fullops-meter footer·pane에 ON/OFF 표시 | dev(직접) | 구현·lint 완료, 1.12.0(fullops-meter 0.11.0)으로 릴리스. 기준 7187d08 | `feat/issue-mode-sidebar` |
| ISSUE-HELD-QUESTION | 사용자 결정 보류를 이슈 댓글 질문으로 옮기고 사이드바 현재 이슈 선택 수정 | dev(직접) | 구현·lint·CI 완료, PR #114 병합(2911c36), 1.12.1 릴리스. 기준 8896129. jevpet 모니터링에서 #1·#35 보류에 이슈 댓글이 없던 것이 근거 | `fix/issue-mode-held-question` |
| LINT-GATE-SCOPE | done-gate 재실행 조건 축소: 정확한 --from 안내, 같은 트리·계획/현황판 기록 커밋 인정, dev 직접 기준을 원격 기본 브랜치 merge-base로 | dev(직접) | 구현·테스트, 1.13.0 릴리스 대상. 기준 9cb771b. 근거: 이번 세션 flow-gate 132초 반복·병합 커밋 재lint | `fix/lint-gate-scope` |
| ISSUE-PR-FOLLOWUP | draft PR 실패 check·수정 요청 리뷰를 새 attempt로, 병합된 이슈 브랜치·워크트리 `prune` | dev(직접) | 구현·테스트, 1.13.0 릴리스 대상. 근거: PR #113 CI 실패, 10-29 병합 브랜치 33개 수동 정리 | `fix/lint-gate-scope` |
| GH-1369701248-109-A1 | 이슈 #109 checkpoint --received 예시 | dev | 배정 안 함: 구현 전 작성자 질문(f3c5d022…)이 필요했고 답변 뒤 새 attempt A2로 대체됨 | https://github.com/tourbut/Fullops-Squad-plugin/issues/109 |
| GH-1369701248-109-A2 | 같은 이슈, 답변 B 반영 | dev | 배정 완료(task_e803a1de7619/ctx_2282a0bcc3dd), failed: push hook 거부, A3로 대체. 지시서·route는 브랜치 `fullops/issue-109-a2` | `fullops/issue-109-a2` d6a40eb |
| GH-1369701248-109-A3 | 같은 이슈, dist 사본 포함 | dev | 배정 완료(task_baddb9300a28/ctx_362d15e01cf9), completed. draft PR #110은 2026-11-04 사용자 결정으로 병합 없이 닫고 브랜치 삭제 | https://github.com/tourbut/Fullops-Squad-plugin/pull/110 |
| NOTIFY-FULLO-RELAY | main push·이슈 이벤트를 Fullo webhook으로 전달하는 CI 워크플로 | dev(직접) | PR #123 병합(11e5ab9, 완료 SHA 80faa21). 리뷰 need: skip(코드 0개 파일). lint 결과 재사용(base dfcb440, 적용 검사 없음). 원격 main push 후 notify-fullo 실행 결과 확인 | https://github.com/tourbut/Fullops-Squad-plugin/pull/123 |
| REPO-CLEANUP | 전체 코드 정리, 불필요 파일 삭제, 로직 점검·리팩토링 | dev(직접) | 완료. PR #126 병합(36a7949, 완료 SHA 289a7dc), 1.16.0 릴리스. 감사 발견 213건 중 187건 적용, 26건은 사유와 함께 후속(PR #126 본문). 전체 npm test 통과(35de341), gate lint ERROR 0(9ed74bd). review need: required/ask → 사용자 결정 D003으로 생략(waiver 기록). 결정 D001 증거 묶음 삭제, D002 로컬 잔여물 삭제, D005 Workflow 예외 명시 | https://github.com/tourbut/Fullops-Squad-plugin/pull/126 |
| AUTONOMY-SHADOW | #125 1단계(섀도 판정기·이벤트·결정 형식)와 2단계의 이 레포 몫 | dev(직접) | 1·2단계 완료. PR #127 병합(0d28d99, 완료 SHA 4dc7797), 1.16.0 릴리스. review need: skip(코드 7개 파일 383줄), gate lint ERROR 0. 남은 일: 3단계(auto·delay 개방)는 섀도 결과를 검토한 뒤 사용자와 정한다. orca-helm·Grok Bot은 다른 저장소 몫 | https://github.com/tourbut/Fullops-Squad-plugin/issues/125 |
| PSTACK-DEPENDENCY | #124 최종 결정(D010): Cursor 공식 pstack을 Claude Code 의존 플러그인으로 설치 | dev(직접) | PR #129, 기준 bf6fec1. lint ERROR 0(9f057e0), review need skip(코드 2개 파일 4줄). #124는 결정·근거 댓글로 완료 처리(D009). PR #129 병합(0f6599e), 1.16.1 릴리스. 이 PC의 Claude Code에도 설치 | https://github.com/tourbut/Fullops-Squad-plugin/pull/129 |
| FULLOPS-UPDATE-1.16.1 | 레포 적용 버전을 1.11.0에서 1.16.1로 갱신하고 dev 작업 공간을 `fullops/dev` 워크트리로 옮김 | dev(직접) | 완료. 사용자 결정 D011로 PR #133 병합(0f918bb, 완료 SHA 80e7b41). review need: skip(코드 0개 파일). lint ERROR 0(적용 검사 없음), CI checks 통과. main 체크아웃과 `fullops/dev` 동기화 | https://github.com/tourbut/Fullops-Squad-plugin/pull/133 |
| FLOW-STOP-WAIT | Claude Code coordinator가 Stop 훅에 포그라운드 대기로 묶이지 않게 수정 | dev(직접) | 구현·lint 완료(509b9bd, 기준 0f918bb). review need: skip(코드 2개 파일 52줄). lint ERROR 0, WARNING 2(SIZE-001). 보류: main 병합과 #112 종료, 담당 사용자, 재개 조건 사용자 승인 | `docs/evaluations/qa-reports/FLOW-STOP-WAIT-test/report.md` |
| LINT-BATCH-READ | lint 파일 읽기를 `git cat-file --batch` 1회로 변경 | dev(직접) | 구현·lint 완료(241b7c4, 기준 0f918bb). 읽기 46.50초 → 1.69초. review need: skip. lint ERROR 0, WARNING 4(SIZE-001). 보류: main 병합, 담당 사용자, 재개 조건 사용자 승인 | `docs/evaluations/qa-reports/LINT-BATCH-READ-test/report.md` |

## 대기 목록

2026-11-07에 main 체크아웃 세션에서 이관했다. 담당은 모두 dev(`claude` `claude-opus-5-5` `high`, 사용자 지정), 작업 공간은 `fullops/dev` 워크트리다.

| 순서 | 과제 키 | 목표 | 재개 조건 | 원천 |
|---|---|---|---|---|
| 1 | FLOW-STOP-WAIT | Claude Code coordinator가 Stop 훅에 포그라운드 대기로 묶이지 않게 수정 | 완료(위 표) | #112 |
| 2 | LINT-BATCH-READ | `lint.py`의 `blob()`을 `git cat-file --batch` 일괄 읽기로 변경. 측정 49.2초 → 0.9초 | 완료(위 표) | #132 선행 개선 |
| 3 | HOOK-SLIM | hook 전체 시간을 먼저 재고, 관계없는 호출 조기 종료·import 지연·git 호출 통합 | 진행 중(`handovers/to_dev.md`) | #132 선행 개선 |
| 4 | ISSUE112-SIDE | `orca_wait --ack` 동시 실행 JSON 오류, 인박스 첫 줄 검사 시점, `worker_done` 형식 처리 | 3번 완료 | #112 "함께 본 작은 문제" |
| 5 | CLEANUP-FOLLOWUPS | #126 후속: lint 서브모듈·Windows timeout, 리뷰 해시 autocrlf, Jev 콜드 메타데이터, 이슈 모드 fencing·잠금·intent·조회 비용, flow-gate 내용 해석, setup 범위·스킬 경로·빈 폴더, fullops-meter 정리, 큰 테스트 3건 | 4번 완료. 묶음이 크면 항목별 과제로 나눈다 | PR #126 "후속으로 남긴 것" |
| 6 | ROADMAP-82 | #82 체크 상태 갱신, P2–P5, 비어 있는 전환 E1·E2·E9·E13, KnowsLink S7 측정 | 5번 완료. 단계별 사용자 확인 | #82 |
| 7 | OUTPUT-HISTORY | #104 후보 A(Bash 출력 압축), B(작업 이력 색인). C는 보류 | 사용자가 순서를 정할 때 | #104 |
| 8 | STATUS-DIAGRAM | 현황판 PR 표시, D03 구조도 원천, 서비스 구조 섹션 | 사용자가 범위를 정할 때 | #59 |
| 9 | AUTONOMY-STAGE3 | 섀도 판정과 실제 결정 비교, `auto`·`delay` 개방 결정 | 섀도 판정이 쌓이고 사용자가 결정할 때 | #125 |
| 10 | ULTRACODE-REVIEW | 울트라코드 하위 에이전트 관리 상세 검토 | 사용자가 시작할 때 | #131 |
| 11 | RUST-MIGRATION | Python·npm 없는 Rust 전환 검토 | 사용자가 시작할 때 | #132 |
| 12 | HERDR-HOST | Herdr 호스트 어댑터 | 사용자가 시작할 때 | #115 |
| 13 | ORCA-PLUGIN | Orca 플러그인 전환 재검토 | 이슈의 재검토 조건 충족 | #120 |
| 14 | DIRECTORY-LISTING | 플러그인 디렉터리 포털 리뷰 결과 확인 | 포털 결과 확인(사용자) | #34 |
| 15 | GROK-WAKE-CHECK | grok이 백그라운드 완료로 세션을 깨우는지 확인. grok 1.0.70 문서에 auto-wake가 있어 스킬·flow-gate의 "깨우지 않는다"가 낡았을 수 있다 | 사용자가 시작할 때 | FLOW-STOP-WAIT 조사 |

### 사용자 결정 대기

- `core.longpaths` 켜기(`FULLOPS-UPDATE-1.16.1.md` 보류 항목)
- FLOW-STOP-WAIT·LINT-BATCH-READ의 main 병합과 #112 종료
