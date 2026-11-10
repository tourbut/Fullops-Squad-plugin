---
title: HARNESS-AUTONOMY 리뷰
status: review
updated: 2026-11-10
owner: reviewer
summary: 8f11810da055 병합 전 독립 리뷰 보고서. 수락 가능, critical·high·medium 0, low 5
---

# HARNESS-AUTONOMY 리뷰

- 검토자 / CLI / 모델: 독립 reviewer 세션 `reviewer-d3dce76a-0463-49da-aecc-30fdfae7c9a6` / `claude` / `claude-opus-5-5` effort `high`. 이 tuple은 `docs/evaluations/jev/HARNESS-AUTONOMY-model-reviewer.json`(source user)에 있다. 구현자 세션은 `f0726204-9981-4e4d-9372-476f2ff7eca3`다. 이 결론은 AI 검토자의 판단이고 OCR의 자동 판정이 아니다.
- base SHA / head SHA / merge-base: `6a71d41e552a65fe5454635a465942e0d4a1f75d` / `8f11810da055ae4d8f6e44fe82ed69b911b29a88` / `6a71d41e552a65fe5454635a465942e0d4a1f75d`.
- snapshot: `C:\Users\shin\orca\workspaces\Fullops-Squad-plugin\.fullops-review-aef1847ba6e847f3bc3beb4dba0a21b2`, detached HEAD 8f11810, `git status --porcelain` 0줄. 읽기만 했다.
- OCR 버전 / 적용 규칙: open-code-review v1.13.6 (891df1b). `.fullops-squad/review/rule.json`(rule_sha256 `34c8f6e8…`), 그룹 규칙은 `rules.json`. 공통 규칙은 `.fullops-squad/rules/common/README.md`와 연결된 코딩·테스트·보안 규칙(기준 커밋 main 6a71d41, 지시서 `적용 기준과 예외`)이다.
- 요구사항·완료 기준 원천과 기준별 충족/미달: 원천은 snapshot의 `.fullops-squad/handovers/to_dev.md`(사용자 결정, 완료 기준)와 `.fullops-squad/docs/evaluations/qa-reports/HARNESS-AUTONOMY-test/report.md`다. dev 직접 작업이라 탐색 패킷은 없다. 상위 의도는 없다.
  - 단계마다 바뀐 동작의 시험이 하나씩 있다: 충족. 1단계는 `tests/board.py`·`flow-state.py`·`integration-gate.py`, 2~3단계는 `flow-gate.py`·`product-routing.py`, 4~5단계는 `issue-mode.py`·`review-check.py`·`stabilization.py`·`jev-*.py`에 있다.
  - 증명 방법 `lint.py --repo . --from 6a71d41` 종료코드 0, ERROR 0, 실행 불가 0: 충족(`lint.json`, head 8f11810).
  - `review.py need` ask/required면 사용자에게 묻는다: 충족. PLANS 행에 required/ask가 있고 이 리뷰가 그 결과다.
  - 사용자 결정 대조: 충족. 아래 `결정 대조`를 본다.
- 전체 변경 / OCR 대상 / 제외 / reviewed / skipped: 82 / 39 / 43 / 43 / 39. skipped 39건은 모두 `dist/` 생성 사본이다. HEAD에서 원본과 blob 해시가 같음을 확인했다. 지시서 승인 범위(1~5단계, 표적 검증, 로컬 커밋) 밖의 변경은 없다. push·PR·릴리스·jevpet 변경은 없다.
- lint(`lint.json`) ERROR / WARNING / 실행 불가: 0 / 16 / 0. 명령은 issue-mode·jev-route·flow-gate·packaging이 passed(종료코드 0)다. lint-gate는 paths 불일치로, full은 test_level lite로 skipped다. 둘 다 고정 사유가 있다. WARNING은 SIZE-001 11건, SIZE-002 1건, SLOP-003 4건이다. SLOP-003은 `flow_gate.py` 745·749·756·809줄의 SessionStart·prompt 보조 기록 경로다. hook 오류가 작업을 막지 않게 하는 기존 패턴과 같고 각 줄에 사유 주석이 있어 수락한다. SIZE-001은 기존 큰 파일이 조금 커진 것이다. 분할은 이 과제 범위 밖이다.
- SIZE-002: 지시서 예상 규모는 "약 230줄과 시험"이다. 실제 추가는 745줄이고, 그중 시험이 369줄이다. 시험을 빼면 약 376줄이다. 다섯 단계를 한 과제로 승인받았고, 반박 리뷰에서 나온 수정(high 1, medium 4)이 더해졌다. 차이 사유는 검증 보고서에 있어 수락한다.
- DEP-001: 해당 없음. 의존성 파일 변경이 없고 새 import는 표준 라이브러리(`time`, `datetime.timezone`)와 레포 내부 모듈뿐이다.
- UI 디자인: 지시서가 "해당 없음. 현황판에 숫자 두 개를 더하는 것만 있다"고 적었다. `board/index.html` 변경은 기존 표 마크업과 `esc`를 그대로 쓴다. 브라우저 렌더는 검증 보고서에서 미실행으로 밝혔다. 숫자 표 한 줄이라 영향이 작아 수락한다.

