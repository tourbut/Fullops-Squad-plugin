---
title: playw 조작 테스트 — 실패 (replay_target_missing_or_ambiguous)
status: draft
updated: 2026-10-13
owner: tester
tasks: [playw]
summary: "Select dark theme, add milk exactly once, then click its checkbox exactly once. Do not load, clear, retry, navigate or change anything else. Finish after those actions even if the fixture is defective."
---

# playw 조작 테스트 — 실패 (replay_target_missing_or_ambiguous)

- 시나리오: `-`
- covers: DARK, ONE-SUBMIT, ONE-MILK, CHECKED
- 목표: Select dark theme, add milk exactly once, then click its checkbox exactly once. Do not load, clear, retry, navigate or change anything else. Finish after those actions even if the fixture is defective.
- 스텝 2 · Jev 0회 · 비용 0 · Jev 시간 0초

## 검증 조건

| 조건 | 읽은 값 | 결과 |
|---|---|---|
| - | - | 판정 전에 끝남 |

실행기: `playwright` / `1.64.0-alpha-1790635538000` · 범위: `regression_replay`
관측: `{"total": 11, "offset": 0, "observed": 11, "remaining": 0, "unsupported": ["custom_or_select_widgets"], "complete": false}`
중단 사유: `replay_target_missing_or_ambiguous` · 독립 assertions: `False`

## 진행

| 스텝 | 동작 | 대상 | 입력값 키 | 확신 | 결과 |
|---|---|---|---|---|---|
| 1 | click | e0 | - | - | ok |
| 2 | fill_submit | e1 | milk | - | ok |

원본: `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용).
