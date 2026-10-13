---
title: playw 조작 테스트 — 실패 (error)
status: draft
updated: 2026-10-13
owner: tester
tasks: [playw]
summary: "Click Dark theme once. Fill New todo with milk without Enter, click Add exactly once, then click Toggle milk exactly once. Finish. Do not load, clear, retry, navigate or change anything else."
---

# playw 조작 테스트 — 실패 (error)

- 시나리오: `-`
- covers: DARK, ONE-SUBMIT, ONE-MILK, CHECKED
- 목표: Click Dark theme once. Fill New todo with milk without Enter, click Add exactly once, then click Toggle milk exactly once. Finish. Do not load, clear, retry, navigate or change anything else.
- 스텝 3 · Jev 0회 · 비용 0 · Jev 시간 0초

## 검증 조건

| 조건 | 읽은 값 | 결과 |
|---|---|---|
| - | - | 판정 전에 끝남 |

오류: RuntimeError / execution stopped before final evidence

실행기: `playwright` / `1.63.0` · 범위: `regression_replay`
관측: `{"total": 10, "offset": 0, "observed": 10, "remaining": 0, "unsupported": ["custom_or_select_widgets"], "complete": false}`
중단 사유: `error` · 독립 assertions: `False`

## 진행

| 스텝 | 동작 | 대상 | 입력값 키 | 확신 | 결과 |
|---|---|---|---|---|---|
| 1 | click | e0 | - | - | ok |
| 2 | fill | e1 | milk | - | ok |
| 3 | click | e2 | - | - | ok |

원본: `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용).
