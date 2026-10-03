---
title: FullOps Squad
status: draft
updated: 2026-10-03
owner: maintainer
summary: Orca에서 AI worker의 배정, 문서, 검증, 리뷰를 관리하는 하네스 플러그인
---

# FullOps Squad

Orca IDE에서 Claude Code·Codex·grok·agy를 역할별 worker로 운영하는 플러그인입니다.
작업 지시서와 결과를 Git 레포에 기록하고, 구현 결과를 lint와 독립 리뷰로 확인합니다.

**Orca IDE가 필요합니다.** 플러그인은 Orca 앱을 설치하지 않습니다.
설치는 CLI 사용자 범위에 적용됩니다. 서비스 레포의 `.fullops-squad/`를 만드는 setup은 별도로 요청합니다.

## 작업 흐름

1. coordinator가 요청과 과제 키를 받습니다. 운영 작업은 직접 처리합니다.
2. 코드·산출물 작업은 Jev가 `simple` 또는 `design`으로 분류합니다. 담당 역할, 모델·effort, 갱신할 산출물도 추천합니다.
3. `simple`은 coordinator가 지시서를 씁니다. `design`은 설계 역할이 문서와 역할별 지시서를 씁니다.
4. worker는 자기 워크트리에서 구현·검증합니다. 질문은 coordinator에게 보내고 완료는 `worker_done`으로 보고합니다.
5. 병합 책임자는 고정 SHA의 lint·테스트·delegate 리뷰를 확인한 뒤 허가된 병합을 수행합니다.

역할은 레포마다 정합니다. 아래 ID는 예시입니다.

| 역할 | 책임 |
|---|---|
| coordinator (`coor`) | 배정, 질문 전달, 완료 보고 처리, 운영과 병합 |
| 설계 역할 (`architecture`) | 요구사항·공유 계약과 지시서 작성. 현재 hook은 제품 코드 수정을 차단함 |
| 구현 역할 (`dev`) | 지시서 범위의 기술 계획, 구현, 테스트와 문서 갱신 |
| 아트·운영 역할 (`art`, `ops`) | 지정한 파일과 결과물 관리 |
| 검증 역할 (`tester`, 선택) | 테스트와 증거 작성. 제품 코드는 수정하지 않음 |

역할·브랜치는 `fullops.json`, 책임·CLI·모델 후보는 `orca-agents.md`에 등록합니다.
모델 후보는 약한 것부터 강한 순서로 적습니다. Jev는 등록된 후보에서 선택합니다.
설계·coordinator·tester 역할은 라우팅 기준의 해당 줄로 지정합니다. 기본 coordinator는 기본 브랜치 체크아웃입니다.
역할 워크트리에서 coordinator를 운영하면 `- coordinator 역할: <역할 ID>`를 등록합니다.

### 제품 기획과 기술 계획 분리

제품 기획자가 목표·제품 규칙을 정하고, DEV가 기술 계획·구현·테스트를 함께 맡을 수 있습니다.
`orca-agents.md`의 `## 라우팅 기준`에 다음 줄을 추가합니다. 역할 ID는 `fullops.json`의 등록 역할을 사용합니다.

```text
- 설계 역할: `designer`
- 제품 기획 역할: `designer`
- 기술 계획 역할: `dev`
```

제품 기획 역할과 기술 계획 역할은 서로 달라야 합니다. coordinator와도 분리합니다.
기술 난도가 높은 작업도 확정된 제품 요구 안에 있으면 `implementation`으로 담당 worker에 배정합니다.
제품 규칙 결정·범위 확대·불명확한 공유 제품 기준은 `product`로 기획자에게 배정합니다.
호출 실패·낮은 확신은 `unresolved`로 보류합니다. 담당 책임을 확인한 뒤 `--override-role`과 `--reason`으로 근거를 남깁니다.
기존 기록의 재선정은 `--force`로 원본을 보존합니다. 위 두 marker가 없으면 기존 `simple/design` 구조를 유지합니다.

역할을 바꿀 때 기존 `fullops/*` 브랜치를 재사용할 수 있습니다. 역할별 브랜치는 고유해야 합니다.
독립 리뷰는 별도 세션과 고정 SHA의 깨끗한 detached snapshot에서 진행합니다.
새 리뷰 기록은 구현자·검토자 세션 ID와 snapshot 경로를 검증합니다. 기존 리뷰 원본은 보존합니다.
ART 직접 검수, 독립 동작 QA와 미해결 critical/high 차단도 유지합니다.

