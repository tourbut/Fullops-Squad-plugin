# Agent Plugins 1.0.0 적용 결과

적용일: 2026-09-16. `plugins/fullops-squad/`를 표준 원본으로 전환했고, 기존 CLI용 패키지는 같은 원본에서 생성한다. 1.1.0 working draft는 적용하지 않았다. [명세 상태](https://github.com/agentplugins/agent-plugins-spec#status).

## 패키지 구조

| 위치 | 역할 |
|---|---|
| `plugins/fullops-squad/plugin.json` | 1.0.0 $schema와 공통 메타데이터 |
| `plugins/fullops-squad/mcp.json` | 1.0.0 $schema, 명시적 type: stdio, 두 MCP 서버 |
| `plugins/fullops-squad/skills/` | 기존 네 스킬의 표준 진입점 |
| `plugins/fullops-squad/scripts/`, `assets/` | 실행 코드와 템플릿 |
| `adapters/` | Codex·Claude Code 전용 메타데이터 |
| `dependencies.json` | 통합 설치기의 외부 의존성 정본 |
| `dist/native/fullops-squad/` | 네 CLI용 생성물, Git 제외 |

표준 원본에서 기존 호스트 전용 manifest와 MCP 설정을 제거했다. 공통 manifest에 비표준 의존성 필드를 추가하지 않는다. 호스트 형식을 표준 확장으로 가장하지 않고 별도 배포물로 분리했다. [1.0.0 명세](https://github.com/agentplugins/agent-plugins-spec/blob/main/spec/1.0.0.md).

`python3 scripts/build.py`가 원본과 adapter를 합쳐 호스트 패키지를 만든다. 공통 메타데이터와 MCP 설정을 복제 편집할 필요가 없다. 현재 변환기는 command·args 기반 stdio만 지원한다. 다른 전송 방식이나 env·cwd를 추가하면 명시적인 변환을 요구하고 중단한다. 생성 표식이 없는 기존 디렉터리와 심볼릭 링크는 교체하지 않는다.

통합 설치기는 빌드를 먼저 실행한다. 마켓플레이스 등록 경로는 저장소 루트로 유지하고 source를 생성본으로 연결한다. Grok의 비대화형 설치에는 해당 패키지를 신뢰하는 `--trust`를 전달한다. README의 AI 설치 프롬프트는 그대로 사용할 수 있다.

## Context7과 하네스 경계

설치기는 `codebase-memory-mcp@latest`와 `@upstash/context7-mcp@4.1.1`을 설치한다. 표준 MCP 정의는 PATH의 각 실행 파일을 사용한다. Context7의 Node 요구사항은 20.18.1 이상이다. 표준 원본만 사용하는 클라이언트는 번들의 `DEPENDENCIES.md`에 따라 실행 의존성을 준비해야 한다.

Context7은 기본적으로 키 없이 사용한다. 추가 한도가 필요하면 호스트의 비밀 설정으로 MCP 프로세스에 `CONTEXT7_API_KEY`를 전달한다. 임의 환경변수 치환은 표준 계약이 아니므로 패키지에 키 치환식을 넣지 않는다. [Context7 안내](https://context7.com/docs/resources/all-clients), [서버 구현](https://github.com/upstash/context7/blob/master/packages/mcp/src/index.ts).

내부 코드는 codebase-memory-mcp로 탐색하고 외부 SDK 문서는 Context7로 확인한다. library ID·버전·출처·API 근거를 핸드오버에 남겨 worker가 재사용한다.

표준은 패키징 계약이다. 의존성 설치, 모델 배정, Orca 작업 전달과 레포별 setup은 기존 설치기·하네스가 담당한다. 설치만으로 서비스 레포를 활성화하지 않는다. 서비스 산출물은 계속 `.fullops-squad/`에서 관리한다. 호스트의 플러그인 상태 영역인 PLUGIN_DATA로 서비스 문서를 옮기지 않는다. [명세](https://github.com/agentplugins/agent-plugins-spec/blob/main/spec/1.0.0.md), [향후 고려 사항](https://github.com/agentplugins/agent-plugins-spec/blob/main/FUTURE_CONSIDERATIONS.md).

이전 하네스 진단의 모델 배정·완료 수락·문서 템플릿 개선은 이번 표준화와 별도 과제다.

## 검증

- `npm test`: 공식 manifest·MCP 스키마, 패키지 경로 경계, 네 스킬, 생성본 setup, 재빌드·사용자 디렉터리 보호, 기존 기록 동작과 설치 계획 통과.
- 공식 스키마를 upstream commit `ff8ab5e392cc87bd88d87c060815a87490e51003`에 고정하고 Apache-2.0 라이선스와 함께 검증용으로 보관했다. Ajv는 개발 의존성이며 설치기에 필요하지 않다.
- 생성본의 Codex 패키지 검증기·Claude Code·Grok validator 통과. agy는 임시 Context7을 PATH에 제공해 스킬 4개·MCP 2개 검증 통과.
- 격리된 CODEX_HOME과 GROK_HOME에서 생성본 설치 성공. Codex 설치 캐시에 setup 스크립트가 포함됨을 확인했다.
- Context7의 임시 설치·MCP initialize·도구 발견·키 없는 공개 Python 라이브러리 검색은 앞선 검토에서 성공했다.

표준 전용 로더의 전체 실행 적합성, Claude Code·agy의 실제 설치, Orca worker 전체 기동까지 검증한 것은 아니다. 사용자 전역 설정과 서비스 레포 setup은 변경하지 않았다.
