# FullOps Squad

Orca에서 Codex·Claude Code·grok·agy worker에게 작업을 전달하고, **개발 산출물과 작업 기록을 레포에 남기는 하네스 플러그인**입니다.
고성능 모델이 기획·설계를 맡고 비용이 낮은 모델이 명확한 지시서에 따라 구현하도록 구성하는 것이 목적입니다. 모델 선택은 프로젝트의 역할 배정과 Orca 실행 설정에서 관리합니다.
플러그인 설치와 레포 활성화를 분리합니다. 설치만으로 다른 레포에 AGENTS.md나 문서 디렉터리를 만들지 않습니다.

## 0.5.0 Jev 코드 탐색

지시서를 쓸 때 `jev_find.py`가 파일 목록과 헤더 설명으로 만든 지도에서 Jev로 코드 위치를 찾고, "관련 코드 없음"도 판정합니다. 과제가 끝나면 실제 변경과 비교한 적중률을 자동으로 기록합니다. 새 코드 파일에는 헤더 설명을 적습니다(lint DOC-001). [변경 범위·기존 레포 적용](docs/releases/0.5.0.md)을 확인하세요.

## 0.4.1 done-gate·lint 보강

worker 세션이 코드를 바꾸고 lint를 통과하지 않은 채 끝내려 하면 Stop hook이 한 번 막습니다. lint 설정은 merge-base 기준으로 적용해 브랜치가 스스로 규칙을 느슨하게 할 수 없고, 테스트 skip 추가·삭제를 잡습니다. codebase-memory-mcp 의존성은 제거했습니다. [변경 범위·기존 레포 적용](docs/releases/0.4.1.md)을 확인하세요.

## 0.4.0 lint 게이트·대기 비용·Jev 문맥

코드 변경마다 레포의 기존 lint 도구와 스택 무관 기본 검사를 실행하고, ERROR가 남으면 리뷰를 수락하지 않습니다. coordinator는 `orca_wait.py`로 기다려 worker heartbeat·status 알림에 세션이 깨지 않게 합니다. 지시서를 쓸 때 Jev로 후보 문서를 분류해 worker가 먼저 읽을 목록을 줄일 수 있습니다. 기존 레포는 setup 갱신과 lint 명령 등록이 필요합니다. [변경 범위·기존 레포 적용](docs/releases/0.4.0.md)을 확인하세요.

## 0.3.1 공통 개발 기준

ECC에서 코딩·테스트·보안 원칙만 선별·수정한 [공통 규칙](plugins/fullops-squad/assets/repository/.fullops-squad/rules/common/README.md)을 제공합니다. ECC 런타임·에이전트·훅은 설치하지 않습니다. 규칙은 setup한 레포의 `.fullops-squad/rules/common/`에만 생성하며 기존 프로젝트 기준과 미해결 critical/high 차단은 유지합니다.

작업자와 검토자는 같은 규칙·프로젝트 정본 버전을 확인하고 지시서에 적용 기준과 예외를 남깁니다. 기존 레포의 규칙·문서·작업 기록은 자동 덮어쓰지 않습니다. 플러그인 업데이트와 별도로 setup 갱신 및 연결 문서의 명시적 통합이 필요합니다. [변경 범위·기존 레포 적용·개선 우선순위](docs/releases/0.3.1.md)를 확인하세요.

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
| caveman | 사용자 범위 스킬 | 사용자 범위 스킬 | 사용자 범위 스킬 |
| typesafe-ai | 사용자 범위 스킬 | 사용자 범위 스킬 | 사용자 범위 스킬 |
| anthropics/skills 5종 | 사용자 범위 스킬 | 사용자 범위 스킬 | 사용자 범위 스킬 |
| Context7 | FullOps MCP 서버 | FullOps MCP 서버 | FullOps MCP 서버 |
| Open Code Review delegate | CLI + 사용자 범위 스킬 | CLI + 사용자 범위 스킬 | CLI + 사용자 범위 스킬 |
| Orca CLI 가이드 | 설치된 Orca에서 동적으로 조회 | 동일 | 동일 |

설치기는 표준 원본에서 `dist/native/fullops-squad/`를 먼저 생성합니다. Codex·Claude Code의 마켓플레이스와 grok·agy의 `plugin install <로컬 경로>`는 이 호스트 호환 패키지를 사용합니다. grok·agy의 위 외부 스킬 의존성은 사용자 범위로 설치합니다.
agy의 npx 대상은 IDE용 `antigravity`가 아닌 `antigravity-cli`이며 경로는 `~/.gemini/antigravity-cli/skills/`입니다. grok은 `~/.grok/skills/`를 사용합니다.