### 대기와 검증

착수를 확인한 뒤 coordinator는 `orca_wait.py`로 완료·질문·오류 메시지를 기다립니다.
heartbeat·status는 스크립트가 흡수합니다. 정상 작업의 진행 확인은 기본 60분 간격입니다.
`worker_done`과 오류·질문은 주기와 관계없이 처리합니다. 완료 보고의 과제 키·SHA·검증 요약·남은 일을 우선 확인합니다.
보고가 누락되거나 충돌·실패가 있으면 추가 근거를 읽습니다. 수락과 병합에서는 검증 게이트를 확인합니다.

| 도구 | 확인하는 것 |
|---|---|
| `fullops-test` | 코드 테스트와 웹·Unity 조작 테스트. 조작 테스트의 통과 판정은 시나리오 `checks`가 담당 |
| `fullops-review` | OCR CLI가 준비한 파일·규칙을 호스트 AI가 리뷰. 별도 OCR LLM API 키는 불필요 |
| `lint.py` | 프로젝트 검사 명령, 코드 헤더, 줄 수, 범위 없는 억제, 비밀값 의심, 문서 메타데이터 |
| flow-gate | route 기록, `worker-start --run`, 역할별 행동과 완료 보고. 터미널 주입으로 배정하는 행동 차단 |
| done-gate | 이 세션의 코드 변경에 현재 HEAD의 lint 통과 기록이 없으면 종료를 한 번 차단 |

미해결 critical/high와 lint ERROR는 수락을 막습니다. 생성 현황판 파일은 done-gate의 코드 검사에서 제외합니다.
hook은 셸 우회까지 차단하지 않으며 hook 자체의 오류는 작업을 막지 않습니다.
자동 검사는 구현의 정확성을 보증하지 않습니다. 프로젝트 기준이 [공통 규칙](plugins/fullops-squad/assets/repository/.fullops-squad/rules/common/README.md)보다 우선합니다.

## 문서와 검색

FullOps가 작성하는 기획·설계·실행 계획·핸드오버·컨텍스트·QA·리뷰 문서에 front matter를 등록합니다.
일반 문서는 `title`, `status`, `updated`, `owner`, `summary`를 사용합니다. 과제 문서는 `tasks`를 연결합니다.
D01–D13 원천 문서에는 `id`를 추가합니다. 필요하면 `upstream`·`downstream`을 연결합니다.

문서는 **한국어**로 작성합니다. ASD-STE100의 짧은 문장, 명확한 주체, 일관된 용어, 실행 순서와 확인 가능한 결과 원칙을 적용합니다.
영어 통제 언어 표준의 공식 준수를 뜻하지 않습니다. 상세 기준은 [문서 작성 규칙](plugins/fullops-squad/assets/repository/.fullops-squad/docs/agents/document-writing.md)에 있습니다.

front matter는 설치된 플러그인의 도구로 씁니다. `--path`는 `.fullops-squad/` 기준입니다.

```bash
# 일반 문서: 기존 본문을 보존한다.
python3 <플러그인>/scripts/deliverables.py --repo . --stamp --path docs/exec-plans/phases/TASK-1.md --owner dev --summary "로그인 실패 처리와 검증 결과" --task TASK-1
# D01–D13 원천: 인덱스 상태도 맞춘다.
python3 <플러그인>/scripts/deliverables.py --repo . --stamp --id D03 --owner architecture --summary "인증 모듈의 책임과 연결" --task TASK-1
```

`work.py new`는 핸드오버의 메타데이터를 생성합니다. 본문 첫 줄은 `# <과제 키> — <목표>`입니다.
기존 문서는 다음 수정 때 적용합니다. 빈 인박스·외부 원본 규칙·도구 로그는 보존합니다.
변경된 원천 문서는 lint `DOC-002`, 일반 FullOps 문서는 `DOC-003`으로 검사합니다. 코드 lint의 제외 설정과 별도로 검사합니다.

### 필요한 파일 찾기

`jev_find.py`는 커밋된 HEAD의 파일 지도에서 후보를 고릅니다.
문서는 front matter의 `title`·`summary`를 사용합니다. 메타데이터가 없는 기존 Markdown은 본문 제목을 사용합니다.
비밀 경로·심볼릭 링크·바이너리는 후보에서 제외합니다.

