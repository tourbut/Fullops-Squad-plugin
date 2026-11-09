---
title: OUTPUT-HISTORY-A 검증 보고
status: draft
updated: 2026-11-09
owner: dev
tasks: [OUTPUT-HISTORY-A]
summary: "#104 후보 A(긴 Bash 출력 줄이기)의 표적 시험, 실제 Claude Code 확인, 한계"
---

# OUTPUT-HISTORY-A 검증 보고

테스트 레벨은 lite다. 기준은 origin/main 34a86aa다.

## 결과

- `tests/output-trim.py`: OK. 그대로 두는 경우, 원문 저장, 오류 줄 유지, 슬롯 상한, `flow_gate post` 연결, 작업 트리 깨끗함을 확인한다.
- 실제 Claude Code 2.1.319 `-p` 1회, 1,000줄 출력: 원문 9,888자, 모델이 받은 tool_result 1,572자. 모델은 `line 0`과 `line 999`를 받았고 `line 500`은 받지 못했다고 답했다. 실제 응답 필드는 `stdout`·`stderr`·`interrupted`·`isImage`·`noOutputExpected`다.
- 문서: `updatedToolOutput`은 내장 도구에 쓸 수 있고 형식이 다르면 무시된다.

## 못 한 검증과 한계

- 절감량은 재지 않았다. 시험 1회의 수치는 일부러 만든 출력이다.
- 시험 세션은 작업 트리가 커밋 전이라 done-gate Stop에 막혀 150초 제한까지 턴을 더 썼다. 기능과는 무관하다.
- PowerShell 도구, Codex, grok은 대상이 아니다. 이들의 응답 형식은 확인하지 않았다.
- 원문을 다시 읽는 빈도, `git diff`처럼 전체가 필요한 명령에 미치는 영향은 실제 작업에서 보지 않았다.