Anthropic 스킬은 frontend-design, mcp-builder, skill-creator, web-artifacts-builder, webapp-testing입니다.
caveman은 Codex·Claude Code에서 FullOps 플러그인을 활성화한 새 세션(`startup`·`clear`)에 `full`로 적용됩니다. SessionStart 훅이 설치된 스킬을 읽으며 외부 규칙을 복제하지 않습니다. `/caveman off`로 해제할 수 있고, 재개·압축 시에는 다시 활성화하지 않습니다. grok·agy는 스킬 설치만 지원하므로 명시적으로 호출합니다. typesafe-ai는 Jev의 문맥 선별·증거 대조 등 의미 판단 기능을 개발·유지보수할 때 사용하는 가이드입니다. Jev 실행 자체의 런타임 의존성은 아니며, 스킬 설치는 API 호출을 활성화하거나 API 키를 설정하지 않습니다.
외부 스킬·MCP 구현을 이 레포에 복사하지 않습니다. 출처와 설치 대상은 [dependencies.json](dependencies.json)에서 관리합니다.
이미 같은 스킬을 다른 출처로 설치했다면 중복 설치 경로를 정리해 한 출처만 사용하세요. 설치기는 기존 사용자 스킬을 삭제하지 않습니다.

**호스트의 설치 버튼만으로 모든 외부 스킬이 설치되는 것은 아닙니다.** Claude Code의 플러그인 의존성은 네이티브 자동 설치를 사용하지만, 사용자 범위 스킬과 Codex의 보완 설치는 위 통합 설치기가 수행합니다. 현재 구현의 전체 설치 진입점은 `scripts/install.py`입니다.
Context7도 통합 설치기가 `@upstash/context7-mcp@4.1.1`을 설치하고 네 CLI에 `context7-mcp` stdio 서버로 연결합니다. 기본 사용은 키 없이 시작하며, 높은 호출 한도가 필요하면 MCP 프로세스에 `CONTEXT7_API_KEY`를 제공하도록 사용하는 호스트의 환경/비밀 설정을 사용합니다. 키를 레포나 지시서에 기록하지 않습니다. 연결·조회 실패는 설치 성공과 구분해 확인합니다. [Context7 설정 안내](https://context7.com/docs/resources/all-clients)
외부 의존성은 일반 도구로 전역 설치됩니다. 이 플러그인의 레포별 활성화 조건은 외부 플러그인의 자체 동작까지 비활성화하지 않습니다.

## 작업 흐름

역할은 레포별 setup에서 제품·기술·규모에 맞게 구성합니다. `fullops.json`에 역할과 브랜치를 등록하고 역할별 인박스·컨텍스트를 생성합니다. GitHub remote의 기준 브랜치에서 `fullops/<역할 ID>` 원격 브랜치를 만들며, 기존 브랜치와 작업 기록은 보존합니다. CLI·모델 배정은 `orca-agents.md`에서 관리합니다.

setup 재실행은 저장된 remote·기준 브랜치를 재사용하며 명시적 옵션으로 변경할 수 있습니다. 원격 연결된 레포의 새 역할은 원격 setup으로 추가합니다. 로컬 전용 모드에서는 해당 레포의 기존 역할과 문서만 유지합니다.

1. `fullops-work`: 실제 상태 확인 → 역할별 지시서·완료 기준·산출물·복귀 주소 작성 → 먼저 읽을 문서 선정(선택: Jev 분류).
2. `fullops-orca dispatch`: 별도 worker 세션에 전달 → 실제 지시서 가시성과 착수 확인 → `orca_wait.py`로 heartbeat·status 알림 없이 대기.
3. worker: 구현·검증·lint 게이트 통과·원천 문서 갱신 → 로그 아카이브 → 컨텍스트 요약 → 부모에게 직접 회신.
4. `fullops-review`: SHA 고정 → OCR delegate 파일·규칙 준비 → AI 검토 → worker 체크아웃 lint 결과 기록 → 통일된 보고서·기록 검사. OCR 제외 파일도 검토하거나 생략 사유를 남깁니다.
5. 병합 책임자: 리뷰·브랜치·SHA·diff·검증 확인 → 허가된 병합 → 쉬고 있는 worker 브랜치 동기화.
6. `fullops-deliverables`: 기획부터 이행까지 D01–D13 원천 문서와 납품용 인덱스 관리.

OCR CLI는 `@alibaba-group/open-code-review@1.12.5`로 설치하고 자동 업데이트를 끈 상태로 delegate 명령을 실행합니다. 별도 OCR API 키 없이 호스트 AI가 리뷰하며 해당 AI의 사용량은 발생합니다. 레포별 `review/rule.json`으로 테스트·문서·게임 자산의 기본 제외를 보완합니다. 리뷰 기록 검사 통과는 검토 내용과 테스트 성공을 자동 보증하지 않습니다.

코드 변경은 `scripts/lint.py` lint 게이트를 거칩니다. setup에서 레포에 이미 있는 ruff·eslint·타입 검사 등의 명령을 `.fullops-squad/lint/lint.json`에 등록하면, 변경 파일에 대해 그 명령들과 스택 무관 기본 검사(줄 수 증가, 범위 없는 억제, `eval`/`exec`, 하드코딩 비밀값, 레포별 정규식 규칙)를 함께 실행합니다. 기존 위반은 소급하지 않습니다. `review.py check`는 lint 결과가 없거나 SHA가 다르거나 ERROR가 남아 있으면 실패합니다. 규칙과 설정은 [lint 게이트](plugins/fullops-squad/assets/repository/.fullops-squad/lint/README.md)를 참고하세요.

```text
.fullops-squad/
  fullops.json                 # 이 레포의 활성화 표식
  FULLOPS.md                   # 규약 지도
  project.md, orca-agents.md    # 프로젝트 기준·역할 배정
  PLANS.md                     # 현재 할 일
  rules/common/                # 공통 코딩·테스트·보안 기준과 출처·MIT 고지
  handovers/to_<role>.md        # 지금 할 일만
  handovers/logs/               # 지시서·결과 전문, append
  contexts/<role>.md           # 결정·교훈 3줄 요약
  lint/lint.json, README.md    # lint 명령·기본 검사 설정과 게이트 규약
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
원본 서비스의 FastAPI/Svelte 코드, 특정 레이어·Svelte 린터 규칙, 과거 로그, remote, 터미널 핸들은 포함하지 않습니다.
각 서비스의 기술 기준은 setup에서 `project.md`에 연결합니다. 기존 FullOps-Squad 전체를 자동 변환하는 마이그레이션 도구는 아닙니다.

## 개발 검증

선택형 Jev 관찰 실험의 입력 형식과 실행 방법은 [Jev 관찰 실험](docs/jev-observe.md)에 있습니다. 지시서를 쓸 때 `jev_context.py`로 후보 문서를 분류해 worker가 먼저 읽을 목록을 줄일 수 있습니다. 제외는 추천이며 필수 문서와 실패 시에는 모두 유지합니다.

`plugins/fullops-squad/`는 Agent Plugins 1.0.0의 표준 원본입니다. `plugin.json`과 `mcp.json`이 공통 정본이며 `adapters/`에서 기존 호스트 메타데이터를 관리합니다. `dist/`는 생성물이므로 직접 수정하지 않습니다. 표준 지원 클라이언트에는 원본 디렉터리를 전달할 수 있으며, 실행 의존성은 별도 설치해야 합니다.

```bash
python3 scripts/build.py
npm ci
npm test
npm run test:review  # OCR CLI가 설치된 환경의 delegate 통합 검사
python3 scripts/install.py --host all --dry-run
claude plugin validate dist/native/fullops-squad
claude plugin validate .claude-plugin/marketplace.json
grok plugin validate dist/native/fullops-squad
agy plugin validate dist/native/fullops-squad
```

setup 검증은 임시 레포에서 실행합니다. 공식 스키마 사본과 개발용 Ajv로 표준 형식을 검사하며 설치·실행 중 스키마를 다운로드하지 않습니다. agy 검증에는 MCP 실행 파일이 PATH에 있어야 합니다. 전체 Orca worker 기동은 별도 통합 검증이 필요합니다.

`npm test`는 기존 Python 회귀·표준 스키마 검사와 공통 규칙 배포·보존·worker 가시성 검사를 실행합니다. GitHub Actions는 기본 검사와 고정 OCR CLI의 실제 delegate 검사를 별도 job으로 실행합니다. 공통 규칙 문서는 자동 품질 판정이나 실행 권한을 추가하지 않습니다.

## 참고

- [Agent Plugins 표준 적용](docs/agent-plugins-spec-review.md): 공통 배포 형식과 호스트 호환 패키지.
- [mattpocock/skills](https://github.com/mattpocock/skills): 배포와 레포별 setup 분리 방식 참고.
- [Claude Code 플러그인 의존성](https://code.claude.com/docs/en/plugin-dependencies): 네이티브 dependencies 및 cross-marketplace 허용 목록.
- [OpenAI 플러그인 패키징](https://developers.openai.com/plugins/build/plugins): Codex 패키지 구조 참고.
- [Antigravity CLI 플러그인·스킬](https://antigravity.google/docs/cli/plugins/): agy 패키지 형식과 사용자 스킬 경로.
- [skills CLI 호스트 매핑](https://github.com/vercel-labs/skills/blob/main/src/agents.ts): `grok`·`antigravity-cli` 설치 대상.
