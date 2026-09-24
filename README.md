# FullOps Squad

Orca에서 여러 AI 코딩 에이전트(Claude Code·Codex·grok·agy)를 한 팀으로 운영하는 하네스 플러그인입니다.

- **일정한 품질**: 어떤 모델이 작업해도 같은 지시서 형식, 같은 lint 관문, 같은 리뷰 기준을 거칩니다. 규칙은 hook이 강제합니다.
- **산출물이 남음**: 작업마다 지시서·검증 결과·리뷰·기획부터 이행까지의 산출물(D01–D13)이 레포에 기록됩니다.
- **비용 절감**: 저렴한 모델의 coordinator가 요청을 나누고, 비싼 모델은 설계가 필요할 때만 씁니다.

**Orca IDE가 필수입니다.** worker의 워크트리·터미널·메시지 전달과 완료 보고를 Orca가 맡습니다.
플러그인 설치와 레포 적용은 분리돼 있습니다. 설치만으로 다른 레포에 파일을 만들지 않습니다.

전체 구조는 [구조 다이어그램](docs/diagrams/fullops-overview.html)에서 볼 수 있습니다.

## 동작 방식

**역할**. 레포마다 setup에서 정합니다. 고정된 worker 세트는 없고, 아래 이름은 예시입니다.

| 역할 | 모델 | 하는 일 |
|---|---|---|
| coordinator | 저렴한 모델 | 요청을 분류해 배정하고, 완료 보고와 질문을 받고, 병합한다 |
| 설계 역할 (예: `architecture`) | 고급 모델 | 설계가 필요할 때만 띄운다. 설계 문서와 역할별 지시서를 쓰고 코드는 고치지 않는다 |
| worker (예: `dev`·`art`·`ops`) | 저렴한 모델 | 지시서대로 구현·검증한다 |

각 역할은 자기 워크트리와 `fullops/<역할>` 브랜치를 씁니다.

**요청 흐름**
1. coordinator가 `jev_route.py`로 요청을 분류합니다. Jev는 선택지마다 확률을 돌려주는 작은 판단 모델입니다.
2. simple이면 coordinator가 짧은 지시서를 써서 담당 역할에 바로 보냅니다. design이거나 확신이 낮으면 설계 역할이 설계와 지시서를 쓴 뒤 worker에게 넘깁니다. 이 요청으로 갱신할 산출물도 함께 고릅니다.
3. worker는 `orchestration worker-start --run`으로 띄워 작업합니다. 설계·범위 판단이 필요하면 `ask`로 묻고, coordinator가 설계 역할에게 전달해 답을 그대로 돌려줍니다.
4. worker가 `worker_done`으로 보고하면 coordinator가 delegate 리뷰와 lint 결과를 확인해 병합합니다.

**자동 규칙 (flow-gate hook)**. Claude Code·Codex·grok build에서 같은 스크립트가 행동 직전과 종료 직전에 검사합니다.
- 지시서를 터미널로 주입하는 배정, `--run` 없는 `worker-start`, Jev 분류 기록 없는 배정을 막습니다.
- 설계 역할의 코드 파일 수정을 막습니다.
- worker가 `worker_done` 없이, coordinator가 분류한 과제를 배정하지 않거나 worker 결과를 받지 않은 채 끝내려 하면 한 번 막습니다.
- 코드를 바꾸고 lint를 통과하지 않은 채 끝내려 하면 한 번 막습니다(done-gate).

hook은 셸 리다이렉션 같은 우회까지는 막지 못하고, hook 자체의 오류는 작업을 막지 않습니다.

