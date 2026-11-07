---
title: LINT-BATCH-READ 검증 보고
status: draft
updated: 2026-11-07
owner: dev
tasks: [LINT-BATCH-READ]
summary: "lint 일괄 읽기의 검사 결과, 내용 비교, 측정값, 한계"
---

# LINT-BATCH-READ 검증 보고

대상은 `fullops/dev` 241b7c4다. 기준은 main 0f918bb다. 테스트 레벨은 lite다.

## 통과한 검사

- `lint.py --from 0f918bb`, dev 워크트리, 241b7c4: 종료코드 0, ERROR 0, WARNING 4, 실행 불가 0. issue-mode·flow-gate·lint-gate·packaging이 통과했다.
- 내용 비교: `99e7b50..446856f`(경로 1,551개, 읽기 612건, 6.2MB)에서 새 읽기와 파일별 읽기의 결과가 같다.

## 측정

| 방식 | git 호출 | 시간 |
|---|---|---|
| 파일별 `git cat-file blob` | 612회 | 46.50초 |
| `git cat-file --batch -Z` | 1회 | 1.69초 |

측정은 파일 읽기만 잰다. 검사 규칙 시간과 시험 명령 시간은 포함하지 않는다.

## 못 한 검증과 한계

- `-Z`는 Git 2.41 이상이 필요하다. README의 필요 환경과 같다. 더 낮은 Git은 lint 실패로 끝난다.
- 서브모듈 경로는 이전처럼 lint 실패로 끝난다. CLEANUP-FOLLOWUPS의 `lint 서브모듈` 항목에서 다룬다.
- `build.py`가 `dist/native` 교체 중 `WinError 5`로 한 번 실패했다. 다시 실행해 통과했다. 원인은 확인하지 못했다.
- WARNING 4건은 SIZE-001이다. 분할은 이 과제 범위가 아니다.
