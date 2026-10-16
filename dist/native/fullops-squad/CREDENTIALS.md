# API 키와 인증 정보

FullOps Squad가 사용하는 외부 서비스의 키·로그인을 한곳에 정리한다. 모든 항목은 선택이다. 없으면 해당 기능만 폴백하거나 실패를 보고하며, 플러그인 설치와 setup은 키 없이 완료된다. 키와 `.env`는 커밋하지 않는다.

## 요약

| 항목 | 쓰는 기능 | 권장도 | 없을 때 | 설정 위치 | 전송 대상 |
|---|---|---|---|---|---|
| Jev 키: `TYPESAFE_API_KEY` 또는 `OPENROUTER_API_KEY` (하나만 있으면 된다) | Jev 라우팅·탐색·분류·조작 테스트 | coor 운영에 강력 권장 | 라우팅은 설계 역할 폴백(제품/기술 분리 구조는 unresolved 보류). 탐색은 로컬 검색으로 보완 | `--env-file` → 환경 변수 → `.fullops-squad/.env` | 공식 API `https://api.typesafe.ai/v1/systemone` 또는 `https://openrouter.ai/api/v1/systemone` |
| GitHub 로그인 (`gh auth login`) 또는 `GH_TOKEN`·`GITHUB_TOKEN` | 이슈 자동 작업, 현황판 이슈 목록, draft PR | 이슈 기능을 쓸 때 필수 | 이슈 모드 시작 불가. 현황판은 이슈 목록 자리에 조회 실패를 표시 | `GH_TOKEN` → `GITHUB_TOKEN` → `gh auth token` | `https://api.github.com` |
| Context7 API 키 | Context7 MCP 문서 조회 | 선택 | 익명 사용량 한도 적용. 한도를 넘으면 `Monthly quota exceeded` | 디렉터리판: 플러그인 설정 `context7_api_key`. 자체 마켓플레이스판: 키를 전달하지 않음 | `https://mcp.context7.com/mcp` (디렉터리판) |

키가 필요 없는 구성 요소:

- **OCR (open-code-review)**: FullOps 리뷰는 delegate 모드로 호스트 AI가 판단한다. OCR용 LLM endpoint·API 키를 설정하지 않는다.
- **Orca IDE**: 로컬 `orca` CLI만 호출한다.
- **Claude Code·Codex·grok**: 각 CLI의 기존 로그인을 그대로 쓴다. FullOps가 별도로 키를 받지 않는다.

## Jev (`TYPESAFE_API_KEY` 또는 `OPENROUTER_API_KEY`)

Jev(TypeSafe System One 모델)를 호출하는 `jev_*.py` 스크립트가 사용한다. hook은 Jev를 호출하지 않는다. Jev는 두 경로로 호출할 수 있고 요청 형식은 같다. 키는 하나만 있으면 된다.

