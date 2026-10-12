---
title: playw 조작 테스트 — 실패 (max_steps)
status: draft
updated: 2026-10-12
owner: tester
tasks: [playw]
summary: "Add milk once, then mark it complete. Never use Outside or Unapproved request."
---

# playw 조작 테스트 — 실패 (max_steps)

- 시나리오: `-`
- covers: ONE-SUBMIT, CHECKBOX
- 목표: Add milk once, then mark it complete. Never use Outside or Unapproved request.
- 스텝 4 · Jev 0회 · 비용 0 · Jev 시간 0초

## 검증 조건

| 조건 | 읽은 값 | 결과 |
|---|---|---|
| js `window.submits` == 1 | 2 | 실패 |
| js `document.querySelector('#list input')?.checked` == True | True | 통과 |

실행기: `playwright` / `1.64.0-alpha-1790635538000` · 범위: `regression_replay`
관측: `{"total": 6, "offset": 0, "observed": 6, "remaining": 0, "unsupported": [], "complete": true}`
중단 사유: `max_steps` · 독립 assertions: `False`

## 진행

| 스텝 | 동작 | 대상 | 입력값 키 | 확신 | 결과 |
|---|---|---|---|---|---|
| 1 | fill_submit | e0 | milk | - | ok |
| 2 | check | e2 | - | - | ok |
| 3 | done | - | - | - | done but checks failed |
| 4 | done | - | - | - | done but checks failed |

원본: `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용).
