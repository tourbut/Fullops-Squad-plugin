# 하네스 플러그인 이식 기록 — 2026-09-14

## 요구사항과 구현

원본: `/Users/mipd/workspace/FullOps-Squad`. 배포 대상: Codex·Claude Code·grok·agy.

| 요구사항 | 구현 |
|---|---|
| 설치 한 번으로 의존성 준비 | `scripts/install.py --host all`, 외부 출처는 `dependencies.json` |
| 선택한 레포에서만 활성화 | `setup-fullops`, 레포 루트 `.fullops-squad/fullops.json` 확인 |
| 코드 탐색 그래프 | `codebase-memory-mcp` 전역 실행 파일 + 플러그인별 MCP 선언 |
| worker 핸드오버 | 역할별 인박스·템플릿, 실제 지시서 가시성·착수 확인 |
| 부모에게 직접 완료 회신 | 지시서의 복귀 주소, 브랜치·SHA·검증·산출물 링크 |
| 작업 기록 보존 | logs 전문 append → 기록 확인 → 완료분만 인박스 제거 |
| 역할 지식 축적 | contexts 3줄 요약, 상세는 exec-plans/phases |
| 개발 산출물 관리 | D01–D13 원천 문서와 링크 기반 조립 인덱스 |
| 기존 서비스에 적용 | 기존 진입점 보존, 충돌 사전 검사, 재실행 시 누락 파일만 생성 |

## 원본에서 유지하거나 조정한 부분

핸드오버·컨텍스트·산출물 규약은 원본 `.agents/handovers/`, `skills/{handover,role-context,deliverable-docs}/`, `workflows/orca.md`를 검토해 이식했다.
서비스별 코드·실행 이력·remote·라벨은 패키지에서 제외하고 setup에서 실제 프로젝트 기준을 연결한다. 린터는 원본 `verify-linter-rules`(AgentBuilder 파생본)에서 스택 무관 검사(주석 제외 줄 수, 범위 없는 억제, eval/exec, 비밀값, 자가 확장 정규식 규칙)만 `scripts/lint.py`로 옮겼다. 파일명·import·레이어·Svelte 규칙은 제외하고, 레포의 기존 lint 도구를 `lint/lint.json`에 연결한다.
새 세션은 제목 변경과 구분하고, 다른 워크트리에서 지시서가 자동 공유된다고 가정하지 않는다.
이미 허가된 작업의 반복 승인 대신 실제 추가 권한이 필요한 행위를 지시서에 분리한다.

## 검증 결과

- `python3 tests/check.py`: 임시 레포의 격리, dry-run 무변경, CRLF 포함 기존 진입점 보존, 로그·진행 작업 보존, 재실행, 충돌·심볼릭 링크·잘못된 설정 거부, 호스트별 설치 계획 통과.
- 기존 호스트 marketplace 목록으로 중복 등록 생략을 확인했다. 전역 설치 상태는 수정하지 않았다.
- 임시 `CODEX_HOME`에서 로컬 marketplace 등록과 `fullops-squad@fullops-squad` 실제 설치 성공.
- 임시 `CLAUDE_CONFIG_DIR`에서 로컬 marketplace 등록 성공.
- Codex plugin-creator 검증기, 스킬 4종 quick_validate, Claude Code plugin/marketplace validate 통과.
- `git diff --check` 통과.

## 남은 통합 검증과 제약

전체 외부 의존성 다운로드 및 실제 모델 worker의 dispatch→report→merge는 실행하지 않았다.
호스트 설치 버튼만으로 두 환경의 외부 스킬까지 모두 설치되는 계약은 구현하지 않았다. 전체 설치는 통합 설치기가 담당하며, Claude의 두 플러그인 의존성은 네이티브 resolver를 사용한다.
기존 사용자 설치는 제거하지 않으므로 여러 출처의 같은 스킬이 이미 있으면 중복 정리가 필요하다.
외부 의존성은 upstream 최신 버전을 추적한다. 릴리즈 검증 후 버전 고정이 필요하면 각 upstream의 배포·태그 정책에 맞춰 추가한다.
원본 레포 전체 마이그레이션, 서비스별 스택 규칙 번들, 납품용 docx/pdf 변환기는 포함하지 않았다.

## grok·agy 추가

- grok은 로컬 플러그인 설치, agy는 루트 `plugin.json`을 추가해 로컬 플러그인 설치를 지원한다.
- 외부 의존성은 npx의 `grok`·`antigravity-cli` 사용자 범위로 설치한다. 하네스 전체 패키지를 유지해 setup 스크립트와 템플릿 상대경로를 보존한다.
- `--host all` 기본값, 기존 `both` 의미 보존, 개별 grok·agy 설치 계획과 GEMINI.md 내용 보존 테스트 통과.
- grok·agy의 실제 CLI로 플러그인 검증 통과(agy 스킬 4종 인식). 전체 의존성 설치와 모델 세션 실행은 검증하지 않았다.
- 임시 `GROK_HOME`에서 실제 설치 성공. 설치된 패키지에 setup 스크립트와 하네스 템플릿이 포함되는 것을 확인했다.

## codebase-memory-mcp 의존성

`scripts/install.py`는 `codebase-memory-mcp@latest`를 한 번 전역 설치한다. Codex·Claude Code·grok은 `.mcp.json`, agy는 `mcp_config.json`으로 같은 stdio 서버를 연결한다.
이 방식은 codebase-memory-mcp의 전역 agent-config 자동 설치를 실행하지 않으므로, FullOps를 설치하지 않은 호스트/클라이언트의 MCP 설정을 변경하지 않는다.

## 전용 디렉터리 분리

하네스 설정·핸드오버·컨텍스트·산출물·실행 로그는 `.fullops-squad/` 아래에서 관리한다. setup은 기존 `.agents/`를 수정하거나 가져오지 않는다. 루트 AGENTS.md·CLAUDE.md·GEMINI.md의 FullOps 블록만 전용 디렉터리를 가리킨다. 배포 레포의 `.agents/plugins/marketplace.json`은 Codex 설치용 메타데이터로 유지한다.
