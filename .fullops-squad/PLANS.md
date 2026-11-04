---
title: 현재 작업
status: draft
updated: 2026-11-04
owner: dev
summary: 현재 작업
---

# 현재 작업

진행 상태와 우선순위의 정본이다. 작업 명세는 handovers, 상세 이력은 logs에 둔다.

| 과제 키 | 목표 | 담당 | 상태 | 지시서·원천 링크 |
|---|---|---|---|---|
| ISSUE-SLASH-SIDEBAR | 이슈 자동 모드 슬래시 명령 인자, fullops-meter footer·pane에 ON/OFF 표시 | dev(직접) | 구현·lint 완료, 1.12.0(fullops-meter 0.11.0)으로 릴리스. 기준 7187d08 | `feat/issue-mode-sidebar` |
| ISSUE-HELD-QUESTION | 사용자 결정 보류를 이슈 댓글 질문으로 옮기고 사이드바 현재 이슈 선택 수정 | dev(직접) | 구현·lint·CI 완료, PR #114 병합(2911c36), 1.12.1 릴리스. 기준 8896129. jevpet 모니터링에서 #1·#35 보류에 이슈 댓글이 없던 것이 근거 | `fix/issue-mode-held-question` |
| LINT-GATE-SCOPE | done-gate 재실행 조건 축소: 정확한 --from 안내, 같은 트리·계획/현황판 기록 커밋 인정, dev 직접 기준을 원격 기본 브랜치 merge-base로 | dev(직접) | 구현·테스트, 1.13.0 릴리스 대상. 기준 9cb771b. 근거: 이번 세션 flow-gate 132초 반복·병합 커밋 재lint | `fix/lint-gate-scope` |
| ISSUE-PR-FOLLOWUP | draft PR 실패 check·수정 요청 리뷰를 새 attempt로, 병합된 이슈 브랜치·워크트리 `prune` | dev(직접) | 구현·테스트, 1.13.0 릴리스 대상. 근거: PR #113 CI 실패, 10-29 병합 브랜치 33개 수동 정리 | `fix/lint-gate-scope` |
| GH-1369701248-109-A1 | 이슈 #109 checkpoint --received 예시 | dev | 배정 안 함: 구현 전 작성자 질문(f3c5d022…)이 필요했고 답변 뒤 새 attempt A2로 대체됨 | https://github.com/tourbut/Fullops-Squad-plugin/issues/109 |
| GH-1369701248-109-A2 | 같은 이슈, 답변 B 반영 | dev | 배정 완료(task_e803a1de7619/ctx_2282a0bcc3dd), failed: push hook 거부, A3로 대체. 지시서·route는 브랜치 `fullops/issue-109-a2` | `fullops/issue-109-a2` d6a40eb |
| GH-1369701248-109-A3 | 같은 이슈, dist 사본 포함 | dev | 배정 완료(task_baddb9300a28/ctx_362d15e01cf9), completed. draft PR #110은 2026-11-04 사용자 결정으로 병합 없이 닫고 브랜치 삭제 | https://github.com/tourbut/Fullops-Squad-plugin/pull/110 |
| NOTIFY-FULLO-RELAY | main push·이슈 이벤트를 Fullo webhook으로 전달하는 CI 워크플로 | dev(직접) | PR #123 병합(11e5ab9, 완료 SHA 80faa21). 리뷰 need: skip(코드 0개 파일). lint 결과 재사용(base dfcb440, 적용 검사 없음). 원격 main push 후 notify-fullo 실행 결과 확인 | https://github.com/tourbut/Fullops-Squad-plugin/pull/123 |
| REPO-CLEANUP | 전체 코드 정리, 불필요 파일 삭제, 로직 점검·리팩토링 | dev(직접) | 진행 중. 기준 7189354, 브랜치 `chore/repo-cleanup`. 감사 16개 모듈에서 발견 213건(검증 50건, 반박 0건). 검증 단계는 시간 과다로 중단하고 소유 파일별 적용으로 전환. 결정 D001: 이슈 #22·#23 증거 묶음은 고정 링크로 바꾸고 삭제. D002: 로컬 미추적 잔여물 삭제(완료). 완료 조건: dist 재생성 일치, 전체 npm test 통과, HEAD lint ERROR 0, review need 판정 처리 | `chore/repo-cleanup` |
| AUTONOMY-SHADOW | #125 1단계(섀도 판정기·이벤트·결정 형식)와 2단계의 이 레포 몫(결정 SHA·만료·응답자 확인, 늦은 답 already, merge 절차) | dev(직접) | 구현·테스트 완료. 기준 35de341(REPO-CLEANUP 위에 쌓음), 브랜치 `feat/autonomy-shadow`. 섀도 모드라 기존 병합 동작은 그대로다. 3단계(auto·delay 개방)는 섀도 결과를 검토한 뒤 사용자와 정한다. orca-helm·봇 설정은 다른 저장소 몫 | https://github.com/tourbut/Fullops-Squad-plugin/issues/125 |
