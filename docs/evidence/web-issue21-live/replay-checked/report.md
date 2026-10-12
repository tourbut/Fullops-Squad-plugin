---
title: web-issue21 조작 테스트 — 통과 (passed)
status: draft
updated: 2026-10-12
owner: tester
tasks: [web-issue21]
summary: "Verify the read-only Home demo and unauthenticated state. Never post, like, share, save, or enter credentials."
---

# web-issue21 조작 테스트 — 통과 (passed)

- 시나리오: `-`
- covers: HOME-STRUCTURE, DEMO-NO-WRITES, AUTH-EXPIRED-STATE, DESKTOP-OVERFLOW
- 목표: Verify the read-only Home demo and unauthenticated state. Never post, like, share, save, or enter credentials.
- 스텝 2 · Jev 0회 · 비용 0 · Jev 시간 0초

## 검증 조건

| 조건 | 읽은 값 | 결과 |
|---|---|---|
| js `location.pathname === '/home'` == True | True | 통과 |
| js `document.querySelector('main h1')?.textContent.trim() === 'Home'` == True | True | 통과 |
| js `document.querySelectorAll('main article').length` == 2 | 2 | 통과 |
| js `[...document.querySelectorAll('textarea,input')].some(e => (e.labels?.[0]?.textContent \|\| e.getAttribute('aria-label') \|\| '').includes('Pet의 소식') && e.disabled)` == True | True | 통과 |
| js `(() => {const controls=[...document.querySelectorAll('button')].filter(e => /^(게시\|Like\|Comment\|Share\|Save)$/.test(e.textContent.trim()));return controls.length >= 9 && controls.every(e => e.disabled);})()` == True | True | 통과 |
| 문구 "로그인이 만료됐습니다. 다시 로그인하세요."가 보여야 함 | True | 통과 |
| js `document.documentElement.scrollWidth <= innerWidth` == True | True | 통과 |

실행기: `orca` / `1.4.223` · 범위: `regression_replay`
관측: `{"total": 48, "offset": 0, "observed": 48, "remaining": 0, "unsupported": [], "complete": true}`
중단 사유: `passed` · 독립 assertions: `True`

## 진행

| 스텝 | 동작 | 대상 | 입력값 키 | 확신 | 결과 |
|---|---|---|---|---|---|
| 1 | scroll_down | - | - | - | ok |
| 2 | done | - | - | - | checks passed |

원본: `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용).
