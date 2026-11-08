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

- `lint.py --from main`, dev 워크트리, f86bb4a: 종료코드 0, ERROR 0, WARNING 0, 실행 불가 0.
- `python tests/common-rules.py`, f86bb4a: 종료코드 0.
- `python tests/delegation.py`, f86bb4a: 종료코드 0.
- `npm test`, 8c5c015에 문구 수정이 얹힌 작업 트리: 종료코드 0.
- `review.py need`: skip(코드 2개 파일 8줄).

```text
head f86bb4aea2bb / 파일 14 / ERROR 0 / WARNING 0 / 실행 불가 0
```

## verifier 실제 실행

이 레포를 `subagent_level: lite`로 바꾼 뒤(결정 D021) 새 절차대로 호스트 서브에이전트를 1회 실행했다.

- 첫 지시문은 PreToolUse hook이 거부했다. 예시로 인용한 수정 지시 문구가 lite 검사에 걸렸다. 그래서 거부되는 표현을 `delegation.md`에 정확히 적었다(a6dcf19).
- 예시 문구를 뺀 지시문은 hook을 통과했다.
- 결과: 시험 2개 통과, 새 setup 레포에 새 절 3개 생성, lite 검사의 거부·허용 사례 확인. `git status`는 깨끗했다.
- `lint.py` 대조에서 찾은 빈틈 3건 중 2건(출력이나 결과 파일이 없는 경우)은 `fullops-work`에 반영했다(f86bb4a). 1건은 아래 한계에 적었다.

## 못 한 검증과 한계

- `npm test`는 a6dcf19·f86bb4a의 문구 수정 2건 전에 돌았다. 두 커밋은 문서와 그 dist 사본만 바꿨다. 관련 시험 2개만 f86bb4a에서 다시 돌렸다.
- verifier의 1번 시험은 8c5c015에 문구 수정이 얹힌 상태, 2·3번은 a6dcf19에서 돌았다.
- standard 이상의 기본 실행(인접 흐름 2개)은 실제로 돌리지 않았다. 이 레포는 lite다.
- 완료 보고의 출력 발췌는 실제 worker 인박스에서 쓰지 않았다.
- `lint-result.json`의 `head`는 lint 뒤 기록 커밋이 있으면 완료 SHA보다 오래될 수 있다. 문서에 적지 않았다.
