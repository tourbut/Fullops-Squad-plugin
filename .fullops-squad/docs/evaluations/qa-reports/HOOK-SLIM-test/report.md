---
title: HOOK-SLIM 검증 보고
status: draft
updated: 2026-11-07
owner: dev
tasks: [HOOK-SLIM]
summary: "hook 시간 단축의 전후 측정값, 검사 결과, 한계"
---

# HOOK-SLIM 검증 보고

대상은 `fullops/dev` d029a21이다. 기준은 main 0f918bb다. 테스트 레벨은 lite다.

## 통과한 검사

- `npm test`, dev 워크트리, d029a21과 같은 작업 트리: 종료코드 0.
- `lint.py --from 0f918bb`, dev 워크트리, d029a21: 종료코드 0, ERROR 0, WARNING 4, 실행 불가 0.

## 측정

대상 레포는 이 저장소다. 소스 hook을 9회씩 실행한 중앙값이다. 도구 호출마다 tool과 post가 함께 돈다.

| hook | 전(12d7f8b) | 후(d029a21) |
|---|---|---|
| flow tool, Bash | 약 1,000ms | 약 530ms |
| flow post, Bash | 약 1,100ms | 약 500ms |
| flow prompt | 약 700ms | 약 340~420ms |
| flow stop | 약 1,700ms | 약 730ms |
| done stop | 약 520ms | 약 340~440ms |
| flow tool, FullOps가 아닌 레포 | 약 235ms | 약 190~280ms |

git 프로세스는 도구 hook 호출당 13~14개에서 5개로 줄었다. 부수 효과로 lint의 flow-gate 시험은 137.9초에서 74.4초로, issue-mode 시험은 28.7초에서 9.6초로 줄었다.

## 못 한 검증과 한계

- 측정값은 이 PC 한 대의 값이다. 다른 프로세스 부하로 흔들린다. FullOps가 아닌 레포의 차이는 오차 범위다.
- 자동 이슈 상태 파일이 이 저장소에 있어 `issue_mode` 생략 효과는 측정에 포함되지 않았다.
- `policy.identity`의 `symbolic-ref`는 도구 hook에서 2회 남아 있다. 값이 HEAD에 따라 바뀌어 캐시하지 않았다.
- 현황판의 이슈 목록은 Stop 경로에서 최대 5분 늦을 수 있다. `board.py`를 직접 실행하면 즉시 조회한다.
- 설치된 hook은 다음 플러그인 갱신 전까지 이전 코드로 돈다. 측정은 소스 파일을 직접 실행했다.