**검증 관문**
- `scripts/lint.py`: 바뀐 파일에 레포의 lint 명령과 기본 검사(줄 수 증가, 범위 없는 억제, `eval`/`exec`, 하드코딩 비밀값, 산출물 front matter 형식)를 실행합니다. 기존 위반은 소급하지 않습니다. [lint 규약](plugins/fullops-squad/assets/repository/.fullops-squad/lint/README.md)
- `fullops-review`: SHA를 고정하고 Open Code Review(OCR) delegate로 파일·규칙을 준비한 뒤 호스트 AI가 리뷰합니다. 별도 OCR API 키는 필요 없습니다. 미해결 critical/high나 lint ERROR가 있으면 수락하지 않습니다.
- 공통 코딩·테스트·보안 기준은 [공통 규칙](plugins/fullops-squad/assets/repository/.fullops-squad/rules/common/README.md)으로 제공하며 프로젝트 기준이 우선합니다.

**작업 현황판**. 서비스 레포의 `.fullops-squad/board/index.html`을 브라우저로 열면 프로젝트 단계, 역할별 현재 과제, `PLANS.md`, 최근 완료, 리뷰 결과, 산출물 진행이 보입니다. 60초마다 새로고침하고 화이트·블랙 테마를 전환할 수 있습니다.
- coordinator는 `board/board.json`에 단계(완료·진행 중·막힘·예정)와 단계별 산출물 ID만 적습니다. 나머지는 `scripts/board.py`가 레포 기록에서 모읍니다.
- coordinator 세션이 끝날 때마다 자동 갱신됩니다. 바로 보려면 `python3 <플러그인>/scripts/board.py --repo .`를 실행합니다. 생성 파일 `board-data.js`는 커밋하지 않습니다.

**산출물**. 기획부터 이행까지 13종(D01–D13)을 `fullops-deliverables`가 관리합니다. 원천 문서 맨 위의 front matter(`id`·`title`·`status`·`updated`·`owner`·`tasks`·`upstream`·`downstream`·`summary`)는 모델이 손으로 쓰지 않고 `deliverables.py --stamp`로만 씁니다. 형식이 다르면 lint가 막습니다.

## 설치

필요 환경: Python 3.9+, Git 2.41+, Node.js 20.18.1+/npm/npx, 사용할 에이전트 CLI, **Orca IDE**. 설치기는 Orca를 설치하지 않습니다.

사용 중인 AI CLI에 아래 프롬프트를 붙여 넣으면 현재 CLI에 맞게 플러그인과 의존성을 설치합니다.

```text
FullOps Squad 플러그인을 https://github.com/tourbut/Fullops-Squad-plugin 에서 찾아 설치해줘. 저장소의 AGENTS.md 설치 지침을 읽고, 지금 사용 중인 AI CLI(Codex, Claude Code, grok, agy)에 맞는 호스트 하나를 선택해 플러그인과 의존성까지 설치하고 확인해줘. 서비스 레포의 하네스 setup은 내가 별도로 요청할 때 진행해줘.
```

직접 설치하려면 이 레포를 유지할 경로에 내려받고 설치기를 실행합니다. Codex·Claude Code는 이 경로를 로컬 마켓플레이스로 등록하므로 지우지 않습니다.

```bash
git clone https://github.com/tourbut/Fullops-Squad-plugin.git
cd Fullops-Squad-plugin
python3 scripts/install.py --host codex --dry-run   # 실행할 명령 확인
python3 scripts/install.py --host codex
```

`--host`는 `codex`, `claude-code`, `grok`, `agy`, `all` 중에서 고릅니다. 설치기는 플러그인과 함께 의존성(ponytail, mattpocock/skills, diagram-design, caveman, typesafe-ai, Open Code Review CLI·delegate 스킬, Context7 MCP)을 설치합니다. 출처는 [dependencies.json](dependencies.json)에 있습니다. 호스트의 플러그인 설치 버튼만으로는 사용자 범위 스킬과 CLI가 설치되지 않습니다.

설치하거나 업데이트한 뒤에는 새 에이전트 세션을 열어야 스킬과 hook이 적용됩니다.

## 레포에 적용

서비스 레포의 **기본 브랜치(main) 체크아웃**에서 Orca로 새 세션을 열고 아래 프롬프트를 붙여 넣습니다. `<>` 부분은 레포에 맞게 바꿉니다.

### 새 레포

