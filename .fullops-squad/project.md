---
title: 프로젝트 설정
status: draft
updated: 2026-10-27
owner: dev
summary: 프로젝트 설정
---

# 프로젝트 설정

setup에서 이 레포를 직접 확인하고 채운다. 원본 템플릿의 기술 스택·remote를 상속하지 않는다.

| 항목 | 값 |
|---|---|
| 제품 목적 | Codex·Claude Code·grok용 FullOps Squad 플러그인 (README.md) |
| 기본 브랜치 | main (origin = github.com/tourbut/Fullops-Squad-plugin, 공개) |
| 기술 스택·아키텍처 정본 | Python 3 스크립트·Markdown 스킬, Node 설치기. 정본 [AGENTS.md](../AGENTS.md), [docs/development.md](../docs/development.md). `plugins/fullops-squad/`·`adapters/`만 편집하고 `python3 scripts/build.py`로 `dist/` 재생성 |
| 공통 개발 기준 | [rules/common/README.md](rules/common/README.md) — `fullops-common-0.3.7` |
| 보안·코딩 규칙 | 공통 규칙. dist는 손으로 고치지 않는다 |
| 테스트·린트·빌드 명령 | 루트에서 `npm test`(PYTHONUTF8=1, 약 10분+), 변경 경로별 `python3 tests/<이름>.py`. 빌드 `python3 scripts/build.py` 후 CRLF 전용 dist 차이 복구. lint 명령은 `lint/lint.json` |
| 문서 언어 | 한국어 |

개발 문서 기본 경로는 `.fullops-squad/docs/`다. 기존 정본이 있으면 이동·복제하지 말고 아래 매핑과 산출물 인덱스를 해당 경로로 갱신한다.
외부 스킬의 `docs/agents/`는 이 레포에서 `.fullops-squad/docs/agents/`를 가리킨다.

## 작업 검증

변경이 동작하는지 보일 때 먼저 쓰는 명령이다. 지시서의 `증명 방법`이 따로 정하지 않으면 이 명령을 쓴다. 현재 `test_level`(lite)에서 실제로 도는 명령이다. 바뀐 경로에 해당하는 시험을 함께 실행한다. `npm test`는 `level: full`이라 lite에서 skipped된다.

| 항목 | 값 |
|---|---|
| 명령과 실행 위치 | 커밋 뒤 레포 루트에서 `python3 plugins/fullops-squad/scripts/lint.py --repo . --from main` |
| 기대 출력 | 종료코드 0, 마지막 줄의 `ERROR 0`과 `실행 불가 0`. 예: `head f86bb4aea2bb / 파일 14 / ERROR 0 / WARNING 0 / 실행 불가 0` |

## 주요 흐름

통합 후보마다 다시 돌리는 고정 세트다. 사용자가 처음부터 끝까지 거치는 핵심 흐름과 결함에서 온 재현 흐름을 적고, 실제로 돌려 본 흐름만 올린다. `실행 수단`은 명령, 시나리오 경로, 재실행 절차 문서 경로 중 하나다. 10개를 넘으면 담당이 빼거나 합칠 흐름을 개선 목록에 적는다.

| 흐름 | 실행 수단 |
|---|---|

## 자주 틀리는 것

같은 실수가 두 번째 나오면 `실수 → 올바른 방법 (근거 링크)` 한 줄을 여기에 추가한다. 첫 발생은 `contexts/<역할>.md`의 교훈으로 남기고, 두 번째인지는 거기서 판단한다. 정규식으로 잡을 수 있는 실수는 `lint/lint.json`의 `rules`로 옮기도록 제안한다.

- Orca `task-list`·`worker-list`·`run-current`·`run-show`를 `--full` 없이 읽는다 → 기본 응답에는 `run`·`spec`·`count`·`page`가 없으므로 `--full`을 붙인다. 시험 대역도 실제 `--full` 응답 모양을 따른다 ([CLEANUP-FOLLOWUPS 1·2차 리뷰](docs/evaluations/qa-reports/CLEANUP-FOLLOWUPS-test/report.md)).

## 공통 기준의 적용과 예외

공통 규칙은 기존 정본이 없는 부분의 기본값이다. 언어 관례·아키텍처·테스트 종류·커버리지는 실제 프로젝트 기준에 연결하고 기존 요구 수준을 낮추지 않는다. 보안·권한·리뷰 수락 기준은 임의 완화하지 않는다.

규칙 충돌과 승인된 예외는 항목·이유·적용 범위·승인 근거를 기록한다. 작업 지시서에는 이번 과제에서 사용하는 문서 경로와 기준 커밋 또는 스냅샷을 적는다. 규칙 개정은 사용자 수정본과 차이를 검토한 뒤 명시적으로 반영한다.

## 이 레포의 FullOps 적용 (dogfooding)

이 레포도 FullOps로 개발한다. `.fullops-squad/`는 플러그인 소스가 아니며 `scripts/build.py` 패키지에 들어가지 않는다. 배포 템플릿은 `plugins/fullops-squad/assets/repository/.fullops-squad/`가 정본이다.
hook은 설치된 릴리스 버전에서 실행된다. hook이 개발을 막으면 체크아웃 빌드(`docs/development.md`)로 띄우거나 플러그인을 끄고 원인을 고친다.

## 검증 명령 결과 (2026-10-27)

| name | run | 결과 |
|---|---|---|
| full | `npm test` | exit 0 (v1.11.0 릴리스 직전 같은 트리) |
| issue-mode | `python3 tests/issue-mode.py` | exit 0 |
| jev-route | `python3 tests/jev-route.py` | exit 0 |
| flow-gate | `python3 tests/flow-gate.py` | exit 0 |
| lint-gate | `python3 tests/lint.py` | exit 0 |
| packaging | `node tests/standard.cjs` | exit 0 |
