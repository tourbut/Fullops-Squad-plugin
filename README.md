# FullOps Squad

Orca에서 Codex·Claude Code·grok·agy worker에게 작업을 전달하고, **개발 산출물과 작업 기록을 레포에 남기는 하네스 플러그인**입니다.
**Orca IDE가 필수입니다.** worker의 워크트리·터미널·메시지 전달과 완료 보고를 Orca가 맡기 때문에 Orca 없이는 동작하지 않습니다.
고성능 모델이 기획·설계를 맡고 비용이 낮은 모델이 명확한 지시서에 따라 구현하도록 구성하는 것이 목적입니다. 모델 선택은 프로젝트의 역할 배정과 Orca 실행 설정에서 관리합니다.
플러그인 설치와 레포 활성화를 분리합니다. 설치만으로 다른 레포에 AGENTS.md나 문서 디렉터리를 만들지 않습니다.

## 0.7.4 배정 누락 방지

coordinator가 Jev로 분류한 과제를 배정하지 않고 세션을 끝내려 하면 flow-gate가 한 번 막습니다. 대화 요약 뒤 배정을 잊는 문제를 막습니다. [변경 범위](docs/releases/0.7.4.md)

## 0.7.3 Windows Jev 호출 수정

Windows에서 Jev 호출이 curl exit 26으로 실패하던 문제를 고쳤습니다. 키는 환경 변수가 없으면 레포 루트 `.env`에서도 읽습니다. [변경 범위](docs/releases/0.7.3.md)

## 0.7.2 워크트리 .env 자동 연결

에이전트가 만든 워크트리에도 원본 체크아웃 루트의 `.env*`가 자동으로 링크됩니다. 워크트리에서 시작하는 세션마다 SessionStart hook이 빠진 파일을 연결합니다. [변경 범위](docs/releases/0.7.2.md)

## 0.7.1 역할 워크트리 coordinator

coordinator를 역할 워크트리(예: `coor`)에서 운영하면 `orca-agents.md` 라우팅 기준에 `- coordinator 역할: `<역할>`` 줄을 둡니다. 그 브랜치의 세션이 coordinator 규칙과 현황판 자동 갱신을 받고 배정 후보에서 빠집니다. [변경 범위](docs/releases/0.7.1.md)

## 0.7.0 작업 현황판·산출물 메타정보

`.fullops-squad/board/index.html`에서 프로젝트 단계, 역할별 과제, 리뷰, 산출물 진행을 눈으로 확인합니다. coordinator 세션이 끝날 때마다 자동으로 갱신됩니다. 산출물 원천 문서의 front matter는 `deliverables.py --stamp`로만 쓰고 lint `DOC-002`가 형식을 검사해, 모델이 달라도 같은 형식으로 남습니다. Jev가 요청마다 갱신할 산출물도 고릅니다. [변경 범위·기존 레포 적용](docs/releases/0.7.0.md)을 확인하세요.

## 0.6.0 coordinator 라우팅·flow-gate

비용이 낮은 모델의 coordinator가 `jev_route.py`로 요청을 분류합니다. simple은 담당 역할에 바로 보내고, design은 설계 역할이 지시서를 쓴 뒤 worker에게 넘깁니다. worker는 `worker-start --run`으로만 띄워 완료 보고가 요청자에게 돌아오게 합니다. flow-gate hook이 Claude Code·Codex·grok build에서 이 흐름을 강제합니다. Windows 호환도 보강했습니다. [변경 범위·기존 레포 적용](docs/releases/0.6.0.md)을 확인하세요.

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

Python 3.9+, Git 2.41+, Node.js 20.18.1+/npm/npx, 사용할 에이전트 CLI, 그리고 **Orca IDE(필수)**가 필요합니다. 설치기는 Orca를 설치하지 않으니 먼저 설치하세요.
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
| Context7 | FullOps MCP 서버 | FullOps MCP 서버 | FullOps MCP 서버 |
| Open Code Review delegate | CLI + 사용자 범위 스킬 | CLI + 사용자 범위 스킬 | CLI + 사용자 범위 스킬 |
| Orca CLI 가이드 | 설치된 Orca에서 동적으로 조회 | 동일 | 동일 |

