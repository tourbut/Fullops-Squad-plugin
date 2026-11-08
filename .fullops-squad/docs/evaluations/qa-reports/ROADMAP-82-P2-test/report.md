---
title: ROADMAP-82-P2 검증 보고
status: draft
updated: 2026-11-08
owner: dev
tasks: [ROADMAP-82-P2]
summary: "#82 P2(작업 검증·자주 틀리는 것·출력 발췌·verifier)의 검사 결과, verifier 실제 실행 결과, 한계"
---

# ROADMAP-82-P2 검증 보고

대상은 `fullops/dev` f86bb4a다. 기준은 main 20d2c96이다. 테스트 레벨은 lite다.

## 통과한 검사

- `lint.py --from main`, f86bb4a: 종료코드 0, `head f86bb4aea2bb / 파일 14 / ERROR 0 / WARNING 0 / 실행 불가 0`.
- `python tests/common-rules.py`·`python tests/delegation.py`, f86bb4a: 종료코드 0.
- `npm test`, 8c5c015에 문구 수정이 얹힌 작업 트리: 종료코드 0.
- `review.py need`: skip(코드 2개 파일 8줄).

## verifier 실제 실행

`subagent_level: lite`(결정 D021)에서 호스트 서브에이전트를 1회 실행했다.

- 첫 지시문은 hook이 거부했다. 예시로 인용한 수정 지시 문구가 lite 검사에 걸렸다. 거부되는 표현을 `delegation.md`에 적었다(a6dcf19).
- 결과: 시험 2개 통과, 새 setup 레포에 새 절 3개 생성, lite 검사의 거부·허용 확인, `git status` 깨끗함.
- `lint.py` 대조의 빈틈 3건 중 2건(출력이나 결과 파일이 없는 경우)을 `fullops-work`에 반영했다(f86bb4a).

## 못 한 검증과 한계

- `npm test`는 a6dcf19·f86bb4a 전에 돌았다. 두 커밋은 문서와 dist 사본만 바꿨다. verifier의 1번 시험도 a6dcf19 커밋 전이다.
- standard 이상의 기본 실행(인접 흐름 2개)과 worker 인박스의 출력 발췌는 실제로 돌리지 않았다.
- `lint-result.json`의 `head`는 lint 뒤 기록 커밋이 있으면 완료 SHA보다 오래될 수 있다. 문서에 적지 않았다.
