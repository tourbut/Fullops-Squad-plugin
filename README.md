# FullOps Squad

Orca에서 Codex·Claude Code·grok·agy worker에게 작업을 전달하고, **개발 산출물과 작업 기록을 레포에 남기는 하네스 플러그인**입니다.
고성능 모델이 기획·설계를 맡고 비용이 낮은 모델이 명확한 지시서에 따라 구현하도록 구성하는 것이 목적입니다. 모델 선택은 프로젝트의 역할 배정과 Orca 실행 설정에서 관리합니다.
플러그인 설치와 레포 활성화를 분리합니다. 설치만으로 다른 레포에 AGENTS.md나 문서 디렉터리를 만들지 않습니다.

## 설치

사용 중인 AI CLI에 아래 프롬프트를 그대로 붙여 넣으세요. 에이전트가 현재 CLI에 맞는 플러그인과 의존성을 설치합니다.

```text
FullOps Squad 플러그인을 https://github.com/tourbut/Fullops-Squad-plugin 에서 찾아 설치해줘. 저장소의 AGENTS.md 설치 지침을 읽고, 지금 사용 중인 AI CLI(Codex, Claude Code, grok, agy)에 맞는 호스트 하나를 선택해 플러그인과 의존성까지 설치하고 확인해줘. 서비스 레포의 하네스 setup은 내가 별도로 요청할 때 진행해줘.
```

Python 3.9+, Git 2.41+, Node.js 20.18.1+/npm/npx, 사용할 에이전트 CLI와 Orca 앱이 필요합니다.
직접 설치하려면 이 레포를 유지할 경로에 내려받은 뒤 통합 설치기를 실행합니다. Codex·Claude Code는 해당 경로를 로컬 마켓플레이스로 등록합니다.

```bash
git clone https://github.com/tourbut/Fullops-Squad-plugin.git
cd Fullops-Squad-plugin
python3 scripts/install.py --host codex
```

위 예시는 Codex용입니다. `--host claude-code`, `--host grok`, `--host agy`로 사용할 CLI를 선택하세요. 네 CLI에 모두 설치하려면 `--host all`을 사용합니다.
기본값 `all`은 네 CLI 전체이며, 기존 `both`는 Codex와 Claude Code 두 개만 설치합니다.
`--dry-run`은 실행할 명령만 출력합니다. 실행 중 실패하면 해당 명령에서 중단하며 성공한 설치를 되돌리지는 않습니다.
배포 전 개발 체크아웃에서도 같은 명령이 현재 로컬 마켓플레이스를 등록합니다.

| 의존성 | Codex | Claude Code | grok·agy |
|---|---|---|---|
| ponytail | 네이티브 플러그인 | 네이티브 의존성 | 사용자 범위 스킬 |
| mattpocock/skills | 사용자 범위 스킬 | mattpocock-skills 네이티브 의존성 | 사용자 범위 스킬 |
| diagram-design | 사용자 범위 스킬 | 사용자 범위 스킬 | 사용자 범위 스킬 |
| anthropics/skills 5종 | 사용자 범위 스킬 | 사용자 범위 스킬 | 사용자 범위 스킬 |
| codebase-memory-mcp | FullOps MCP 서버 | FullOps MCP 서버 | FullOps MCP 서버 |
| Context7 | FullOps MCP 서버 | FullOps MCP 서버 | FullOps MCP 서버 |
| Open Code Review delegate | CLI + 사용자 범위 스킬 | CLI + 사용자 범위 스킬 | CLI + 사용자 범위 스킬 |
| Orca CLI 가이드 | 설치된 Orca에서 동적으로 조회 | 동일 | 동일 |

설치기는 표준 원본에서 `dist/native/fullops-squad/`를 먼저 생성합니다. Codex·Claude Code의 마켓플레이스와 grok·agy의 `plugin install <로컬 경로>`는 이 호스트 호환 패키지를 사용합니다. grok·agy의 위 외부 스킬 의존성은 사용자 범위로 설치합니다.
agy의 npx 대상은 IDE용 `antigravity`가 아닌 `antigravity-cli`이며 경로는 `~/.gemini/antigravity-cli/skills/`입니다. grok은 `~/.grok/skills/`를 사용합니다.