```text
이 레포에 FullOps Squad를 처음 setup하고 Orca 워크트리까지 구성해줘. 지금 체크아웃은 기본 브랜치이고, 이 세션이 coordinator다.

1. 기본 브랜치이고 작업 트리가 깨끗한지 확인해. 아니면 멈추고 알려줘. Jev API 키가 없으면 Jev 없이 진행된다고 알려줘.
2. 레포의 코드·에셋·배포 구조를 보고 필요한 worker 역할을 제안해. 역할마다 책임과 담당 경로를 한 줄씩 적고, 내가 확정하면 설계 역할 architecture와 함께 그 역할로 setup-fullops를 실행해. 먼저 --dry-run으로 계획을 보여주고 실행해. 원격이 없으면 연결 정보만 물어봐.
3. project.md에 기술 기준·검증 명령을 채우고, 레포에 있는 lint 도구를 lint.json에 등록해. review/rule.json도 이 레포에 맞게 구성해.
4. orca-agents.md 배정표에 역할별 CLI·모델을 적어. coordinator는 <하위 모델>, architecture는 <상위 모델>, worker는 <하위 모델>이다. 미정인 것만 물어봐.
5. orca-agents.md의 "## 라우팅 기준"에서 설계 역할 줄과 역할별 책임 줄을 실제 역할에 맞게 고쳐.
6. board/board.json에 이 레포의 제목과 실제 진행 단계를 적어.
7. setup으로 생긴 파일을 기본 브랜치에 커밋하고 원격에 push해.
8. fullops-orca bootstrap으로 확정한 worker 역할마다 상설 워크트리를 fullops/<역할> 브랜치에서 만들어. 각 역할 브랜치에 방금 커밋한 setup을 반영해. architecture 워크트리도 만들되 세션은 띄우지 마. 설계가 필요할 때 worker-start로 띄운다.
9. 이번 작업에 쓸 orchestration Run을 만들고 run id를 PLANS.md에 적어.
10. 만든 워크트리·브랜치·run id·미정 사항을 보고하고 첫 요청을 기다려.
```

### 기존 레포

```text
이 레포는 이미 FullOps Squad를 쓰고 있다. 최신 플러그인 기준으로 setup을 갱신하고 Orca 워크트리를 맞춰줘. 지금 체크아웃은 기본 브랜치이고, 이 세션이 coordinator다.

1. 기본 브랜치이고 작업 트리가 깨끗한지 확인해. 아니면 멈추고 알려줘.
2. fullops.json의 기존 역할을 읽어. 모든 역할의 인박스(handovers/to_<역할>.md)와 PLANS.md에서 진행 중인 과제를 찾아 보고해. 진행 중 작업은 건드리지 마.
3. setup-fullops를 기존 역할로 다시 실행해. 먼저 --dry-run으로 보여주고, 새로 생기는 파일만 추가해. 사용자 문서와 기록은 보존해.
4. setup이 바꾸지 않는 기존 문서(handovers/_TEMPLATE.md, lint/lint.json, FULLOPS.md, docs/deliverables/README.md, orca-agents.md의 라우팅 기준)를 플러그인 템플릿과 비교해 빠진 절만 더해. 설계 역할은 <architecture>로 하고, 역할별 책임은 기존 배정표와 contexts/에서 가져와.
5. deliverables.py --repo . --strict의 경고가 없어질 때까지 원천 문서마다 deliverables.py --stamp로 front matter를 써. front matter를 손으로 쓰지 마.
6. board/board.json에 실제 진행 단계를 적고 board.py로 현황판을 만들어.
7. 변경을 기본 브랜치에 커밋하고 push해.
8. fullops-orca bootstrap으로 기존 워크트리를 조회해. 없는 역할의 워크트리만 만들어. 쉬고 있고 작업 트리가 깨끗한 역할 브랜치에만 기본 브랜치를 반영하고, 작업 중인 역할은 반영을 예약해.
9. orchestration Run을 만들거나 PLANS.md의 기존 run id를 확인해.
10. 워크트리·브랜치·run id·예약된 동기화·미정 사항을 보고하고 요청을 기다려.
```

