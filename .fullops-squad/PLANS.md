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
| FLOW-STOP-WAIT | Claude Code coordinator가 Stop 훅에 포그라운드 대기로 묶이지 않게 수정 | dev(직접) | 구현·lint 완료(509b9bd, 기준 0f918bb). review need: skip(코드 2개 파일 52줄). lint ERROR 0, WARNING 2(SIZE-001). PR #134 병합(0cea3b8, 완료 SHA ff165f6), #112 종료(결정 D013) | `docs/evaluations/qa-reports/FLOW-STOP-WAIT-test/report.md` |
| LINT-BATCH-READ | lint 파일 읽기를 `git cat-file --batch` 1회로 변경 | dev(직접) | 구현·lint 완료(241b7c4, 기준 0f918bb). 읽기 46.50초 → 1.69초. review need: skip. lint ERROR 0, WARNING 4(SIZE-001). PR #134 병합(0cea3b8, 완료 SHA ff165f6) | `docs/evaluations/qa-reports/LINT-BATCH-READ-test/report.md` |
| HOOK-SLIM | 저장소 위치 조회 통합, 이슈 상태 없을 때 import 생략, Stop `gh` 5분 재사용 | dev(직접) | 구현·lint 완료(d029a21, 기준 0f918bb). 도구 hook 약 1,000ms → 약 530ms, git 13~14개 → 5개, Stop 약 1,700ms → 약 730ms. `npm test` 통과. review need: skip. lint ERROR 0, WARNING 4(SIZE-001). PR #134 병합(0cea3b8, 완료 SHA ff165f6) | `docs/evaluations/qa-reports/HOOK-SLIM-test/report.md` |
| ISSUE112-SIDE | `record` 원자적 쓰기, `integration.py set-sha`, 배정 검사 안내 | dev(직접) | 구현·lint 완료(505d579, 기준 0f918bb). 인박스 검사 시점은 PreToolUse 한계로 안내만 고침. review need: skip(누적 코드 319줄, 기준 400줄). lint ERROR 0, WARNING 5(SIZE-001). PR #134 병합(0cea3b8, 완료 SHA ff165f6) | `docs/evaluations/qa-reports/ISSUE112-SIDE-test/report.md` |
| CLEANUP-FOLLOWUPS | PR #126 후속 8개 묶음을 Workflow로 병렬 구현(결정 D014) | dev(직접) | 구현·lint 완료(37a3ba0, 기준 0cea3b8). `npm test` 통과. review need: ask(코드 25개 파일 약 1,600줄) → 결정 D015로 독립 리뷰 진행. 리뷰어 `claude` `claude-opus-5-5` `high`, run_88a80b39c65f, ctx_e532ea8c0ae8, snapshot `.fullops-review-6c25899aeb1642b4b55a88a6bfbce049`. 결정 D016: 캐시 status·statuses 제거. 1차 리뷰 수락 불가(high 2: Orca `--full` 누락) → 7ef2723 수정. 2차(CLEANUP-FOLLOWUPS-R2) 수락 불가(high 1: `run-current`·`run-show` `--full` 누락) → 267b1b1 수정. 3차(CLEANUP-FOLLOWUPS-R3, 5bc36e5) 수락: 미해결 critical·high·medium 0, low 5. `review.py check` 통과, 1·2차는 supersede·abandon, snapshot 3개 정리. 결정 D018로 PR #135 병합(e7acaee, 완료 SHA fe07f01) | `docs/evaluations/qa-reports/CLEANUP-FOLLOWUPS-test/report.md` |
| RELEASE-1.17.0 | 1.17.0 릴리스(#134·#135), fullops-meter 0.12.0 | dev(직접) | 사용자 지시로 진행. 릴리스 노트는 Workflow로 사실 추출(5개 영역)과 반박 검증(정확성·누락·실행 가능성)을 거쳤다. 검증이 찾은 문서 결함 2건(fullops-orca 스킬 Stop 문구, issue-auto-mode 최소 Orca 문장)을 고쳤다. PR #136 병합(20d2c96, 완료 SHA 8b572c6), 태그·GitHub 릴리스 v1.17.0 게시. review need: skip, lint ERROR 0, npm test·플러그인 검증·CI 통과 | `docs/releases/1.17.0.md` |
| FULLOPS-UPDATE-1.17.0 | 이 PC 설치와 레포 적용 버전을 1.17.0으로 갱신 | dev(직접) | 사용자 지시로 진행. 플러그인 1.17.0·meter 0.12.0 설치, `deps.py` 설치·검사 통과. 레포 적용: `.gitkeep`만 있는 setup 폴더 6개 삭제, 나머지 4건 해당 없음. `update.py --verify` 통과, `plugin_version` 1.17.0. 보류: `/reload-plugins`(사용자) | `docs/exec-plans/phases/FULLOPS-UPDATE-1.17.0.md` |
| ISSUE-CLOSEOUT-1.17.0 | 1.17.0 뒤 이슈 정리 | dev(직접) | 사용자 지시. #82 체크박스에 P0·P1을 표시했다(#81·#84 병합 확인). #132에 선행 개선 2건 반영 댓글을 남겼다. #132·#82는 본 작업이 남아 열어 둔다 | #82, #132 |
| ROADMAP-82-P2 | #82 P2: `작업 검증`·`자주 틀리는 것`, 완료 보고 출력 발췌, verifier 절 | dev(직접) | 구현·lint 완료(f86bb4a, 기준 20d2c96). 결정 D019(standard 이상 기본, lite는 지시서 지정), D020(릴리스에서 필수 적용), D021(이 레포 subagent_level lite, `--local-only`로 원격 브랜치 생성을 피함). review need: skip(코드 2개 파일 8줄). `npm test` 통과, verifier 실제 1회 실행. PR #137 병합(b315e2c, 완료 SHA c6c8866) | `docs/evaluations/qa-reports/ROADMAP-82-P2-test/report.md` |
| RELEASE-1.18.0 | 1.18.0 릴리스(#82 P2) | dev(직접) | 사용자 지시로 진행. 릴리스 노트는 Workflow로 반박 검증(정확성·누락·실행 가능성)해 지적 8건을 반영했다. PR #137(b315e2c)에 함께 넣었고 태그·GitHub 릴리스 v1.18.0을 게시했다. `npm test`·플러그인 검증·CI 통과 | `docs/releases/1.18.0.md` |
| FULLOPS-UPDATE-1.18.0 | 이 PC 설치와 레포 적용 버전을 1.18.0으로 갱신 | dev(직접) | 필수 적용 3건 적용, `update.py --verify` 통과, `plugin_version` 1.18.0. #82의 P2를 체크했다. 보류: `/reload-plugins`(사용자) | `docs/exec-plans/phases/FULLOPS-UPDATE-1.18.0.md` |
| ROADMAP-82-P3 | #82 P3: `fullops-review` `## 리뷰 정책`, 리뷰 보고서 템플릿 3곳 | dev(직접) | 구현·lint 완료(ee124c6, 기준 b315e2c). 결정 D022(nit 상한 한 문장), D023(high는 지금 쓰임), D024(완료 기준 미달 medium 이상과 처분), D025(수락 기준 대체는 제외). review need: skip(코드 1개 파일 2줄). `npm test` 통과, 과거 low 32건 재분류 통과. PR #138 병합(8344743, 완료 SHA 4eea9ef) | `docs/evaluations/qa-reports/ROADMAP-82-P3-test/report.md` |
| RELEASE-1.19.0 | 1.19.0 릴리스(#82 P3) | dev(직접) | 사용자 지시로 진행. PR #138(8344743)에 함께 넣었고 태그·GitHub 릴리스 v1.19.0을 게시했다. `npm test`·CI 통과 | `docs/releases/1.19.0.md` |
| FULLOPS-UPDATE-1.19.0 | 이 PC 설치와 레포 적용 버전을 1.19.0으로 갱신 | dev(직접) | 필수 적용 없음, `update.py --verify` 통과, `plugin_version` 1.19.0. #82의 P3를 체크했다. 보류: `/reload-plugins`(사용자) | `docs/exec-plans/phases/FULLOPS-UPDATE-1.19.0.md` |
| ROADMAP-82-P4 | #82 P4: `project.md` `주요 흐름` 표, 통합 후보 기본값, 세트에 넣을 결함 범위, `--level full --from` | dev(직접) | 구현·lint 완료(7cf3736, 기준 fb48669). 결정 D026(세트 정본은 표), D027(소프트 상한 10), D028(흐름·재발 결함만), D029(플레이북 eval 미반영 명시). review need: skip(코드 2개 파일 5줄). `npm test` d8c6f60 통과, 반박 검증 2회 반영. PR #140 병합(30a8837, 완료 SHA e21a4fa) | `docs/evaluations/qa-reports/ROADMAP-82-P4-test/report.md` |
| RELEASE-1.20.0 | 1.20.0 릴리스(#82 P4) | dev(직접) | 사용자 지시로 진행. PR #140(30a8837)에 함께 넣었고 태그·GitHub 릴리스 v1.20.0을 게시했다. `checks`·`claude-review` 통과, 리뷰 지적 없음 | `docs/releases/1.20.0.md` |
| FULLOPS-UPDATE-1.20.0 | 이 PC 설치와 레포 적용 버전을 1.20.0으로 갱신 | dev(직접) | 필수 적용 3건 적용, `update.py --verify` 3/3, `plugin_version` 1.20.0. #82의 P4를 체크하고 eval 미반영을 댓글로 적었다 | `docs/exec-plans/phases/FULLOPS-UPDATE-1.20.0.md` |
| ROADMAP-82-P5 | #82 P5: 현황판 `작업 지표`(첫 시도 완료, 재작업, 리뷰 소요), 발견의 intent 재진입 문구 | dev(직접) | 병합(#142, 66a481c)과 1.21.0 릴리스(#143, a43d19e) 완료, #82의 P5 체크. review need: skip(코드 4개 파일 119줄) | `docs/evaluations/qa-reports/ROADMAP-82-P5-test/report.md` |
| FULLOPS-UPDATE-1.21.0 | 이 PC 설치와 레포 적용 버전을 1.21.0으로 갱신 | dev(직접) | 필수 적용 0건, `update.py --verify` 0/0, intent 템플릿 문장 동기화, `plugin_version` 1.21.0. `/reload-plugins` 사용자 실행, 오류 없음 | `docs/exec-plans/phases/FULLOPS-UPDATE-1.21.0.md` |
| OUTPUT-HISTORY-A | #104 후보 A: 긴 Bash 출력 줄이기(`output_trim.py`) | dev(직접) | 병합(#145, 6b6eae0). 절감량 실측은 남았다 | `docs/evaluations/qa-reports/OUTPUT-HISTORY-A-test/report.md` |
| RELEASE-1.22.0 | 1.22.0 릴리스(#104 후보 A) | dev(직접) | 사용자 지시로 진행. 태그·GitHub 릴리스 v1.22.0 게시. 병합 f8363f7 | `docs/releases/1.22.0.md` |
| FULLOPS-UPDATE-1.22.0 | ShinPC 설치와 레포 적용 버전을 1.22.0으로 갱신 | dev(직접) | 필수 적용 0건, `update.py --verify` 0/0, `plugin_version` 1.22.0. `deps.py --check`는 `.in_use` 표지 때문에 한 번 실패했고 `--runtime-only` 뒤 통과. `/reload-plugins`는 사용자 실행 대기 | `docs/exec-plans/phases/FULLOPS-UPDATE-1.22.0.md` |
| RELEASE-1.22.1 | 1.22.1 릴리스(`.in_use` 표지 오탐 수정) | dev(직접) | 사용자 지시로 진행. 수정 병합(#149, d1f8797). 이 PR의 병합 커밋에 태그·GitHub 릴리스 v1.22.1을 게시한다. 이 PC와 레포 적용은 지시 범위 밖이라 하지 않았다 | `docs/releases/1.22.1.md` |

## 대기 목록

2026-11-07에 main 체크아웃 세션에서 이관했다. 담당은 모두 dev(`claude` `claude-opus-5-5` `high`, 사용자 지정), 작업 공간은 `fullops/dev` 워크트리다.

| 순서 | 과제 키 | 목표 | 재개 조건 | 원천 |
|---|---|---|---|---|
| 1 | FLOW-STOP-WAIT | Claude Code coordinator가 Stop 훅에 포그라운드 대기로 묶이지 않게 수정 | 완료(위 표) | #112 |
| 2 | LINT-BATCH-READ | `lint.py`의 `blob()`을 `git cat-file --batch` 일괄 읽기로 변경. 측정 49.2초 → 0.9초 | 완료(위 표) | #132 선행 개선 |
| 3 | HOOK-SLIM | hook 전체 시간을 먼저 재고, 관계없는 호출 조기 종료·import 지연·git 호출 통합 | 완료(위 표) | #132 선행 개선 |
| 4 | ISSUE112-SIDE | `orca_wait --ack` 동시 실행 JSON 오류, 인박스 첫 줄 검사 시점, `worker_done` 형식 처리 | 완료(위 표) | #112 "함께 본 작은 문제" |
| 5 | CLEANUP-FOLLOWUPS | #126 후속: lint 서브모듈·Windows timeout, 리뷰 해시 autocrlf, Jev 콜드 메타데이터, 이슈 모드 fencing·잠금·intent·조회 비용, flow-gate 내용 해석, setup 범위·스킬 경로·빈 폴더, fullops-meter 정리, 큰 테스트 3건 | 완료(위 표, PR #135) | PR #126 "후속으로 남긴 것" |
| 6 | ROADMAP-82 | 체크 상태 갱신·P2·P3·P4·P5 릴리스 완료(위 표). 남은 일: 비어 있는 전환 E1·E2·E9, 이 레포 자체 기록의 S7 측정. E13은 D026 이후 게이트 없이 지침 문장으로 둔다 | 단계별 사용자 확인 | #82 |
| 7 | OUTPUT-HISTORY | #104 후보 A(Bash 출력 압축)는 구현(위 표), B(작업 이력 색인)는 A의 절감량을 잰 뒤, C는 보류 | A 릴리스 뒤 `trim.jsonl` 실측 | #104 |
| 8 | STATUS-DIAGRAM | 현황판 PR 표시, D03 구조도 원천, 서비스 구조 섹션 | 사용자가 범위를 정할 때 | #59 |
| 9 | AUTONOMY-STAGE3 | 섀도 판정과 실제 결정 비교, `auto`·`delay` 개방 결정 | 섀도 판정이 쌓이고 사용자가 결정할 때 | #125 |
| 10 | ULTRACODE-REVIEW | 울트라코드 하위 에이전트 관리 상세 검토 | 사용자가 시작할 때 | #131 |
| 11 | RUST-MIGRATION | Python·npm 없는 Rust 전환 검토 | 사용자가 시작할 때 | #132 |
| 12 | HERDR-HOST | Herdr 호스트 어댑터. 사용자 결정으로 기각(2026-11-10), 이슈 종료 | 없음(진행 안 함) | #115 |
| 13 | ORCA-PLUGIN | Orca 플러그인 전환 재검토 | 이슈의 재검토 조건 충족 | #120 |
| 14 | DIRECTORY-LISTING | 플러그인 디렉터리 포털 리뷰 결과 확인 | 포털 결과 확인(사용자) | #34 |
| 15 | GROK-WAKE-CHECK | grok이 백그라운드 완료로 세션을 깨우는지 확인. grok 1.0.70 문서에 auto-wake가 있어 스킬·flow-gate의 "깨우지 않는다"가 낡았을 수 있다 | 사용자가 시작할 때 | FLOW-STOP-WAIT 조사 |

### CLEANUP-FOLLOWUPS 리뷰 후속

1·2차 리뷰가 병합 뒤에 처리해도 된다고 판단한 항목이다. 담당은 dev다.

- CI 공백(medium): Windows 전용 `windows_paths`, Windows의 `tests/lint.py`, render 파이프라인, meter 시험이 CI에서 돌지 않는다. 사용자 결정 D017로 후속 등재했다. 재개 조건: 사용자가 CI 비용과 Windows job 범위를 정할 때.
- lint: 스레드가 `RUNNING`에 넣기 전의 중단은 그 프로세스를 timeout까지 남긴다(low). SIGINT가 무시된 채 상속되면 중단 시험이 60초 뒤 실패한다(low).
- `sync`가 `--full` worker 목록 전체를 history에 쌓는다. 100행이면 호출당 약 200KB다(low). 재개 조건: 상태 파일 크기 문제 발생.
- `flow_gate.task_listing`이 `integration.task_list`와 중복이다(low). 시험이 `flow_gate.orca`를 바꿔 끼우므로 함께 정리한다.
- 3차 리뷰 low 5건: `integration.record`가 기본 `check` 메시지에 없는 `run_id`를 읽어 bound Run의 task 목록을 쓴다. 그 시험 대역이 이 차이를 숨긴다. `orca_wait.summarize`가 기본 메시지에 없는 `from_handle`·`created_at`을 읽는다(표시 전용). `nohup`으로 SIGHUP을 무시한 lint도 터미널 종료에 중단된다. reconcile의 worker-list 대역이 `--full`을 무시한다. 재개 조건: 다음 integration·lint 변경.
- 하네스 충돌: 리뷰어 배정 게이트(`route_key_denial`)가 리뷰 키의 route 기록을 요구하는데, `jev_route.py`가 만든 route는 `requires_packet`을 켜서 dev 직접 작업 리뷰의 `review.py check`가 "탐색 패킷이 없습니다"로 실패한다. `work.py finish`도 같은 이유로 실패한다. 이번에는 게이트 통과용으로 만든 `CLEANUP-FOLLOWUPS-route.json`(81002f2)과 커밋하지 않은 `CLEANUP-FOLLOWUPS-R3-route.json`을 지웠다. 두 분류(design → architecture)도 사실과 달랐다. 원본은 Git 이력에 남는다. 재개 조건: 다음 FullOps 하네스 수정.
- 리뷰 뒤 기록 커밋을 더하면 done-gate의 `direct_check`가 HEAD와 리뷰 SHA가 달라 리뷰 기록이 없다고 막는다. main 병합 뒤에는 풀린다. 재개 조건: 다음 FullOps 하네스 수정.
- 이전 coor의 bare `git push`, `gh issue comment 2`는 fencing을 통과한다(low). `complete`의 head SHA 확인으로 피해가 제한된다. 재개 조건: 실제 발생 또는 다음 이슈 모드 변경.
- meter가 일시 읽기 실패로 얻은 경로를 60초 캐시한다(low). 표시 전용이다. 재개 조건: 다음 meter 변경.
- `issue_mode.py`(1401줄) 분할 검토. 재개 조건: 다음 이슈 모드 변경.
- grok auto-wake 확인은 대기 목록 15번(GROK-WAKE-CHECK)에 있다.

### ROADMAP-82-P2 후속

담당은 dev다.

- `setup.py`를 `--local-only` 없이 실행하면 원격에 `fullops/architecture` 브랜치를 만든다. 이 레포에서 역할을 정리할지는 사용자 결정이다.
- `lint-result.json`의 `head`는 lint 뒤 기록 커밋이 있으면 완료 SHA보다 오래될 수 있는데 `fullops-work`에 적지 않았다(low). 재개 조건: 다음 `fullops-work` 변경.

### ROADMAP-82-P3 후속

담당은 dev다.

- 리뷰 보고서도 `REPORT_LINES`(40줄) 안내에 걸린다(`harness_gate.py:145-149`). 템플릿만으로 44줄이다(low, 이전부터 있던 문제). 재개 조건: 다음 `harness_gate.py` 변경.
- 수락 기준을 coordinator가 바꾸는 문제(jevpet UX2-ART)는 결정 D025로 P3에서 뺐다. 재개 조건: 같은 일이 다시 나올 때.

### FULLOPS-UPDATE-1.22.0 후속

담당은 dev다.

- `hook_runtime.package_files`의 `.in_use` 표지 오탐: 1.22.1로 릴리스한다(RELEASE-1.22.1). 이 PC 적용은 재개 조건: 사용자의 업데이트 지시.
- Orca 프로필의 `fullops-deps.json`이 `~/.claude` 사본으로 덮어써져 `home` 값이 달라지고 `deps.py --check`가 `host dependency installation incomplete`로 실패한다. `--host`로 고친 뒤 되돌아간 일이 1회 있었다(2026-11-10 00:13:02). 복사 주체는 확인되지 않았다. 재개 조건: 사용자가 `home` 비교를 고칠지 정할 때.
- #104 절감량: `.fullops-squad/local/outputs/trim.jsonl`로 잰다. 이 워크트리의 앞 2줄은 일부러 만든 시험 출력이라 뺀다. 재개 조건: 실제 작업이 쌓였을 때.

### ROADMAP-82-P5 후속

담당은 dev다.

- 지표로 판단할 수 있는 것은 입증되지 않았다. 재개 조건: 1.21.0을 적용한 KnowsLink 또는 jevpet에서 묶음 하나가 끝난 뒤 값을 본다. 쓸모가 없으면 표를 빼는 것을 사용자에게 묻는다.
- 첫 시도 CI 성공률은 뺐다. 재개 조건: 제품 CI가 있는 FullOps 레포가 생기거나 사용자가 요청할 때.
- FOLLOWUP 연쇄는 재작업에 잡히지 않는다. 재개 조건: 지표에 넣어 달라는 요청이나 연쇄 재발.
- `board/index.html`이 384줄로 상한 300을 넘는다(이전 371, WARNING). 재개 조건: 현황판을 다음에 고칠 때.

### ROADMAP-82-P4 후속

담당은 dev다.

- 고정 세트의 효과는 입증되지 않았다. 재개 조건: 1.20.0을 적용한 KnowsLink 또는 jevpet에서 큰 틀 검수 2회를 본다. 표가 비어 있거나 재실행이 없으면 표를 intent 방식으로 되돌릴지 사용자에게 묻는다.
- 세트 재실행의 커밋 범위(실행마다 3개 파일)는 바꾸지 않았다(사용자에게 고지). 재개 조건: 세트가 실제로 쌓일 때.
- `minimal`에서 `lint.json`에 `level: full` 명령이 있을 때 통합 후보 full 실행의 예외, 묶음 시작 SHA를 기록하는 칸은 넣지 않았다(low). 재개 조건: 실제로 막힌 사례.
- 플레이북 eval 원뜻(에이전트 구성 회귀)은 반영하지 않았다(D029). 재개 조건: 사용자 결정.

### 사용자 결정 대기

- `core.longpaths` 켜기(`FULLOPS-UPDATE-1.16.1.md` 보류 항목)
