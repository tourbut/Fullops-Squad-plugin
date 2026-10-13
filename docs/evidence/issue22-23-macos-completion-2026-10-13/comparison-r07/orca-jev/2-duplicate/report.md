---
title: orc 조작 테스트 — 실패 (max_steps)
status: draft
updated: 2026-10-13
owner: tester
tasks: [orc]
summary: "Select dark theme, add milk exactly once, then click its checkbox exactly once. Do not load, clear, retry, navigate or change anything else. Finish after those actions even if the fixture is defective."
---

# orc 조작 테스트 — 실패 (max_steps)

- 시나리오: `-`
- covers: DARK, ONE-SUBMIT, ONE-MILK, CHECKED
- 목표: Select dark theme, add milk exactly once, then click its checkbox exactly once. Do not load, clear, retry, navigate or change anything else. Finish after those actions even if the fixture is defective.
- 스텝 5 · Jev 5회 · 비용 0.000405 · Jev 시간 2.231초

## 검증 조건

| 조건 | 읽은 값 | 결과 |
|---|---|---|
| js `document.documentElement.dataset.theme` == dark | dark | 통과 |
| js `window.submits` == 1 | 2 | 실패 |
| js `document.querySelectorAll('#list li').length` == 1 | 2 | 실패 |
| js `document.querySelector('#list li')?.textContent.trim()` == milk | milk | 통과 |
| js `document.querySelector('#list input')?.checked` == True | True | 통과 |

실행기: `orca` / `unverified` · 범위: `scenario_checks`
관측: `{"total": 14, "offset": 0, "observed": 14, "remaining": 0, "unsupported": ["custom_or_select_widgets"], "complete": false}`
중단 사유: `max_steps` · 독립 assertions: `False`

## 진행

| 스텝 | 동작 | 대상 | 입력값 키 | 확신 | 결과 |
|---|---|---|---|---|---|
| 1 | click | e2 | - | 0.88 | ok |
| 2 | fill_submit | e9 | milk | 0.77 | ok |
| 3 | check | e10 | - | 0.92 | ok |
| 4 | done | - | - | 0.91 | done but checks failed |
| 5 | done | - | - | 0.61 | done but checks failed |

원본: `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용).