Anthropic 스킬은 frontend-design, mcp-builder, skill-creator, web-artifacts-builder, webapp-testing입니다.
외부 스킬·MCP 구현을 이 레포에 복사하지 않습니다. 출처와 설치 대상은 [dependencies.json](dependencies.json)에서 관리합니다.
이미 같은 스킬을 다른 출처로 설치했다면 중복 설치 경로를 정리해 한 출처만 사용하세요. 설치기는 기존 사용자 스킬을 삭제하지 않습니다.

**호스트의 설치 버튼만으로 모든 외부 스킬이 설치되는 것은 아닙니다.** Claude Code의 플러그인 의존성은 네이티브 자동 설치를 사용하지만, 사용자 범위 스킬과 Codex의 보완 설치는 위 통합 설치기가 수행합니다. 현재 구현의 전체 설치 진입점은 `scripts/install.py`입니다.
`codebase-memory-mcp`는 `npm install --global codebase-memory-mcp@latest`로 설치합니다. FullOps 플러그인의 MCP 선언이 이 실행 파일을 Codex·Claude Code·grok·agy에 연결하므로, 전역 MCP 설정을 별도로 쓰지 않습니다.
Context7도 통합 설치기가 `@upstash/context7-mcp@4.1.1`을 설치하고 네 CLI에 `context7-mcp` stdio 서버로 연결합니다. 기본 사용은 키 없이 시작하며, 높은 호출 한도가 필요하면 MCP 프로세스에 `CONTEXT7_API_KEY`를 제공하도록 사용하는 호스트의 환경/비밀 설정을 사용합니다. 키를 레포나 지시서에 기록하지 않습니다. 연결·조회 실패는 설치 성공과 구분해 확인합니다. [Context7 설정 안내](https://context7.com/docs/resources/all-clients)
외부 의존성은 일반 도구로 전역 설치됩니다. 이 플러그인의 레포별 활성화 조건은 외부 플러그인의 자체 동작까지 비활성화하지 않습니다.

## 작업 흐름

역할은 레포별 setup에서 제품·기술·규모에 맞게 구성합니다. `fullops.json`에 역할과 브랜치를 등록하고 역할별 인박스·컨텍스트를 생성합니다. GitHub remote의 기준 브랜치에서 `fullops/<역할 ID>` 원격 브랜치를 만들며, 기존 브랜치와 작업 기록은 보존합니다. CLI·모델 배정은 `orca-agents.md`에서 관리합니다.

setup 재실행은 저장된 remote·기준 브랜치를 재사용하며 명시적 옵션으로 변경할 수 있습니다. 원격 연결된 레포의 새 역할은 원격 setup으로 추가합니다. 로컬 전용 모드에서는 해당 레포의 기존 역할과 문서만 유지합니다.

1. `fullops-work`: 실제 상태 확인 → 역할별 지시서·완료 기준·산출물·복귀 주소 작성.
2. `fullops-orca dispatch`: 별도 worker 세션에 전달 → 실제 지시서 가시성과 착수 확인.
3. worker: 구현·검증·원천 문서 갱신 → 로그 아카이브 → 컨텍스트 요약 → 부모에게 직접 회신.
4. `fullops-review`: SHA 고정 → OCR delegate 파일·규칙 준비 → AI 검토 → 통일된 보고서·기록 검사. OCR 제외 파일도 검토하거나 생략 사유를 남깁니다.
5. 병합 책임자: 리뷰·브랜치·SHA·diff·검증 확인 → 허가된 병합 → 쉬고 있는 worker 브랜치 동기화.
6. `fullops-deliverables`: 기획부터 이행까지 D01–D13 원천 문서와 납품용 인덱스 관리.

OCR CLI는 `@alibaba-group/open-code-review@1.12.5`로 설치하고 자동 업데이트를 끈 상태로 delegate 명령을 실행합니다. 별도 OCR API 키 없이 호스트 AI가 리뷰하며 해당 AI의 사용량은 발생합니다. 레포별 `review/rule.json`으로 테스트·문서·게임 자산의 기본 제외를 보완합니다. 리뷰 기록 검사 통과는 검토 내용과 테스트 성공을 자동 보증하지 않습니다.

```text
.fullops-squad/
  fullops.json                 # 이 레포의 활성화 표식
  FULLOPS.md                   # 규약 지도
  project.md, orca-agents.md    # 프로젝트 기준·역할 배정
  PLANS.md                     # 현재 할 일
  handovers/to_<role>.md        # 지금 할 일만
  handovers/logs/               # 지시서·결과 전문, append
  contexts/<role>.md           # 결정·교훈 3줄 요약
  review/rule.json             # 레포별 OCR 필터·규칙
  review/_REPORT.md            # 리뷰 보고서 템플릿
  docs/
    planning/                  # 문제 정의·요구사항
    design-docs/               # 설계·도메인·목업·ADR
    exec-plans/                # 실행 계획·상세 작업 로그
    evaluations/qa-reports/     # 검증 근거
    operations/                # 사용자·운영·인수인계
    generated/                 # 실제 도구가 생성한 결과
    deliverables/              # 원천 링크 기반 산출물 13종
    agents/                    # 외부 엔지니어링 스킬의 레포 설정
```

원본 FullOps-Squad의 핸드오버·직접 회신·이력 분리·산출물 정본 구조를 이식했습니다.
원본 서비스의 FastAPI/Svelte 코드, 특정 레이어·린터 규칙, 과거 로그, remote, 터미널 핸들은 포함하지 않습니다.
각 서비스의 기술 기준은 setup에서 `project.md`에 연결합니다. 기존 FullOps-Squad 전체를 자동 변환하는 마이그레이션 도구는 아닙니다.

## 개발 검증

`plugins/fullops-squad/`는 Agent Plugins 1.0.0의 표준 원본입니다. `plugin.json`과 `mcp.json`이 공통 정본이며 `adapters/`에서 기존 호스트 메타데이터를 관리합니다. `dist/`는 생성물이므로 직접 수정하지 않습니다. 표준 지원 클라이언트에는 원본 디렉터리를 전달할 수 있으며, 실행 의존성은 별도 설치해야 합니다.

```bash
python3 scripts/build.py
npm ci
npm test
python3 tests/review-check.py  # OCR CLI가 설치된 환경의 delegate 통합 검사
python3 scripts/install.py --host all --dry-run
claude plugin validate dist/native/fullops-squad
claude plugin validate .claude-plugin/marketplace.json
grok plugin validate dist/native/fullops-squad
agy plugin validate dist/native/fullops-squad
```

setup 검증은 임시 레포에서 실행합니다. 공식 스키마 사본과 개발용 Ajv로 표준 형식을 검사하며 설치·실행 중 스키마를 다운로드하지 않습니다. agy 검증에는 MCP 실행 파일이 PATH에 있어야 합니다. 전체 Orca worker 기동은 별도 통합 검증이 필요합니다.

## 참고

- [Agent Plugins 표준 적용](docs/agent-plugins-spec-review.md): 공통 배포 형식과 호스트 호환 패키지.
- [mattpocock/skills](https://github.com/mattpocock/skills): 배포와 레포별 setup 분리 방식 참고.
- [Claude Code 플러그인 의존성](https://code.claude.com/docs/en/plugin-dependencies): 네이티브 dependencies 및 cross-marketplace 허용 목록.
- [OpenAI 플러그인 패키징](https://developers.openai.com/plugins/build/plugins): Codex 패키지 구조 참고.
- [Antigravity CLI 플러그인·스킬](https://antigravity.google/docs/cli/plugins/): agy 패키지 형식과 사용자 스킬 경로.
- [skills CLI 호스트 매핑](https://github.com/vercel-labs/skills/blob/main/src/agents.ts): `grok`·`antigravity-cli` 설치 대상.