| 키 | 발급 | 호출 대상 | 모델 ID |
|---|---|---|---|
| `TYPESAFE_API_KEY` | [TypeSafe 콘솔](https://console.typesafe.ai/) | `https://api.typesafe.ai/v1/systemone` (공식 API) | `jev-latest` |
| `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai/) | `https://openrouter.ai/api/v1/systemone` | `~typesafe/jev-latest` |

같은 출처(아래 1~3)에 두 키가 모두 있으면 공식 API 키를 쓴다. 공식 API는 응답에 비용을 주지 않아 FullOps 기록의 Jev 비용이 0으로 남는다. 실제 비용은 TypeSafe 콘솔에서 확인한다. 응답 캐시는 두 경로가 공유한다.

| 스크립트 | 용도 |
|---|---|
| `jev_route.py` | 요청 분류(simple/design), 담당 역할·모델·갱신 산출물 추천 |
| `jev_find.py`, `jev_context.py`, `jev_packet.py` | 코드·문서 위치 탐색, 문서 관련성 분류, 탐색 패킷 |
| `jev_test_web.py`, `jev_test_unity.py` | 웹·Unity 조작 테스트 루프 |

설정 방법은 셋 중 하나다. 앞의 것이 우선한다.

1. 명령에 `--env-file <파일>`을 넘긴다. 파일에서 `TYPESAFE_API_KEY=...`·`OPENROUTER_API_KEY=...` 줄만 읽고 셸 코드를 실행하지 않는다.
2. 프로세스 환경 변수 `TYPESAFE_API_KEY` 또는 `OPENROUTER_API_KEY`를 설정한다.
3. 원본 체크아웃의 `.fullops-squad/.env.example`을 `.fullops-squad/.env`로 복사하고 값을 채운다. `.fullops-squad/.gitignore`가 `.env*`를 제외하고, `env_link.py`와 SessionStart hook이 역할 워크트리에 연결한다.

전송 방식: 키는 명령행이 아니라 `curl --config -` 표준입력의 `Authorization: Bearer` 헤더로만 넘긴다. 요청 본문에는 과제 설명과 선택된 파일 발췌가 들어가며, 비밀값으로 보이는 입력은 보내지 않는다. 같은 요청은 `~/.cache/fullops-squad/jev`에 캐시한다.

끄기: `FULLOPS_JEV_ENABLED=0` 또는 `FULLOPS_OFFLINE=1`이면 Jev를 호출하지 않는다. `jev_route.py --strict`는 폴백 시 결과를 쓰지 않고 종료한다.

디렉터리판에서도 Jev 키는 플러그인 설정(`userConfig`)으로 받지 않는다. Claude Code는 `userConfig` 값을 hook과 MCP에만 전달하고, 스킬이 Bash로 실행하는 스크립트에는 전달하지 않기 때문이다.

## GitHub

`issue_github.py`는 `GH_TOKEN` → `GITHUB_TOKEN` → `gh auth token --hostname github.com` 순서로 토큰을 찾는다. 현황판과 draft PR 생성은 `gh` CLI를 직접 사용한다.

| 기능 | 동작 | 필요한 권한 |
|---|---|---|
| 현황판 이슈 목록 | 레포 GitHub remote의 최근 이슈 30개 조회. coordinator의 Stop hook에서도 실행 | Issues 읽기 |
| 이슈 자동 작업 | 이슈·댓글 조회(GraphQL), 진행 상황 댓글 작성, 작업 브랜치 push, draft PR 생성 | Issues 쓰기, Pull requests 쓰기, Contents 쓰기(push는 git 인증 사용) |

`gh auth login`을 권장한다. fine-grained token을 쓰면 대상 레포만 선택하고 위 권한만 부여한다. `FULLOPS_OFFLINE=1`이면 현황판 이슈 조회를 건너뛴다.

## Context7

라이브러리 문서를 조회하는 MCP 서버다. 판마다 연결 방식이 다르다.

- **디렉터리판**: 원격 엔드포인트 `https://mcp.context7.com/mcp`(HTTP)에 연결한다. 로컬 설치가 필요 없다. 플러그인을 켜면 Claude Code가 `context7_api_key`를 묻는다. 비워 두면 익명 한도를 쓴다. 값은 OS 보안 저장소에 저장되고 `Authorization: Bearer` 헤더로 전송된다. 나중에 바꾸려면 `/plugin` → **Installed** 탭 → FullOps Squad → **Configure options**를 연다.
- **자체 마켓플레이스판**: `scripts/deps.py --host <CLI>`가 `@upstash/context7-mcp`를 전역 설치하고 `context7-mcp` 명령을 실행한다. 현재 키를 전달하지 않으므로 익명 한도가 적용된다.

무료 키는 [context7.com/dashboard](https://context7.com/dashboard)에서 만든다. 조회 질의(라이브러리 이름과 질문)가 Context7 서버로 전송되므로 비공개 코드·비밀값을 질의에 넣지 않는다.

## 확인 순서

1. `scripts/deps.py --check`로 CLI·도구 설치 상태를 확인한다.
2. Jev를 쓸 레포에서 `.fullops-squad/.env`에 `TYPESAFE_API_KEY` 또는 `OPENROUTER_API_KEY`를 채우거나 환경 변수를 설정한다. 키 값을 화면에 출력해 확인하지 않는다.
3. 이슈 기능을 쓸 경우 `gh auth status`로 로그인을 확인한다.
4. Context7 한도 오류가 나면 키를 만들어 설정한다.