설치기는 표준 원본에서 `dist/native/fullops-squad/`를 먼저 생성합니다. Codex·Claude Code의 마켓플레이스와 grok·agy의 `plugin install <로컬 경로>`는 이 호스트 호환 패키지를 사용합니다. grok·agy의 위 외부 스킬 의존성은 사용자 범위로 설치합니다.
agy의 npx 대상은 IDE용 `antigravity`가 아닌 `antigravity-cli`이며 경로는 `~/.gemini/antigravity-cli/skills/`입니다. grok은 `~/.grok/skills/`를 사용합니다.

프런트엔드 디자인·웹 테스트 등 범용 스킬은 각 호스트(Claude Code·Codex)의 기본 제공 스킬을 사용하며 이 하네스에서 설치하지 않습니다.
caveman은 Codex·Claude Code에서 FullOps 플러그인을 활성화한 새 세션(`startup`·`clear`)에 `full`로 적용됩니다. SessionStart 훅이 설치된 스킬을 읽으며 외부 규칙을 복제하지 않습니다. `/caveman off`로 해제할 수 있고, 재개·압축 시에는 다시 활성화하지 않습니다. grok·agy는 스킬 설치만 지원하므로 명시적으로 호출합니다. typesafe-ai는 Jev의 문맥 선별·증거 대조 등 의미 판단 기능을 개발·유지보수할 때 사용하는 가이드입니다. Jev 실행 자체의 런타임 의존성은 아니며, 스킬 설치는 API 호출을 활성화하거나 API 키를 설정하지 않습니다.
외부 스킬·MCP 구현을 이 레포에 복사하지 않습니다. 출처와 설치 대상은 [dependencies.json](dependencies.json)에서 관리합니다.
이미 같은 스킬을 다른 출처로 설치했다면 중복 설치 경로를 정리해 한 출처만 사용하세요. 설치기는 기존 사용자 스킬을 삭제하지 않습니다.

