---
title: 현재 작업
status: draft
updated: 2026-10-27
owner: dev
summary: 현재 작업
---

# 현재 작업

진행 상태와 우선순위의 정본이다. 작업 명세는 handovers, 상세 이력은 logs에 둔다.

| 과제 키 | 목표 | 담당 | 상태 | 지시서·원천 링크 |
|---|---|---|---|---|
| ISSUE-SLASH-SIDEBAR | 이슈 자동 모드 슬래시 명령 인자, fullops-meter footer·pane에 ON/OFF 표시 | dev(직접) | 구현·lint 완료, 1.12.0(fullops-meter 0.11.0)으로 릴리스. 기준 7187d08 | `feat/issue-mode-sidebar` |
| ISSUE-HELD-QUESTION | 사용자 결정 보류를 이슈 댓글 질문으로 옮기고 사이드바 현재 이슈 선택 수정 | dev(직접) | 구현·테스트, 1.12.1 릴리스 대상. 기준 8896129. jevpet 모니터링에서 #1·#35 보류에 이슈 댓글이 없던 것이 근거 | `fix/issue-mode-held-question` |
| GH-1369701248-109-A1 | 이슈 #109 checkpoint --received 예시 | dev | 배정 안 함: 구현 전 작성자 질문(f3c5d022…)이 필요했고 답변 뒤 새 attempt A2로 대체됨 | https://github.com/tourbut/Fullops-Squad-plugin/issues/109 |
| GH-1369701248-109-A2 | 같은 이슈, 답변 B 반영 | dev | 배정 완료(task_e803a1de7619/ctx_2282a0bcc3dd), failed: push hook 거부, A3로 대체. 지시서·route는 브랜치 `fullops/issue-109-a2` | `fullops/issue-109-a2` d6a40eb |
| GH-1369701248-109-A3 | 같은 이슈, dist 사본 포함 | dev | 배정 완료(task_baddb9300a28/ctx_362d15e01cf9), completed. draft PR #110, integration hold: main 병합은 사용자 판단 | https://github.com/tourbut/Fullops-Squad-plugin/pull/110 |