## 검토 범위

result.json의 82개 (path, status)에 모두 상태와 사유를 적었다. 읽은 방식은 다음과 같다.

- 코드: `flow_gate.py`, `integration.py`, `board.py`, `flow_state.py`, `issue_mode.py`, `review.py`, `jev_route.py`, `work.py`, `decision.py`, `scripts/build.py`의 diff를 읽었다. 판단에 필요한 주변 코드(`issue_mode.occupies`·`worker_job`, `review.historical`·`cleanup`·`prune`·`snapshot`, `integration.references`, `flow_gate.main` Stop 분기, `done_gate.run_hook`)도 snapshot에서 읽었다.
- 시험: 12개 시험 파일의 추가 부분을 읽고, 시험이 주장하는 경계와 코드 조건이 맞는지 대조했다.
- 문서·스킬: 네 스킬, 템플릿 PLANS·_TEMPLATE·testing.md, flow-graph·issue-auto-mode·README 문장이 코드 동작과 맞는지 대조했다.
- dist: 39개 사본은 HEAD blob 해시가 원본과 같다. `dist/directory/.../hooks.json`은 기존 run.sh 명령 변환 외에 원본과 같고 StopFailure가 `flow_gate failure`로 등록됐다. INSTALL·README 생성 문서는 원본 문장과 같다.
- 하네스 자동 생성 기록(제외 43건)은 prepare가 이미 걸렀다. 이 범위의 실제 diff에는 자동 생성 증거 파일이 없다.

### 결정 대조

| 사용자 결정·지정 확인 항목 | 확인 결과 |
|---|---|
| 운영 배포·운영 부하 테스트·backfill·운영 데이터 정리는 항상 사용자 승인 | 유지. coordinator SessionStart brief, fullops-orca 스킬("위임 범위와 관계없이 매번 따로 승인"), 템플릿 PLANS `## 위임 범위`("위임하지 않는다")에 있다. 위임 범위 원문 주입도 이 문장 뒤에 붙는다. Stop 차단 문구는 예외를 다시 적지 않는다(low 1). |
| 되돌릴 수 있는 디자인 선택·버그 수정 여부는 자율 | worker·designer·제품 기획 brief, 템플릿, 스킬에 반영됐다. 추천안과 되돌리는 방법 기록 요구도 있다. 제품 규칙·범위·공유 계약·되돌릴 수 없는 일의 질문 경로는 남았다. |
| 이슈 모드 fencing 해제는 모드 OFF·보류 잡·묶이지 않은 세션에 한정 | 유지. `worker_job`은 `bound` 세션을 먼저 처리한다. OFF일 때 조회를 건너뛰는 조건은 모든 job이 `occupies`(ACTIVE 또는 미정산 dispatch_intents)가 아닐 때뿐이다. ON이면 전과 같다. `boundary`의 coordinator hold 판정은 바뀌지 않았다. `publish`는 표시만 비우고 SQLite 상태는 그대로다. 시험 `inert_when_off`가 세 경계를 확인한다. |
| 리뷰 수락 조건 유지 | 유지. `issue_mode.complete`의 새 경로는 `snapshot-cleanup.json` state removed일 때만 쓴다. 이때 `review.historical`이 live_check passed, 증거 hash, 독립성 일치를 요구한다. 이 영수증은 `cleanup --finished`가 live `check()` 통과 뒤에만 쓴다. 추가로 base/head, rule hash, 과제 패킷을 다시 검사한다. prepare·snapshot 재시도는 결과·중단·리뷰어 기록이 없는 실패 흔적에만 허용된다. |
| 패킷이 있는 과제의 검사 유지 | 유지. `review.check_packets`, `integration.baseline_denial`, `jev_packet.check`는 패킷 파일(작업 트리·HEAD 커밋·worker 워크트리) 또는 기존 `requires_packet` true가 있으면 전처럼 검사한다. 새 route만 `requires_packet`을 쓰지 않는다. |
| 모델 한도: 대기 후 같은 모델로 재배정, 최대 2회 | fullops-orca 스킬에 반영됐다. StopFailure hook은 escalation을 한 번 보내고 정산하지 않는다. Stop 게이트는 그대로 막는다(시험 확인). |

