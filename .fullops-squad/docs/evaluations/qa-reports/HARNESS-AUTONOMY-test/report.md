---
title: HARNESS-AUTONOMY 검증 보고
status: draft
updated: 2026-11-10
owner: dev
tasks: [HARNESS-AUTONOMY]
summary: "사람 개입을 줄이는 하네스 개선 1~5단계의 시험·lint 결과, 동작 변경, 못 한 검증"
---

# HARNESS-AUTONOMY 검증 보고

테스트 레벨은 lite다. 기준은 main 6a71d41, 구현 커밋은 71772b2(1단계), bd8c67c(2~3단계), a56b095(4~5단계), 3979644(시험 표기)다.

## 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| 표적 시험 | `python3 tests/<이름>.py` 21개, `node tests/standard.cjs`, `node --test tests/npm-installer.cjs` | 모두 종료코드 0 |
| gate lint | `lint.py --repo . --from 6a71d41` | `head 397964441f30 / 파일 37 / ERROR 0 / WARNING 16 / 실행 불가 0` |
| 리뷰 필요 | `review.py need` | required, ask: 코드 23개 파일 744줄 |

- 시험: flow-gate, board, flow-state, integration-gate, jev-packet, jev-route, issue-mode, review-check, operating-policy, stabilization, product-routing, session-regressions, handover-rules, decision, delegation, done-gate, flow-graph, check, common-rules, caveman-start, setup-scope.
- 단계 묶음마다 반박 리뷰 Workflow를 돌렸다. 1단계 medium 1, 2~3단계 high 1·medium 1, 4~5단계 medium 2를 모두 고쳤다. low 7건 중 4건을 고쳤다.
- lint WARNING 16: SIZE-001 11건, SIZE-002(추가 741줄, 예상 230줄. 시험이 절반이다), SLOP-003 4건(hook이 오류로 작업을 막지 않게 넓게 잡은 예외, 사유 주석 있음).
- `stabilization.py`가 1회 실패했고 원인을 찾지 못했다. 같은 트리에서 종료코드 0으로 2회 다시 통과했다.

## 동작이 바뀌는 점(다음 릴리스 노트 원천)

- lead 세션의 사람 입력 시각을 기록해 현황판에 `과제당 사람 턴`, `사람 없이 이어진 배정`을 낸다. 본문은 저장하지 않는다.
- 통합 판정에 원격 기본 브랜치를 본다. 병합된 SHA의 hold는 풀고 사유를 `released_hold`에 남긴다. `integration.py settle`.
- 되돌릴 수 있는 디자인·연출·문구·배치 선택과 버그 수정 여부는 묻지 않고 정한다. 운영 배포·부하 테스트·backfill·운영 데이터 정리는 항상 사용자 승인이다.
- PLANS 표의 `대기` 행이 준비되면 lead Stop을 한 번 막고 배정하게 한다. `대기(…)`는 사람 대기, `보류(…)`는 보류다.
- 탐색 패킷은 선택이다. 패킷이 있는 과제는 전과 같이 검사한다.
- 이슈 모드가 꺼져 있으면 보류 잡이 무관한 worker를 Orca 조회에 묶지 않는다.
- API 오류로 끝난 dispatched worker가 coordinator에 escalation을 한 번 보낸다(StopFailure hook).
- 실패하고 아무것도 남기지 않은 리뷰 snapshot·prepare는 같은 키로 다시 한다. 정리된 수락 리뷰로 `issue_mode complete`가 통과한다.
- 기존 레포는 PLANS 상태 어휘, `## 위임 범위`, `.gitignore` 두 줄을 update-fullops로 받아야 한다.

## 못 한 검증과 한계

- 전체 `npm test`는 돌리지 않았다(표적 검증 지시).
- StopFailure hook과 사람 턴 기록은 실제 Claude Code·Orca 세션에서 확인하지 않았다. 기계 알림을 가르는 문구 목록은 추정이다.
- 현황판 화면은 브라우저로 렌더하지 않았다(Playwright 없음).
- Codex·grok coordinator의 Stop 동작, worker 워크트리에만 패킷이 있을 때의 배정 검사는 전용 시험이 없다.
- 두 지표의 실제 변화는 jevpet 적용 뒤에 잰다. jevpet은 수정하지 않았다.