### 플러그인 업데이트

새 버전이 나오면 기본 브랜치에서 **업데이트 전용 세션**을 열어 붙여 넣습니다. 이 세션은 시작할 때 읽은 옛 스킬·hook을 쓰므로 coordinator로 이어 쓰지 않습니다. 버전별로 레포에 반영할 내용은 [변경 이력](docs/releases/)에 있습니다.

```text
FullOps Squad 플러그인을 최신으로 올리고 이 레포에 적용해줘. 지금 체크아웃은 서비스 레포의 기본 브랜치다. 이 세션은 업데이트만 하는 세션이고 coordinator가 아니다. 요청을 받거나 worker를 dispatch하지 마.
0. 이 PC의 https://github.com/tourbut/Fullops-Squad-plugin 체크아웃을 찾아 git pull로 최신 main에 맞추고, AGENTS.md대로 지금 쓰는 CLI의 --host로 install.py를 --dry-run 후 실행해. 설치된 버전을 확인하고, grok은 버전이 그대로면 uninstall 후 --trust로 다시 설치해. 이후 단계의 스크립트와 템플릿은 갱신된 플러그인 경로(체크아웃의 dist/native/fullops-squad)에서 직접 실행하고 읽어.
1. 기본 브랜치이고 작업 트리가 깨끗한지 확인해. 아니면 멈추고 알려줘.
2. docs/releases/에서 이 레포의 plugin_version 이후 변경을 읽고 "기존 레포 적용" 항목을 정리해 보여줘.
3. setup-fullops를 기존 역할로 다시 실행해 새 파일만 추가하고, 정리한 항목 중 기존 문서에 직접 반영할 것을 반영해. 진행 중인 과제와 기록은 건드리지 마.
4. 변경을 기본 브랜치에 커밋하고 push해. 쉬고 있고 깨끗한 역할 브랜치에만 기본 브랜치를 반영해.
5. 반영한 내용과 미정 사항을 보고하고, 이 세션을 닫고 새 세션을 열어 coordinator로 쓰라고 안내해. 다른 PC와 실행 중인 worker 세션도 플러그인을 갱신하고 새 세션을 열어야 한다고 알려줘.
```

### 요청하기

setup 뒤에는 coordinator 세션에 이렇게 요청합니다. 분류·배정·대기는 스킬과 hook이 이어서 처리합니다.

```text
요청: <기능 또는 수정 내용>
과제 키: <예: PLAYER-JUMP-1>
fullops-orca route로 분류하고 dispatch해줘.
```

## 설정

### Jev API 키

Jev는 OpenRouter를 거쳐 호출하며 세 곳에서 씁니다. 키가 없어도 동작하지만 모든 요청이 설계 역할로 가서 고급 모델 비용이 늘어납니다.

| 스크립트 | 쓰는 곳 | 키가 없거나 실패하면 |
|---|---|---|
| `jev_route.py` | 요청을 simple·design으로 분류하고 갱신할 산출물을 고름 | 설계 역할로 보냄 |
| `jev_find.py` | 지시서를 쓸 때 관련 코드 위치 탐색 | 검색으로 후보를 정함 |
| `jev_context.py` | worker가 먼저 읽을 문서 선별 | 후보를 모두 유지 |