### 지정 위험 경로 확인

- hook이 세션을 가두는 경로: 찾지 못했다. lead Stop의 대기 행 차단은 첫 Stop에서 `ready_blocked`를 저장한다. 같은 목록으로 `stop_hook_active` Stop이 오면 systemMessage로 통과한다. 다른 차단이 먼저 나면 평가하지 않는다. 그래서 한 응답에서 추가 차단은 최대 한 번이다. 사용자 턴마다 다시 한 번 막히지만, 행을 `보류(…)`/`대기(사람: …)`로 바꾸면 멈춘다. 이 동작은 사용자 결정 "준비된 대기 과제의 Stop 1회 확인"과 같다. worker 세션(dispatch 있음)은 `primary`가 아니라 대상이 아니다.
- 오류로 작업을 막는 경로: 찾지 못했다. 새 SessionStart 보조(대기·위임·prune·버전), 사람 턴 기록, `board.ready`, `metrics.autonomy`는 모두 `except Exception`으로 삼킨다. StopFailure는 output `{}`이고 `run_hook`이 나머지 예외를 삼킨다. `integration.pending`의 hold 재검사는 기존 비보류 경로와 같은 `ancestor` 호출이다.
- integration hold 자동 해제가 병합되지 않은 SHA를 푸는 경우: 찾지 못했다. 해제 조건은 `ancestor(sha, published or base)`뿐이다. git 연결 setup에서 `published`는 `refs/remotes/<remote>/<base>`, 로컬 전용은 원본 체크아웃 브랜치다. 로컬에만 병합하고 push하지 않은 SHA는 hold를 유지한다. 비보류 기록이면 push 대상으로 남는다. 보고 SHA가 base와 같은(커밋 없는) 경우도 풀리지만, 병합할 것이 없으므로 결함이 아니다. 시험 `published_holds`는 미병합 SHA가 남는 것, 원격에 없는 SHA, HOLD_CAP 순환, settle을 확인한다.
- lead Stop의 대기 행 판정: 오판을 찾지 못했다. `WAITING.match`는 상태가 `대기`로 시작하고 괄호(반각·전각, 앞 공백 허용)가 붙지 않은 행만 고른다. 원천 칸이 빈 행, 담당 인박스 제목이 있는 행, 흐름 노드가 build 이상인 행, `선행:` 과제가 report 미만인 행은 뺀다. 선행 과제의 흐름 기록이 없으면 준비되지 않은 것으로 본다. 그래서 오판 방향은 배정 누락 쪽이다. 운영 작업 행의 내용 판정은 없다(low 1).

## 발견 사항

| # | 태그 / 심각도 | 파일·줄 | 재현 조건 / 영향 | 수정 상태 |
|---|---|---|---|---|
| 1 | [준수] low | `plugins/fullops-squad/scripts/board.py:124-145`, `flow_gate.py:935` | 운영 배포 행을 `대기`로 적으면 Stop이 "묻지 말고 배정"을 지시한다. 승인 규칙은 brief·스킬에 있고 배정 자체가 배포를 실행하지는 않는다. | 미해결, 후속(차단 문구에 운영 작업 예외 추가) |
| 2 | [버그] low | `flow_gate.py:750-756` | 다른 세션의 snapshot 생성 중 lead SessionStart prune이 creating 기록을 missing으로 닫을 수 있다. worktree add가 실패하면 같은 키 재시도가 거부된다. 성공하면 active로 회복된다. | 미해결, 후속 |
| 3 | [버그] low | `flow_gate.py:43` | 추정 목록 밖의 Orca 기계 알림은 사람 턴으로 세어진다. 지표만 부풀고 작업은 막지 않는다. shortcut 주석이 있다. | 미해결, 실제 세션 확인 뒤 보정 |
| 4 | [버그] low | `tests/stabilization.py` | 검증 보고서에 원인을 모르는 1회 실패가 있다(2회 재통과). 간헐 실패 원인이 남았다. | 미해결, 후속 |
| 5 | [nit] low | `.fullops-squad/handovers/to_dev.md` | 부모 체크 항목 미체크, `## 완료 보고` 비어 있음, 줄 수 741/744/745 불일치(기록 커밋 차이). 판정 영향 없음. | work.py finish 때 정리 |

