---
title: FullOps Squad 개발
status: draft
updated: 2026-10-06
owner: maintainer
summary: 플러그인 원본 수정, 통합 설치기 패키징과 배포 검증 절차
---

# FullOps Squad 개발

플러그인 자체를 고치는 사람을 위한 문서다. 사용법은 [README](../README.md)를 본다.

## 구조

- `plugins/fullops-squad/`: Agent Plugins 1.0.0 표준 원본. `plugin.json`과 `mcp.json`이 공통 정본이다.
- `adapters/`: 호스트별 메타데이터.
- `dist/native/fullops-squad/`: `scripts/build.py`가 만드는 생성물. 직접 고치지 않는다. 루트 마켓플레이스 카탈로그가 이 경로를 가리키므로 호스트 검증 전에 빌드한다.
- `dist/directory/fullops-squad/`: 같은 빌드가 만드는 Anthropic 플러그인 디렉터리 제출판. native에서 다음을 바꾼다. hook은 `${CLAUDE_PLUGIN_ROOT}/hooks/run.sh`로 플러그인 안의 스크립트를 직접 실행하고, 의존 플러그인·Codex 메타데이터는 제거하고, Context7은 원격 https MCP와 선택 `userConfig` 키(`context7_api_key`)로 바꾸고, 영문 README와 LICENSE를 넣는다. 원본은 `adapters/claude-directory.json`과 `adapters/claude-directory/`다. 포털 제출 경로는 이 폴더이고, 제출 전 `claude plugin validate --strict dist/directory/fullops-squad`를 실행한다.
- 저장소에 `.gitattributes`를 두지 않는다. Anthropic 디렉터리 포털이 `text`·`eol`·`filter` 같은 내용 변환 속성을 거부해 `Couldn't validate that repository`가 난다. 줄바꿈은 LF로 커밋하며, Windows에서는 `git config core.autocrlf false`로 체크아웃한다. CI의 Windows 작업은 이 설정을 직접 건다.
- `dependencies.json`: 외부 스킬·MCP·도구의 출처와 설치 대상. 외부 구현은 이 레포에 복사하지 않는다.
- `docs/releases/`: 버전별 변경 범위와 기존 레포 적용 방법.

## 체크아웃에서 설치

개발 중인 체크아웃을 로컬 마켓플레이스로 등록해 바로 시험하거나, 마켓플레이스 등록 방법이 확인되지 않은 agy에 설치할 때 쓴다. 체크아웃 경로는 지우지 않는다.

```bash
git clone https://github.com/tourbut/Fullops-Squad-plugin.git
cd Fullops-Squad-plugin
python3 scripts/install.py --host codex --dry-run   # claude-code, grok, agy, all
python3 scripts/install.py --host codex
```

이미 GitHub 출처의 `fullops-squad`가 등록돼 있으면 출처 충돌로 멈춘다. 로컬 출처로 전환할 때 marketplace 제거는 설치 캐시도 지울 수 있으므로 실행 중 세션에서 바로 제거하지 않는다. 이전 cache의 원본을 먼저 보존하고 별도 신규 세션에서 전환한다. 기존 세션이 완전히 끝나기 전까지 그 hook 경로를 보존한다. 개발 directory 출처는 Claude가 dist를 직접 읽을 수 있으므로 검증 중 빌드로 실행 코드를 바꾸지 않는다.

설치기는 빌드한 뒤 플러그인 안의 `scripts/deps.py`와 같은 의존성 목록으로 의존성을 설치하고, 체크아웃을 로컬 마켓플레이스로 등록해 플러그인을 설치한다.

## 배포

### 통합 설치기

`bin/fullops-squad.cjs`는 Node.js 기본 모듈만 사용합니다. AI CLI 자체는 설치하지 않습니다.
플러그인은 GitHub 마켓플레이스에서 받습니다. 설치기는 npm에 게시하지 않고 `npx --yes github:tourbut/Fullops-Squad-plugin`으로 main에서 바로 실행합니다(`package.json`의 `private: true`). main에 병합하면 배포가 끝납니다.

1. `npm run test:installer`를 실행합니다. 설치·업데이트·실패 처리와 Windows 인자 전달을 확인합니다.
2. 병합 전 브랜치는 `npx --yes github:tourbut/Fullops-Squad-plugin#<브랜치> help`로 확인합니다.

npm의 `fullops-squad@1.0.1`은 예전에 게시한 판으로, 더 갱신하지 않습니다.

설치기 버전은 루트 `package.json`에서 관리합니다. GitHub 플러그인의 버전은 `plugins/fullops-squad/plugin.json`에서 관리합니다.
`--repo`는 설치된 플러그인의 `update.py`로 적용 안내를 출력합니다. 에이전트가 이후 레포 변경을 수행합니다.

### GitHub 마켓플레이스

GitHub 마켓플레이스가 커밋된 `dist/native/fullops-squad`를 가리킨다. 원본을 고치면 `python3 scripts/build.py`로 `dist/`를 다시 만들어 함께 커밋한다. CI는 빌드 결과가 커밋된 `dist/`와 다르면 실패한다. 버전을 올리고 `docs/releases/<버전>.md`에 변경 범위와 기존 레포 적용 방법을 적는다.