```bash
# 코드 검색: 하네스 파일은 제외한다.
python3 <플러그인>/scripts/jev_find.py find --repo . --role dev --key TASK-1
# 문서 검색: .fullops-squad 문서도 포함한다.
python3 <플러그인>/scripts/jev_find.py find --repo . --role dev --key TASK-1 --scope documents
```

결과는 각각 `<과제 키>-find.json`과 `<과제 키>-documents-find.json`에 남습니다.
별도 지시서에는 `--handover .fullops-squad/handovers/<파일>.md`를 지정합니다.
필요한 후보를 합친 뒤 `jev_context.py`가 관련성·근거·충돌·AI 지시문을 분류합니다. 추천이므로 필수 문서는 유지합니다.
코드와 문서 검색을 분리해 문서 후보가 코드 후보를 밀어내는 것을 방지합니다.

## 설치

필요 환경: Python 3.9+, Git 2.41+, Node.js 20.18.1+/npm/npx, 사용할 AI CLI, Orca IDE.
일반 설치는 GitHub 마켓플레이스를 사용합니다. 개발 체크아웃·agy 설치는 [개발 문서](docs/development.md)를 따릅니다.

### 통합 설치기

통합 설치기는 Codex·Claude Code·grok의 설치 명령을 실행합니다. PATH에 있는 CLI를 자동으로 선택합니다.
플러그인은 각 CLI의 GitHub 마켓플레이스에서 설치합니다. 외부 의존성도 설치하고 검사합니다.

터미널에서 다음 명령을 실행합니다. `@latest`는 최신 설치기를 선택합니다.

```bash
npx --yes fullops-squad@latest install
npx --yes fullops-squad@latest update
npx --yes fullops-squad@latest check
```

기본 대상은 사용 가능한 세 CLI 전체입니다. `--hosts codex,grok`처럼 일부 CLI만 지정할 수 있습니다.
`--dry-run`으로 변경 전에 실행 계획을 확인합니다.

```bash
npx --yes fullops-squad@latest update --dry-run
npx --yes fullops-squad@latest install --hosts codex,grok
```

Codex는 현재 `CODEX_HOME`, 기본 사용자 홈, 기존 Windows Orca 홈을 처리합니다. 다른 홈은 `--codex-home PATH`로 추가합니다.
설치나 업데이트가 끝나면 각 CLI에서 새 에이전트 세션을 엽니다.

`update --repo PATH`는 업데이트 전 설치 버전 이후의 레포 적용 안내를 출력합니다.
에이전트에게 해당 레포의 FullOps update를 요청하면 적용 작업을 진행합니다.

```bash
npx --yes fullops-squad@latest update --repo "D:/workspace/my-service"
```

설치기는 서비스 레포를 직접 변경하지 않습니다. 레포 적용은 에이전트가 릴리스 내용을 읽고 수행합니다.
설치기를 전역에 설치하려면 `npm install --global fullops-squad@latest`를 실행합니다.
이후 `fullops-squad install|update|check` 명령을 사용할 수 있습니다. 설치기 자체 갱신은 같은 npm 설치 명령으로 수행합니다.
아래 CLI별 명령으로 직접 설치할 수도 있습니다.

### Claude Code

Claude Code 세션에서 실행합니다. 이미 등록된 마켓플레이스는 건너뜁니다.

```text
/plugin marketplace add DietrichGebert/ponytail
/plugin marketplace add anthropics/claude-plugins-official
/plugin marketplace add tourbut/Fullops-Squad-plugin
/plugin install fullops-squad@fullops-squad
```

### Codex

```bash
codex plugin marketplace add tourbut/Fullops-Squad-plugin
codex plugin add fullops-squad@fullops-squad
```

### grok

```bash
grok plugin marketplace add tourbut/Fullops-Squad-plugin
grok plugin install fullops-squad@fullops-squad --trust
```

### 외부 의존성

설치 뒤 OCR CLI·Context7 MCP와 외부 스킬을 설치합니다. `dependencies.json`이 설치 목록의 정본입니다.
FullOps의 Context7은 라이브러리 문서 조회용 MCP입니다. OCR은 delegate 준비용 CLI입니다.

```bash
python3 <설치된 플러그인>/scripts/deps.py --host codex  # claude-code, grok, agy
python3 <설치된 플러그인>/scripts/deps.py --check
```

에이전트에게 설치를 맡길 때는 다음 지시를 사용합니다.

