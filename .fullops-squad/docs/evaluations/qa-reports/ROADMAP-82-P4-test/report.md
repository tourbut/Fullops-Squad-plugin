---
title: ROADMAP-82-P4 검증 보고
status: draft
updated: 2026-11-09
owner: dev
tasks: [ROADMAP-82-P4]
summary: "#82 P4(주요 흐름 고정 세트, 통합 후보 기본값, 결함 범위)의 검사 결과, 반박 검증 처리, 한계"
---

# ROADMAP-82-P4 검증 보고

대상은 `fullops/dev` 7cf3736이다. 기준은 origin/main fb48669다. 이 체크아웃의 로컬 `main`은 뒤처져 있어 쓰지 않았다. 테스트 레벨은 lite다.

## 통과한 검사

- `lint.py --from origin/main`, 7cf3736: 종료코드 0, `head 7cf3736c1562 / 파일 12 / ERROR 0 / WARNING 0 / 실행 불가 0`.
- `tests/common-rules.py`·`flow-graph.py`·`operating-policy.py`·`update.py`, 7cf3736 커밋 전 작업 트리: 모두 OK.
- `npm test`, d8c6f60: 종료코드 0.
- `review.py need`, d8c6f60: skip(코드 2개 파일 5줄). 7cf3736은 코드를 바꾸지 않았다.

## 사용자 결정과 기본값

결정 D026(세트 정본은 `project.md` 표), D027(소프트 상한 10), D028(세트에는 흐름·재발 결함만), D029(플레이북 eval 원뜻은 미반영 명시)다. 실행 수단 혼합과 통합 후보 경계는 기본값으로 고지했다. minimal 담당은 `coordinator`로 고지했으나 dev 모드에 없어 `병합 책임자`로 바꿨다.

## 반박 검증

- 1차(3772804, 관점 3개): 규칙 모순, 문구 추적, 릴리스 노트와 적용 절차를 봤다. `dist` 미갱신(high)과 따라 할 수 없는 문구를 d8c6f60에 반영했다.
- 2차(d8c6f60, 1회): medium 2건, low 7건을 7cf3736에 반영했다. 빈 표에서 돌린 흐름을 올리는 문장이 빠진 것과, minimal의 품질 판단이 designer 차수로 이어지는 것이 medium이다.
- 적용 절차: 1차 검증의 임시 복사본(버전 1.20.0 가정)에서 `update.py --verify`가 적용 전 0/3, 적용 뒤 3/3이었다. 필수 적용 문구는 7cf3736에도 그대로 있다.

반영하지 않은 지적은 PLANS.md의 `ROADMAP-82-P4 후속`에 적었다.

## 못 한 검증과 한계

- `npm test`는 7cf3736 전에 돌았다. 7cf3736은 문서와 `dist` 사본만 바꿨다.
- 7cf3736의 문구는 다시 반박 검증하지 않았다.
- 실제 Orca 세션에서 큰 틀 검수를 배정하거나 세트를 돌리지 않았다. 레벨별 동작은 문구 추적이다. `lint.py --level full --from`만 임시 레포에서 실행했다.
- 세트 1회의 비용과 시간은 측정하지 않았다. 고정 세트가 회귀를 더 잘 잡는다는 근거도 없다. 찾은 회귀 1건은 세트 없이 intent 기준으로 잡혔고, KL·JP 조사는 표본이다.
- `testing.md`의 `담당과 반복 범위` 37번 줄이 길어졌다. 줄 수 상한(60줄)에 1줄만 남아 같은 줄에 넣었다.