빌드는 README.md를 패키지의 INSTALL.md로, docs/releases/ 전체를 releases/로 포함한다. 각 릴리스의 `기존 레포 적용`에는 에이전트가 수행할 변경·검증·선택 조건을 적는다. `update-fullops`는 업데이트 전 설치 버전과 레포 적용 버전 중 오래된 기준 이후의 내용을 읽고 적용하므로 별도 버전별 지시문을 사용자에게 요구하지 않는다.

## 검증

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

`npm test`는 Python 회귀 검사와 표준 스키마 검사를 실행한다. setup·hook·스크립트 검사는 임시 레포에서 돌고, 공식 스키마 사본과 개발용 Ajv로 표준 형식을 검사하며 실행 중 스키마를 다운로드하지 않는다. agy 검증에는 MCP 실행 파일이 PATH에 있어야 한다. GitHub Actions는 기본 검사와 OCR CLI의 실제 delegate 검사를 별도 job으로 실행한다. 전체 Orca worker 기동은 별도 통합 검증이 필요하다.

Windows에서 로컬로 돌리려면 실제 `python3` 실행 파일(Microsoft Store 스텁이 아닌 것), `PYTHONUTF8=1`, 심볼릭 링크용 개발자 모드가 필요하다.

보드 문서 UI는 선택형 `python3 tests/board-browser.py [--channel chrome|msedge] [--out <캡처 디렉터리>]`로 검증한다. 테스트 환경에 Playwright Python 패키지와 해당 브라우저가 필요하다. file://·HTTP 열람, 여러 원천·누락 문서, 키보드 복귀와 상태 보존을 확인한다. 플러그인 실행 의존성에는 Playwright가 추가되지 않는다.

shadcn 연계는 선택형 `python3 tests/shadcn-lint.py --tools <검사 도구 폴더> [--out <결과.json>]`로 검증한다. 해당 폴더에 `npm install --prefix <검사 도구 폴더> --save-exact @shadcn/lint@0.2.0 eslint@9.33.0 @typescript-eslint/parser@8.40.0 tailwindcss@4.3.3`로 검증 버전을 설치한다. 이 버전은 재현용이며 서비스 레포에는 호환되는 지원 버전을 사용한다. Node.js 20.19 이상이 필요하며 샘플은 도구 폴더 안의 임시 Git 레포에 생성·삭제된다. 실제 플러그인의 위반 검출·정상 통과와 setup의 기존 스크립트 등록·FullOps 종료코드 게이트를 확인한다. FullOps 실행 의존성에는 이 패키지를 추가하지 않는다.

선택형 Jev 관찰 실험의 입력 형식과 실행 방법은 [Jev 관찰 실험](jev-observe.md)에 있다.

## 참고

- [Agent Plugins 표준 적용](agent-plugins-spec-review.md): 공통 배포 형식과 호스트 호환 패키지.
- [mattpocock/skills](https://github.com/mattpocock/skills): 배포와 레포별 setup 분리 방식 참고.
- [Claude Code 플러그인 의존성](https://code.claude.com/docs/en/plugin-dependencies): 네이티브 dependencies 및 cross-marketplace 허용 목록.
- [OpenAI 플러그인 패키징](https://developers.openai.com/plugins/build/plugins): Codex 패키지 구조 참고.
- [Antigravity CLI 플러그인·스킬](https://antigravity.google/docs/cli/plugins/): agy 패키지 형식과 사용자 스킬 경로.
- [skills CLI 호스트 매핑](https://github.com/vercel-labs/skills/blob/main/src/agents.ts): `grok`·`antigravity-cli` 설치 대상.

## 고정 hook 실행 경로

hook 명령은 Python의 사용자 홈에서 `.fullops-squad/runtime/fullops-squad/scripts/hook_runtime.py`를 실행한다. 호스트의 버전별 캐시나 작업 디렉터리에 의존하지 않는다. `deps.py --host`는 의존성 설치 전에 런타임을 준비하고 `--check --host`는 런타임 버전과 파일 존재도 확인한다. 외부 의존성 갱신 없이 복구할 때는 설치된 새 패키지의 `deps.py --runtime-only`를 사용한다.

`hook_runtime.py`는 동일 사용자 호스트가 공유하는 실행 진입점이다. 마지막으로 명시적으로 설치한 패키지를 사용한다. 전체 패키지 사본은 내용 해시별 `packages/`에 보존하고 `current.json`만 원자적으로 교체한다. hook 하나가 시작할 때 선택한 사본은 실행 도중 바뀌지 않는다. 기존 사본은 실행 중 hook·하위 프로세스가 사용할 수 있어 자동 삭제하지 않는다. 디스크 정리는 모든 호스트 세션을 종료한 뒤 수행한다. 이 런타임은 설치 캐시이며 사용자 설정이나 비밀값을 복사하지 않는다.

기존 버전 경로를 기억한 세션을 소급 변경할 수는 없다. 최초 전환은 런타임 준비 후 새 세션에서 수행한다. 호스트 자동 업데이트만으로 런타임 코드가 갱신되지는 않으므로 설치된 새 패키지의 deps 단계를 완료한다.