[OpenRouter](https://openrouter.ai/) 키를 쓰며 `--env-file`로 지정한 파일 → 환경 변수 `OPENROUTER_API_KEY` → 레포 루트 `.env`의 `OPENROUTER_API_KEY=` 줄 순서로 찾습니다. **레포 루트 `.env`에 넣는 방법이 가장 간단합니다.** 워크트리에도 자동으로 링크됩니다. 환경 변수로 쓰려면 Windows는 `setx OPENROUTER_API_KEY "sk-or-..."`, macOS·Linux는 셸 설정 파일에 `export`를 추가하고 Orca를 다시 시작합니다.

키를 레포에 커밋하거나 지시서·`orca-agents.md`에 적지 않습니다. 비밀값처럼 보이는 문자열이 섞인 요청은 Jev에 보내지 않고, 같은 요청의 응답은 `~/.cache/fullops-squad/jev`에 캐시해 다시 과금되지 않습니다.

### Orca 워크트리

**`.env` 연결**. git은 `.env`를 새 워크트리로 옮기지 않습니다. FullOps의 SessionStart hook이 워크트리에서 시작하는 모든 세션마다 원본 체크아웃 루트의 `.env*`(git 미추적) 중 빠진 것을 링크합니다. Orca 레포 설정의 설정 스크립트에도 아래 한 줄을 넣어 두면 워크트리를 만들 때 바로 연결됩니다. Windows(cmd.exe)·macOS·Linux에서 같은 줄을 씁니다.

```text
python3 -c "import os,pathlib as p;r=p.Path(os.environ['ORCA_ROOT_PATH']);w=p.Path(os.environ['ORCA_WORKTREE_PATH']);[(w/f.name).symlink_to(f) for f in r.glob('.env*') if f.is_file() and not (w/f.name).exists() and not (w/f.name).is_symlink()]"
```

- Windows는 개발자 모드(설정 → 시스템 → 개발자용)가 켜져 있어야 심볼릭 링크를 만들 수 있습니다. `python3`가 Microsoft Store 스텁이면 `py -3`로 바꿉니다.
- 서비스 레포의 `.gitignore`에 `.env`와 `.env.local`이 있는지 확인합니다.

**grok worker**. grok은 워크트리에서도 원본 레포 경로의 폴더 신뢰를 요구하고, 신뢰되지 않으면 착수 전에 멈춥니다. 원본 레포를 한 번 신뢰하면 모든 워크트리에 적용됩니다. grok에서 `/hooks-trust`를 실행하거나 `python3 <플러그인>/scripts/grok_trust.py --repo <레포> --add`로 추가합니다. coordinator는 grok을 배정하기 전에 `--check`로 확인하고 필요하면 사용자에게 묻습니다.

**coordinator를 역할 워크트리에서 운영할 때**. 기본은 기본 브랜치 체크아웃이 coordinator입니다. `coor` 같은 역할 워크트리에서 운영하려면 `orca-agents.md` 라우팅 기준에 `- coordinator 역할: `coor`` 줄을 둡니다. 그 브랜치의 세션이 coordinator 규칙과 현황판 갱신을 받고 배정 후보에서 빠집니다.

## 레포에 생기는 파일

setup은 선택한 레포에 `.fullops-squad/`를 만듭니다.

```text
.fullops-squad/
  fullops.json                 # 이 레포의 활성화 표식, 역할·브랜치 정본
  FULLOPS.md                   # 규약 지도
  project.md, orca-agents.md   # 프로젝트 기준, 역할 배정과 라우팅 기준
  PLANS.md                     # 현재 할 일
  board/                       # 작업 현황판(index.html 고정, board.json은 coordinator가 관리)
  rules/common/                # 공통 코딩·테스트·보안 기준
  handovers/to_<role>.md       # 역할별 지금 할 일
  handovers/logs/              # 지시서·완료 보고 전문
  contexts/<role>.md           # 역할별 결정·교훈 요약
  lint/lint.json, README.md    # lint 명령·기본 검사 설정과 규약
  review/                      # OCR 규칙과 리뷰 보고서 템플릿
  docs/
    planning/, design-docs/, exec-plans/, operations/, generated/
    evaluations/               # Jev 분류·QA·리뷰 기록
    deliverables/              # 산출물 13종 인덱스
    agents/                    # 외부 엔지니어링 스킬의 레포 설정
```

## 참고

- [구조 다이어그램](docs/diagrams/fullops-overview.html)
- [변경 이력](docs/releases/): 버전별 변경 범위와 기존 레포 적용 방법
- [개발 문서](docs/development.md): 플러그인 구조, 빌드와 검증
