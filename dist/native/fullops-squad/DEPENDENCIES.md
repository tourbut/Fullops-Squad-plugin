# 실행 의존성

Python 3.9+, Git 2.41+, Node.js 20.18.1+, npm, 사용할 에이전트 CLI와 Orca가 필요하다.
리뷰에는 `ocr` (`@alibaba-group/open-code-review@latest`)와 외부 `open-code-review-delegate` 스킬이 필요하다. 별도 OCR LLM endpoint/API 키는 필요 없다. FullOps 리뷰는 OCR_NO_UPDATE=1로 실행하고 호스트 AI가 판단한다.
MCP 실행 파일은 PATH에서 찾는다: `context7-mcp` (`@upstash/context7-mcp@4.1.1`).
Context7은 키 없이 기본 사용이 가능하다. 선택적 인증값 전달은 호스트 설정을 따르며 표준 환경변수 치환에 의존하지 않는다.

플러그인은 GitHub 마켓플레이스 `tourbut/Fullops-Squad-plugin`에서 설치한다. 마켓플레이스 설치는 위 CLI와 사용자 범위 스킬을 넣지 않으므로 이 플러그인의 `scripts/deps.py --host <현재 CLI>`로 설치하고 `--check`로 확인한다. 의존성 목록은 패키지에 함께 들어 있는 `dependencies.json`이다.
설치 후 명시한 서비스 레포에만 `setup-fullops`를 실행한다. 서비스 산출물은 `.fullops-squad/`에 두며 호스트의 `PLUGIN_DATA`로 옮기지 않는다.