```text
FullOps Squad를 GitHub 마켓플레이스 tourbut/Fullops-Squad-plugin에서 설치해줘.
README의 설치 절에서 현재 CLI 명령을 따르고 설치된 scripts/deps.py로 의존성을 설치·확인해줘.
설치 버전과 실패한 명령을 보고해줘. 서비스 레포 setup은 내가 별도로 요청할 때 실행해줘.
```

설치 후 새 에이전트 세션을 엽니다. 설치만으로 서비스 레포를 활성화하지 않습니다.

### 업데이트

에이전트에게 `FullOps update 수행해줘`라고 요청하면 됩니다. `update-fullops`가 현재 설치 버전을 먼저 기록하고, 업데이트 뒤 그 이후의 릴리스 내용을 읽어 이 레포에 필요한 변경까지 수행합니다. 레포 적용이 설치보다 뒤처졌으면 미적용 릴리스도 함께 확인합니다.

현재 CLI에 해당하는 명령을 실행합니다.

```bash
claude plugin marketplace update fullops-squad
claude plugin update fullops-squad@fullops-squad

codex plugin marketplace upgrade fullops-squad
codex plugin add fullops-squad@fullops-squad

grok plugin marketplace update
grok plugin update fullops-squad
```

업데이트 후 설치 버전과 `deps.py --check`를 확인합니다.
실행 중인 세션은 이전 hook 경로를 사용할 수 있습니다. 작업을 정리한 뒤 새 세션으로 전환합니다.
다른 PC와 Orca가 별도로 사용하는 CLI 홈도 갱신해야 합니다.

## 레포에 적용

기본 브랜치 체크아웃에서 시작합니다. 역할·모델·원격이 정해졌으면 그 설정을 사용합니다.
setup은 기존 문서를 덮어쓰지 않습니다. 필요한 기존 문서 변경은 템플릿과 비교해 반영합니다.

### 새 레포

```text
이 레포에 FullOps Squad를 setup하고 Orca 워크트리를 구성해줘.
1. 기본 브랜치와 작업 트리를 확인하고 기존 변경을 보존해.
2. 역할·책임·파일 소유권을 제안해. 미정 역할과 모델 후보만 나에게 확인해.
3. setup-fullops의 dry-run을 확인한 뒤 확정한 역할로 실행해.
4. project.md에 기술 기준과 검증 명령을 적고 기존 lint 도구와 review 규칙을 연결해.
5. orca-agents.md에 CLI·모델 후보·라우팅 기준을 등록하고 board.json에 실제 단계를 적어.
6. 문서 작성 규칙을 적용하고 준비 파일을 커밋·push해.
7. fullops-orca bootstrap으로 역할 워크트리를 만들고 준비 커밋과 .env 연결을 확인해.
8. orchestration Run을 만들고 PLANS.md에 run id를 남겨.
9. 역할·워크트리·브랜치·run id·미정 사항을 보고하고 첫 요청을 기다려.
```

### 기존 레포·플러그인 업데이트

업데이트 전용 세션에서 실행합니다. 이 세션은 coordinator로 이어 쓰지 않습니다.

```text
FullOps update 수행해줘.
```

설치 패키지에는 `INSTALL.md`와 `releases/`가 포함됩니다. 새 패키지의 `scripts/update.py --repo <레포 루트> --from <업데이트 전 실제 설치 버전>`은 해당 릴리스 본문과 수행할 내용을 출력합니다. 에이전트는 이를 읽고 적용 가능한 항목을 진행하며, 결과와 보류 사항을 `.fullops-squad/docs/exec-plans/phases/FULLOPS-UPDATE-<대상 버전>.md`에 남깁니다. 출력 스크립트 자체는 레포를 수정하지 않습니다.

`fullops.json`의 `plugin_version`은 레포 적용 버전입니다. 필수 적용과 관련 검증이 끝난 뒤 갱신합니다. 설치만 성공하거나 setup을 재실행한 상태는 적용 완료가 아닙니다. 기존 기록·제품 정지·진행 중 워크트리는 보존하고, 동기화는 안전한 시점에 수행합니다.

### 개발 요청

```text
요청: <기능 또는 수정 내용>
과제 키: <예: PLAYER-JUMP-1>
fullops-orca route로 분류하고 dispatch해줘.
```

## 설정

원본 체크아웃의 `.fullops-squad/.env.example`을 `.fullops-squad/.env`로 복사합니다.
`.env`와 API 키는 커밋하지 않습니다. 기존 레포에서도 ignore와 추적 여부를 확인합니다.

