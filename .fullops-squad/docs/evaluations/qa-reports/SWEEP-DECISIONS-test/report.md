---
title: SWEEP-DECISIONS 검증 보고
status: draft
updated: 2026-11-10
owner: dev
tasks: [SWEEP-DECISIONS]
summary: "REPO-SWEEP 감사의 사용자 결정 8건 반영 결과와 한계"
---

# SWEEP-DECISIONS 검증 보고

테스트 레벨은 lite다. 기준은 main c2ec335, 구현 커밋은 eb8f6f4다.

## 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| 해당 시험 | `python3 tests/<이름>.py` 14개, `node tests/standard.cjs` | 모두 종료코드 0 |
| gate lint | `lint.py --repo . --from c2ec335` | `head eb8f6f4e026d / 파일 18 / ERROR 0 / WARNING 3 / 실행 불가 0` |
| 리뷰 필요 | `review.py need` | skip: 코드 11개 파일 143줄 |

- 시험: caveman-start, handover-rules, jev-find, jev-context, autonomy, deps, issue-mode, stabilization, lint, check, setup-scope, search-index, product-routing, jev-packet.
- 지운 옵션 확인: `jev_find.py --handover`는 `unrecognized arguments`, `deps.py --prune-runtime --runtime-only`는 옵션 충돌 오류다.
- `--prune-runtime` 시험: 현재 사본만 남고 hook이 계속 실행된다. `current.json`을 읽을 수 없으면 아무것도 지우지 않는다.
- lint WARNING 3: LINT-001(`lint.json` 변경, 병합 뒤 적용), SIZE-001(`deps.py` 325줄, 1줄 증가), ANTI-005(`tests/handover-audit.py` 삭제, 사용자 결정).

## 못 한 검증과 한계

- 전체 `npm test`는 로컬에서 다시 돌리지 않았다. CI가 실행한다.
- 실제 사용자 홈의 런타임 사본은 지우지 않았다. 이 PC의 정리는 사용자가 세션을 닫고 실행한다.
- `issue_mode.py`에 예전 `--token <값>`을 주면 argparse 약어로 `--token-file`로 읽혀 lease 파일 경로 오류가 난다. 토큰으로는 쓰이지 않는다.
- packaging 경로를 좁혀 `adapters/`·`scripts/build.py` 변경은 로컬 lint에서 시험이 선택되지 않는다. dist 일치 검사는 CI에만 있다.
