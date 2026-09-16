# 실행 의존성

Python 3.9+, Git, Node.js 20.18.1+, npm, 사용할 에이전트 CLI와 Orca가 필요하다.
MCP 실행 파일은 PATH에서 찾는다: `codebase-memory-mcp`, `context7-mcp` (`@upstash/context7-mcp@4.1.1`).
Context7은 키 없이 기본 사용이 가능하다. 선택적 인증값 전달은 호스트 설정을 따르며 표준 환경변수 치환에 의존하지 않는다.

설치는 [배포 저장소](https://github.com/tourbut/Fullops-Squad-plugin)의 `AGENTS.md`와 `scripts/install.py --host <현재 CLI>`를 사용한다. 외부 스킬·플러그인 의존성 정본은 배포 저장소 루트의 `dependencies.json`이다. Agent Plugins 표준 자체는 의존성을 설치하지 않는다.
설치 후 명시한 서비스 레포에만 `setup-fullops`를 실행한다. 서비스 산출물은 `.fullops-squad/`에 두며 호스트의 `PLUGIN_DATA`로 옮기지 않는다.