nit은 1건이고 모두 findings에 적었다.

## 검증 및 남은 제약

- 재사용한 증거: `lint.json`(prepare가 dev 워크트리의 `fullops-gate/lint-result.json`에서 복사, head 8f11810, base 6a71d41, test_level lite, config_sha256 `63a6e3b5…`)과 snapshot 안의 `HARNESS-AUTONOMY-test/report.md`다. 지시대로 lint.py와 전체 시험은 다시 실행하지 않았다. lint의 test 명령 로그 경로는 `D:\workspace\Fullops-Squad-plugin\.git\worktrees\dev\fullops-gate\logs\`다. lint.json의 HEAD가 리뷰 SHA와 같아 동일 트리 결과로 본다. 환경 동일성은 자동 판정하지 않는다.
- 검증 보고서가 밝힌 미검증: 전체 `npm test`, 실제 Claude Code·Orca 세션의 StopFailure·사람 턴 기록, 현황판 브라우저 렌더, Codex·grok coordinator Stop, worker 워크트리에만 패킷이 있을 때의 배정 검사 전용 시험이 없다. 표적 시험 21개와 lint로 대체했다. 이 리뷰는 위 미검증이 수락을 막지 않는다고 판단한다. 다만 StopFailure와 사람 턴 기록은 실제 세션 확인 뒤 지표를 신뢰해야 한다.
- 시험 삭제·기대값 완화: 없다. `tests/check.py`·`caveman-start.py`·`product-routing.py`의 기대값 변경은 brief 문구 추가를 따른 것이다. `board.py` 시험의 JUMP-1 행 위치 변경은 템플릿 표 뒤에 안내문이 생긴 데 따른 것이다. 행을 파일 끝에 붙이는 스크립트는 없다.
- 남은 일: low 5건을 PLANS.md 후속으로 올린다. 기존 레포는 update-fullops로 PLANS 어휘·`## 위임 범위`·.gitignore를 받아야 한다(검증 보고서에 명시).

## 대화 미참조 인계 점검

| 확인 항목 | 정본 경로/절 | 결과(확인/미확인/해당 없음) | 누락·오래된 정보·후속 |
|---|---|---|---|
| 현재 요구와 결정 이유 | `handovers/to_dev.md` `현재 상황과 확인 근거`, PLANS.md HARNESS-AUTONOMY 행 | 확인 | 원인 분석 문서는 `local/`(gitignore)라 snapshot에 없다. 결정 요지는 지시서에 있어 인계에는 충분하다 |
| 구조와 구현/미완료 상태 | `to_dev.md` `해야 할 일과 파일 소유권`, `HARNESS-AUTONOMY-test/report.md` `동작이 바뀌는 점` | 확인 | 부모 체크 항목 미체크(finding 5) |
| 실행·검증 방법과 증거 | test report `결과`·`못 한 검증과 한계`, 이 폴더의 `lint.json` | 확인 | 없음 |
| 운영·복구(해당 시) | fullops-orca 스킬의 한도 재배정·`integration.py settle`, fullops-review 스킬의 재시도 절 | 확인 | 없음 |
| 다음 작업·담당·재개 조건 | PLANS.md 행 "push·PR·릴리스·jevpet 적용은 승인 대기" | 확인 | 리뷰 수락 뒤 사용자 승인 필요 |
| 로컬 링크·절 접근/지원 한계 | PLANS 행의 report 링크, to_dev.md `먼저 읽을 문서` | 확인 | `local/harness-cause-and-plan.md`는 커밋되지 않아 다른 체크아웃에서 열 수 없다 |
| snapshot 정리 후 정본 접근 | 기록 체크아웃 `qa-reports/HARNESS-AUTONOMY-review/` | 확인 | 결과는 snapshot 밖에 있다 |

## 검토 결론

수락 가능하다. critical 0, high 0, medium 0, low 5(nit 1 포함)다. 사용자 결정에 어긋나는 완화를 찾지 못했다. 세션을 가두거나 오류로 작업을 막는 hook 경로, 병합되지 않은 SHA의 hold 해제, lead Stop 대기 행 오판도 찾지 못했다. 미해결 medium은 없다. low 4건과 nit은 PLANS.md 후속으로 남긴다. `review.py check` 통과는 기록 검사이며 이 판단의 내용이나 시험 성공을 자동 보증하지 않는다.