**호스트의 설치 버튼만으로 모든 외부 스킬이 설치되는 것은 아닙니다.** Claude Code의 플러그인 의존성은 네이티브 자동 설치를 사용하지만, 사용자 범위 스킬과 Codex의 보완 설치는 위 통합 설치기가 수행합니다. 현재 구현의 전체 설치 진입점은 `scripts/install.py`입니다.
Context7도 통합 설치기가 `@upstash/context7-mcp@4.1.1`을 설치하고 네 CLI에 `context7-mcp` stdio 서버로 연결합니다. 기본 사용은 키 없이 시작하며, 높은 호출 한도가 필요하면 MCP 프로세스에 `CONTEXT7_API_KEY`를 제공하도록 사용하는 호스트의 환경/비밀 설정을 사용합니다. 키를 레포나 지시서에 기록하지 않습니다. 연결·조회 실패는 설치 성공과 구분해 확인합니다. [Context7 설정 안내](https://context7.com/docs/resources/all-clients)
외부 의존성은 일반 도구로 전역 설치됩니다. 이 플러그인의 레포별 활성화 조건은 외부 플러그인의 자체 동작까지 비활성화하지 않습니다.

## Jev 설정

FullOps는 TypeSafe의 판단 모델 Jev(`~typesafe/jev-latest`, OpenRouter 경유)를 세 곳에서 씁니다. Jev는 선택지마다 확률을 돌려주는 작고 저렴한 모델입니다.

| 스크립트 | 쓰는 곳 | 키가 없거나 실패하면 |
|---|---|---|
| `jev_route.py` | coordinator가 요청을 simple·design으로 분류하고, 갱신할 산출물(D01–D13)을 고름 | 설계 역할로 보내고 산출물은 추천하지 않음 |
| `jev_find.py` | 지시서를 쓸 때 관련 코드 위치 탐색 | 검색으로 후보를 정함 |
| `jev_context.py` | worker가 먼저 읽을 문서 선별 | 후보를 모두 유지 |

키가 없어도 FullOps는 동작합니다. 다만 라우팅이 항상 설계 쪽으로 가서 상위 모델 비용이 늘어납니다.

**API 키 넣는 곳**: [OpenRouter](https://openrouter.ai/)에서 발급한 키를 쓰며, 스크립트는 `--env-file`로 지정한 파일 → 환경 변수 `OPENROUTER_API_KEY` → 레포 루트 `.env`의 `OPENROUTER_API_KEY=` 줄 순서로 찾습니다. 레포 루트 `.env`에 넣어 두면 워크트리에도 자동 링크되므로 가장 간단합니다. 환경 변수로 쓰려면 아래처럼 등록합니다. 에이전트 세션은 Orca가 띄우므로, Orca가 물려받는 사용자 환경에 넣고 **Orca를 다시 시작**해야 합니다.

- Windows: `setx OPENROUTER_API_KEY "sk-or-..."` 실행 후 Orca 재시작
- macOS·Linux: `~/.zshrc` 또는 `~/.bashrc`에 `export OPENROUTER_API_KEY="sk-or-..."`를 추가하고 Orca 재시작. Dock에서 실행한 Orca가 셸 설정을 읽지 않으면 터미널에서 Orca를 실행합니다.
- 환경 변수 대신 파일을 쓰려면 스크립트에 `--env-file <경로>`를 넘깁니다. 파일에서 `OPENROUTER_API_KEY=...` 줄만 읽고 코드로 실행하지 않습니다. 파일은 레포 밖에 두거나 `.gitignore`에 넣습니다.

키를 레포, 지시서, `orca-agents.md`에 적지 않습니다. 스크립트는 비밀값처럼 보이는 문자열이 섞인 요청을 Jev에 보내지 않습니다. 같은 요청의 응답은 `~/.cache/fullops-squad/jev`(`FULLOPS_JEV_CACHE`로 변경 가능)에 캐시되어 다시 과금되지 않습니다.

## 작업 현황판

사람이 프로젝트 진행 상황을 눈으로 확인하는 페이지입니다. 서비스 레포의 `.fullops-squad/board/index.html`을 브라우저로 열면 됩니다. 60초마다 새로고침합니다.

- **양식은 고정**: `index.html`은 플러그인이 제공하며 고치지 않습니다.
- **단계는 coordinator가 관리**: `board/board.json`에 제목, 요약, 프로젝트 단계(상태: 완료·진행 중·막힘·예정)와 단계별 산출물 ID를 적습니다. 단계를 추가하면 현황판에도 늘어납니다.
- **나머지는 자동 수집**: 역할별 현재 과제(인박스), `PLANS.md`, 완료 이력(작업 로그), Jev 분류, 리뷰·lint 결과, 산출물 D01–D13 상태와 원천 문서 유무를 `scripts/board.py`가 레포 기록에서 모아 `board/board-data.js`로 만듭니다.
- **자동 갱신**: coordinator 세션이 끝날 때마다 flow-gate hook이 데이터를 다시 만듭니다. 바로 보려면 `python3 <플러그인>/scripts/board.py --repo .`를 실행합니다.
- `board-data.js`는 `board/.gitignore`로 커밋하지 않습니다. 다른 PC에서는 한 번 실행하면 생깁니다.
- **산출물 메타정보**: 산출물 원천 문서 맨 위의 front matter(`id`·`title`·`status`·`updated`·`owner`·`tasks`·`upstream`·`downstream`·`summary`)를 현황판이 인덱스 표보다 우선해서 읽습니다. front matter는 모델이 손으로 쓰지 않고 `deliverables.py --stamp`로만 씁니다. 필드 순서·목록 표기·갱신일이 고정되고 인덱스 표의 상태도 함께 맞춰집니다. 바뀐 원천 문서가 이 형식과 다르면 lint `DOC-002` ERROR로 worker 종료와 병합이 막힙니다. Jev 산출물 라우팅도 이 `title`·`summary`로 판단합니다.

## Orca 설정

FullOps는 Orca IDE가 있어야 동작합니다. worker 워크트리, 에이전트 터미널, orchestration 메시지와 완료 보고를 모두 Orca가 관리합니다. 서비스 레포는 Orca에 등록해서 열고, coordinator 세션도 Orca 안에서 시작합니다.

**워크트리 설정 스크립트: `.env` 연결**

git은 `.env`를 새 워크트리로 옮겨 주지 않습니다. Orca 레포 설정의 설정 스크립트(새 워크트리를 만든 뒤 실행)에 아래 한 줄을 넣으면, 원본 체크아웃(`ORCA_ROOT_PATH`)의 `.env*` 파일이 새 워크트리(`ORCA_WORKTREE_PATH`)에 심볼릭 링크로 연결됩니다. 워크트리에 이미 같은 이름이 있으면 건너뛰므로 git이 관리하는 `.env.example`은 바뀌지 않습니다.

```text
python3 -c "import os,pathlib as p;r=p.Path(os.environ['ORCA_ROOT_PATH']);w=p.Path(os.environ['ORCA_WORKTREE_PATH']);[(w/f.name).symlink_to(f) for f in r.glob('.env*') if f.is_file() and not (w/f.name).exists() and not (w/f.name).is_symlink()]"
```

- Windows, macOS, Linux에서 같은 줄을 씁니다. 환경 변수를 셸이 아니라 Python이 읽기 때문에, Orca가 Windows에서 설정 스크립트를 실행하는 cmd.exe에서도 동작합니다. PowerShell 문법(`$env:`, `ForEach-Object`)은 cmd.exe에서 실패합니다.
- Windows는 개발자 모드(설정 → 시스템 → 개발자용)가 켜져 있어야 관리자 권한 없이 심볼릭 링크를 만들 수 있습니다. `python3`가 Microsoft Store 스텁이면 `py -3`로 바꿉니다.
- 서비스 레포의 `.gitignore`에 `.env`와 `.env.local`이 있는지 확인합니다. 링크도 워크트리 안에서는 일반 파일처럼 보입니다.
- 에이전트가 `git worktree add`나 설정 생략 옵션으로 만든 워크트리는 설정 스크립트가 돌지 않습니다. 그래서 FullOps의 SessionStart hook이 워크트리에서 시작하는 모든 세션마다 원본 체크아웃 루트의 `.env*`(git 미추적) 중 빠진 것을 링크합니다(링크 불가 시 복사). 직접 실행하려면 `python3 <플러그인>/scripts/env_link.py --all <레포 루트>`입니다.

## 시작 프롬프트

서비스 레포의 **기본 브랜치(main) 체크아웃**에서 새 에이전트 세션을 열고 아래 프롬프트를 붙여 넣습니다. 이 체크아웃이 coordinator가 됩니다. coordinator는 비용이 낮은 모델로 여는 것을 권합니다.
flow-gate는 역할 브랜치(`fullops/<역할>`)가 아닌 브랜치를 coordinator로 판정합니다. 따라서 coordinator 세션은 항상 기본 브랜치에서 시작합니다.
`<>` 부분은 레포에 맞게 바꿉니다. worker 구성은 레포마다 다르며, 새 레포에서는 에이전트가 레포를 보고 worker 역할을 제안한 뒤 확정하고 setup합니다. 아래 dev·art·ops 같은 이름은 예시입니다. Orca IDE 안에서 세션을 열어야 합니다.

### 새 레포

```text
이 레포에 FullOps Squad를 처음 setup하고 Orca 워크트리까지 구성해줘. 지금 체크아웃은 기본 브랜치이고, 이 세션이 coordinator다.

1. 기본 브랜치이고 작업 트리가 깨끗한지 확인해. 아니면 멈추고 알려줘. OPENROUTER_API_KEY가 없으면 Jev 없이 진행된다고 알려줘.
2. 레포의 코드·에셋·배포 구조를 보고 필요한 worker 역할을 제안해. 역할마다 책임과 담당 경로를 한 줄씩 적고, 내가 확정하면 설계 역할 architecture와 함께 그 역할로 setup-fullops를 실행해. 먼저 --dry-run으로 계획을 보여주고 실행해. 원격이 없으면 연결 정보만 물어봐.
3. project.md에 기술 기준·검증 명령을 채우고, 레포에 있는 lint 도구를 lint.json에 등록해. review/rule.json도 이 레포에 맞게 구성해.
4. orca-agents.md 배정표에 역할별 CLI·모델을 적어. coordinator는 <하위 모델>, architecture는 <상위 모델>, worker는 <하위 모델>이다. 미정인 것만 물어봐.
5. orca-agents.md의 "## 라우팅 기준"에서 설계 역할 줄과 역할별 책임 줄을 실제 역할에 맞게 고쳐.
6. setup으로 생긴 파일을 기본 브랜치에 커밋하고 원격에 push해.
7. fullops-orca bootstrap으로 확정한 worker 역할마다 상설 워크트리를 fullops/<역할> 브랜치에서 만들어. 각 역할 브랜치에 방금 커밋한 setup을 반영해. architecture 워크트리도 만들되 세션은 띄우지 마. 설계가 필요할 때 worker-start로 띄운다.
8. 이번 작업에 쓸 orchestration Run을 만들고 run id를 PLANS.md에 적어.
9. 만든 워크트리·브랜치·run id·미정 사항을 보고하고 첫 요청을 기다려.
```

### 기존 레포

```text
이 레포는 이미 FullOps Squad를 쓰고 있다. 최신 플러그인 기준으로 setup을 갱신하고, coordinator 구조로 Orca 워크트리를 다시 맞춰줘. 지금 체크아웃은 기본 브랜치이고, 이 세션이 coordinator다.

1. 기본 브랜치이고 작업 트리가 깨끗한지 확인해. 아니면 멈추고 알려줘.
2. fullops.json의 기존 역할을 읽어. 모든 역할의 인박스(handovers/to_<역할>.md)와 PLANS.md에서 진행 중인 과제를 찾아 보고해. 진행 중 작업은 건드리지 마.
3. setup-fullops를 기존 역할로 다시 실행해. 먼저 --dry-run으로 보여주고, 새로 생기는 파일만 추가해. 사용자 문서와 기록은 보존해.
4. orca-agents.md에 "## 라우팅 기준" 섹션이 없으면 플러그인 템플릿 형식으로 추가해. 설계 역할은 <architecture>로 하고, worker 역할은 fullops.json에 이미 등록된 역할을 그대로 쓰되 빠진 역할이 필요하면 제안해. 역할별 책임은 기존 배정표와 contexts/에서 가져와. 배정표에 coordinator(<하위 모델>)를 추가하고 architecture는 필요할 때만 띄우는 설계 역할로 바꿔.
5. 변경을 기본 브랜치에 커밋하고 push해.
6. fullops-orca bootstrap으로 기존 워크트리를 조회해. 없는 역할의 워크트리만 만들어. 쉬고 있고 작업 트리가 깨끗한 역할 브랜치에만 기본 브랜치를 반영해. 작업 중인 역할은 반영을 예약하고 보고해.
7. 지금까지 architecture가 터미널로 띄운 worker가 있으면 목록을 보고해. 다음 과제부터는 worker-start --run으로 띄운다.
8. orchestration Run을 만들거나 PLANS.md의 기존 run id를 확인해.
9. 워크트리·브랜치·run id·예약된 동기화·미정 사항을 보고하고 요청을 기다려.
```

### 기존 레포 0.7.0 업데이트

FullOps를 이미 쓰는 레포에 0.7.0을 적용합니다. 서비스 레포의 기본 브랜치 체크아웃에서 **업데이트 전용 세션**을 열어 붙여 넣으면 플러그인 갱신부터 레포 적용까지 진행합니다. 이 세션은 시작할 때 읽은 옛 스킬·hook을 계속 쓰므로 coordinator로 이어 쓰지 않습니다. 갱신 뒤 스크립트는 새 플러그인 경로에서 직접 실행하고, 끝나면 새 세션을 열어 coordinator로 씁니다.

```text
FullOps Squad 플러그인을 0.7.0으로 올리고 이 레포에 적용해줘. 지금 체크아웃은 서비스 레포의 기본 브랜치다. 이 세션은 업데이트만 하는 세션이고 coordinator가 아니다. 요청을 받거나 worker를 dispatch하지 마.
0. 플러그인 갱신: 이 PC의 https://github.com/tourbut/Fullops-Squad-plugin 체크아웃을 찾아 git pull로 최신 main에 맞추고, 저장소 AGENTS.md대로 지금 쓰는 CLI의 --host로 install.py를 --dry-run 후 실행해. Codex와 Claude Code는 설치된 플러그인 버전이 0.7.0인지 확인하고, grok은 plugin details에서 v0.7.0이 아니면 uninstall 후 --trust로 다시 설치해. 이 세션은 옛 스킬을 쓰고 있으니 이후 단계의 scripts/*.py와 템플릿은 갱신된 플러그인 경로(체크아웃의 dist/native/fullops-squad)에서 직접 실행하고 읽어.
1. 기본 브랜치이고 작업 트리가 깨끗한지 확인해. 아니면 멈추고 알려줘.
2. 모든 인박스(handovers/to_<역할>.md)와 PLANS.md에서 진행 중인 과제를 찾아 보고해. 건드리지 마.
3. setup-fullops를 fullops.json의 기존 역할 그대로 다시 실행해. --dry-run으로 먼저 보여주고, 새 파일(.fullops-squad/board/)만 추가하고 기존 문서와 기록은 보존해.
4. setup이 바꾸지 않는 파일을 플러그인 템플릿과 비교해 필요한 부분만 더해.
   - handovers/_TEMPLATE.md: "## 갱신할 산출물" 절
   - lint/lint.json: exclude에 ".fullops-squad/board/**"
   - FULLOPS.md: 현황판 행
   - docs/deliverables/README.md: front matter 절(--stamp 규칙). 기존 행과 상태는 보존
   - orca-agents.md에 "## 라우팅 기준"이 없으면 템플릿 형식으로 추가
5. board/board.json을 이 레포에 맞게 써. title과 summary, 그리고 PLANS.md와 개발계획 문서에서 실제 프로젝트 단계와 상태를 옮기고, 단계마다 관련 산출물 ID를 연결해.
6. deliverables.py --repo . --strict를 실행해. 경고가 난 원천 문서마다 deliverables.py --stamp로 front matter를 써. 처음 쓰는 문서는 --owner와 --summary를 문서 내용에서 정하고, 원천이 폴더이거나 여러 파일이면 --path를 붙여. 본문에 있던 자유 형식 "상태·갱신일" 줄은 front matter로 옮긴 뒤 지워. --strict 결과가 0이 될 때까지 반복해. front matter를 손으로 쓰지 마.
7. board.py --repo .를 실행하고 board/index.html 경로를 알려줘.
8. 변경을 기본 브랜치에 커밋하고 push해. 쉬고 있고 작업 트리가 깨끗한 역할 브랜치에만 기본 브랜치를 반영하고, 작업 중인 역할은 반영을 예약해.
9. 추가·수정한 파일, stamp한 산출물, 예약된 동기화, 미정 사항을 보고해. 이 세션을 닫고 새 세션을 열어 coordinator로 쓰라고 안내해. 새 스킬·hook(현황판 자동 갱신·DOC-002)은 새 세션부터 적용되니, 다른 PC와 worker 세션도 플러그인을 갱신하고 새 세션을 열어야 한다고 함께 알려줘.
```

### setup 뒤 요청

coordinator 세션에 요청할 때는 아래 형식을 씁니다. route, dispatch, 대기는 스킬과 flow-gate가 이어서 처리합니다.

```text
요청: <기능 또는 수정 내용>
과제 키: <예: PLAYER-JUMP-1>
fullops-orca route로 분류하고 dispatch해줘.
```

## 작업 흐름

역할은 레포별 setup에서 제품·기술·규모에 맞게 구성합니다. 고정된 worker 세트는 없으며, 문서의 dev·art·ops는 예시입니다. `fullops.json`에 역할과 브랜치를 등록하고 역할별 인박스·컨텍스트를 생성합니다. GitHub remote의 기준 브랜치에서 `fullops/<역할 ID>` 원격 브랜치를 만들며, 기존 브랜치와 작업 기록은 보존합니다. CLI·모델 배정은 `orca-agents.md`에서 관리합니다.

setup 재실행은 저장된 remote·기준 브랜치를 재사용하며 명시적 옵션으로 변경할 수 있습니다. 원격 연결된 레포의 새 역할은 원격 setup으로 추가합니다. 로컬 전용 모드에서는 해당 레포의 기존 역할과 문서만 유지합니다.

1. `fullops-work`: 실제 상태 확인 → 역할별 지시서·완료 기준·산출물·복귀 주소 작성 → 먼저 읽을 문서 선정(선택: Jev 분류).
2. `fullops-orca dispatch`: 별도 worker 세션에 전달 → 실제 지시서 가시성과 착수 확인 → `orca_wait.py`로 heartbeat·status 알림 없이 대기.
3. worker: 구현·검증·lint 게이트 통과·원천 문서 갱신 → 로그 아카이브 → 컨텍스트 요약 → 부모에게 직접 회신.
4. `fullops-review`: SHA 고정 → OCR delegate 파일·규칙 준비 → AI 검토 → worker 체크아웃 lint 결과 기록 → 통일된 보고서·기록 검사. OCR 제외 파일도 검토하거나 생략 사유를 남깁니다.
5. 병합 책임자: 리뷰·브랜치·SHA·diff·검증 확인 → 허가된 병합 → 쉬고 있는 worker 브랜치 동기화.
6. `fullops-deliverables`: 기획부터 이행까지 D01–D13 원천 문서와 납품용 인덱스 관리.

OCR CLI는 `@alibaba-group/open-code-review@latest`(설치 시점 최신)로 설치하고 자동 업데이트를 끈 상태로 delegate 명령을 실행합니다. 별도 OCR API 키 없이 호스트 AI가 리뷰하며 해당 AI의 사용량은 발생합니다. 레포별 `review/rule.json`으로 테스트·문서·게임 자산의 기본 제외를 보완합니다. 리뷰 기록 검사 통과는 검토 내용과 테스트 성공을 자동 보증하지 않습니다.

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
coordinator는 `jev_route.py`로 요청을 simple(담당 역할에 직접 지시)과 design(설계 역할에 먼저 맡김)으로 나눕니다. 판단 기준은 `orca-agents.md`의 `## 라우팅 기준`이고, 이 섹션이 Jev에 전달됩니다. 확신이 낮거나 호출이 실패하면 설계 역할로 보냅니다. worker의 설계 질문은 coordinator가 설계 역할에게 전달하고, 받은 답을 그대로 회신합니다. 기존 레포는 `orca-agents.md`에 이 섹션을 직접 추가해야 합니다.
flow-gate hook(`flow_gate.py`)이 이 흐름을 강제합니다. Claude Code·Codex·grok build에서 동작하며, 현재 브랜치로 역할을 판정합니다.
- 공통: 지시서의 터미널 주입과 `--run` 없는 `worker-start`를 차단합니다.
- coordinator: route 기록 없는 dispatch, route와 맞지 않는 지시서 작성을 차단합니다.
- 설계 역할: 코드 파일 수정을 차단합니다.
- dispatched worker: `worker_done`·`escalation` 없이 끝내면 한 번 막습니다.

셸 리다이렉션 같은 우회까지는 막지 못하며, hook 오류는 작업을 막지 않습니다.

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

- [구조 다이어그램](docs/diagrams/fullops-overview.html): 품질 관문과 산출물, 역할 구조, 요청 라우팅, 질문 전달, flow-gate 규칙.
- [Agent Plugins 표준 적용](docs/agent-plugins-spec-review.md): 공통 배포 형식과 호스트 호환 패키지.
- [mattpocock/skills](https://github.com/mattpocock/skills): 배포와 레포별 setup 분리 방식 참고.
- [Claude Code 플러그인 의존성](https://code.claude.com/docs/en/plugin-dependencies): 네이티브 dependencies 및 cross-marketplace 허용 목록.
- [OpenAI 플러그인 패키징](https://developers.openai.com/plugins/build/plugins): Codex 패키지 구조 참고.
- [Antigravity CLI 플러그인·스킬](https://antigravity.google/docs/cli/plugins/): agy 패키지 형식과 사용자 스킬 경로.
- [skills CLI 호스트 매핑](https://github.com/vercel-labs/skills/blob/main/src/agents.ts): `grok`·`antigravity-cli` 설치 대상.