| 설정 | 기본값 | 의미 |
|---|---|---|
| `OPENROUTER_API_KEY` | 빈 값 | Jev 호출용 OpenRouter 키 |
| `FULLOPS_WORKER_CHECK_MINUTES` | `60` | 정상 작업 확인 주기, 분 |
| `FULLOPS_WORKER_READY_TIMEOUT_SECONDS` | `90` | worker 시작 준비 대기, 초 |
| `FULLOPS_WORKER_LOG_LIMIT` | `30` | 한 번 조회할 최근 메시지·줄 상한 |

운영 설정은 명령행(확인 주기만) → 프로세스 환경 변수 → 레포 `.env` → 기본값 순서입니다.
`orca_wait.py --repo . --settings`는 운영 설정만 출력합니다. API 키를 보려고 `.env` 전문을 읽지 않습니다.

### Jev

기본 모델은 `~typesafe/jev-latest`입니다. OpenRouter의 System One API를 사용합니다.
키는 `--env-file` → `OPENROUTER_API_KEY` 환경 변수 → `.fullops-squad/.env` 순서로 찾습니다.
동일 요청은 `~/.cache/fullops-squad/jev`에 캐시합니다. 비밀값으로 보이는 입력은 보내지 않습니다.

| 용도 | 실패·키 없음 처리 |
|---|---|
| 요청·역할·모델·산출물 라우팅 | 기존 구조는 설계 역할로 폴백. 제품/기술 분리 구조는 unresolved로 보류. 모델 폴백은 stderr 경고 확인 |
| 코드·문서 위치 탐색 | 검색으로 후보 보완 |
| 문서 관련성 분류 | 후보 유지 |
| 웹·Unity 조작 테스트 | 실패 근거 확인. 성공으로 처리하지 않음 |

`jev_route.py --strict`는 폴백 시 결과를 쓰지 않고 종료합니다.
재선정은 `--force`로 이전 결과를 보존합니다. simple 역할 수정은 `--override-role <역할> --reason <근거>`를 사용합니다.
Solar Decide로의 기본 모델 교체는 포함하지 않습니다.

### 워크트리와 grok

`env_link.py --all <원본 레포>`와 SessionStart hook이 미추적 `.fullops-squad/.env*`를 워크트리에 연결합니다.
기존 파일은 덮어쓰지 않습니다. Windows의 심볼릭 링크에는 개발자 모드 또는 필요한 권한이 있어야 합니다.
grok worker는 원본 레포의 폴더 신뢰가 필요합니다. `grok_trust.py --repo <레포> --check`로 확인합니다.
사용자가 허가하면 `/hooks-trust` 또는 `--add`로 등록합니다.

## 기록과 현황판

| 경로 (`.fullops-squad/` 기준) | 내용 |
|---|---|
| `FULLOPS.md`, `project.md`, `orca-agents.md` | 규약 지도, 프로젝트 기준, 역할·모델 배정 |
| `PLANS.md`, `board/board.json` | 과제와 프로젝트 단계 |
| `handovers/`, `contexts/` | 지시서·완료 기록, 역할별 결정과 교훈 |
| `docs/agents/document-writing.md` | front matter와 한국어 문장 규칙 |
| `docs/planning/`, `docs/design-docs/`, `docs/exec-plans/` | 기획·설계·실행 계획 |
| `docs/evaluations/` | Jev 결과, 테스트 시나리오, QA·리뷰 증거 |
| `docs/deliverables/README.md` | D01–D13 원천 매핑과 상태 |
| `lint/`, `review/` | 검사 명령·규칙과 리뷰 템플릿 |

`board/index.html`에 단계·과제·완료 이력·리뷰·테스트·산출물이 표시됩니다.
coordinator는 `board.json`을 관리하고 `board.py`는 기록에서 `board-data.js`를 생성합니다.
coordinator 종료 때 자동 갱신됩니다. 즉시 갱신하려면 `board.py --repo .`를 실행합니다.
`board-data.js`는 커밋하지 않습니다. HTML 양식은 플러그인이 관리합니다.

## 참고

- [구조 다이어그램](docs/diagrams/fullops-overview.html)
- [변경 이력과 기존 레포 적용](docs/releases/)
- [개발·빌드·검증](docs/development.md)
- [문서 작성 규칙](plugins/fullops-squad/assets/repository/.fullops-squad/docs/agents/document-writing.md)
- [lint 규약](plugins/fullops-squad/assets/repository/.fullops-squad/lint/README.md)
