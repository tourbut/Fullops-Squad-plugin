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
| 공통 개발 기준 | [rules/common/README.md](rules/common/README.md) — `fullops-common-0.3.6` |
| 보안·코딩 규칙 | 공통 규칙. dist는 손으로 고치지 않는다 |
| 테스트·린트·빌드 명령 | 루트에서 `npm test`(PYTHONUTF8=1, 약 10분+), 변경 경로별 `python3 tests/<이름>.py`. 빌드 `python3 scripts/build.py` 후 CRLF 전용 dist 차이 복구. lint 명령은 `lint/lint.json` |
| 문서 언어 | 한국어 |

개발 문서 기본 경로는 `.fullops-squad/docs/`다. 기존 정본이 있으면 이동·복제하지 말고 아래 매핑과 산출물 인덱스를 해당 경로로 갱신한다.
외부 스킬의 `docs/agents/`는 이 레포에서 `.fullops-squad/docs/agents/`를 가리킨다.

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
