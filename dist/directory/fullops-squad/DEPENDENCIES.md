# 실행 의존성

Python 3.10+, Git 2.41+, Node.js 20.18.1+, npm, 사용할 에이전트 CLI와 Orca가 필요하다.
리뷰에는 `ocr` (`@alibaba-group/open-code-review@latest`)와 외부 `open-code-review-delegate` 스킬이 필요하다. 별도 OCR LLM endpoint/API 키는 필요 없다. FullOps 리뷰는 OCR_NO_UPDATE=1로 실행하고 호스트 AI가 판단한다.
MCP 실행 파일은 PATH에서 찾는다: `context7-mcp` (`@upstash/context7-mcp@latest`).
Context7은 키 없이 기본 사용이 가능하다. 선택적 인증값 전달은 호스트 설정을 따르며 표준 환경변수 치환에 의존하지 않는다.

플러그인은 GitHub 마켓플레이스 `tourbut/Fullops-Squad-plugin`에서 설치한다. 마켓플레이스 설치는 위 CLI와 사용자 범위 스킬을 넣지 않으므로 이 플러그인의 `scripts/deps.py --host <현재 CLI>`로 설치하고 `--check --host <현재 CLI>`로 실제 구성과 완료 기록을 확인한다. 단독 `--check`는 CLI 존재만 검사한다. 의존성 목록은 패키지에 함께 들어 있는 `dependencies.json`이다.
설치 후 명시한 서비스 레포에만 `setup-fullops`를 실행한다. 서비스 산출물은 `.fullops-squad/`에 두며 호스트의 `PLUGIN_DATA`로 옮기지 않는다.

`deps.py --host <현재 CLI>`는 공통 사용자 스킬을 Claude Code·Codex·Grok Build 셋 모두에 설치한다. 다른 CLI가 없어도 공통 스킬 경로는 준비하며 해당 CLI의 설치·인증은 수행하지 않는다. provider 전용 플러그인은 지정한 호스트만 설치한다. agy를 지정하면 그 스킬 경로도 추가한다. `--check --host`는 공통 세 호스트의 스킬과 지정한 호스트의 전용 구성·완료 기록을 확인한다.

프런트엔드 UI/UX용 공통 스킬 네 개를 포함한다. 공식 출처·라이선스는 dependencies.json에서 관리하며 저장소의 최신 스킬을 설치한다. 설치 전 기존 스킬 폴더를 백업하고 설치 후 출처·실행 상태를 확인한다.

| 스킬 | 출처 | 용도 |
|---|---|---|
| `frontend-design` | `anthropics/skills` | 화면·컴포넌트 구현 |
| `ui-ux-pro-max` | `nextlevelbuilder/ui-ux-pro-max-skill` | 디자인 시스템·UX 기준 |
| `impeccable` | `pbakaus/impeccable` | 기존 화면 평가·다듬기 |
| `web-design-guidelines` | `vercel-labs/agent-skills` | 접근성·사용성 검수 |

외부 스킬 원문을 FullOps에 복사하지 않는다. Vercel 스킬의 개별 라이선스는 미확인으로 기록하며 재배포하지 않는다. Impeccable 전용 설치기의 자동 hook은 추가하지 않는다. 스킬 자체의 사용료와 별개로 호스트 AI 모델의 비용은 기존 계약을 따른다.

실제 UI 작업은 `fullops-frontend`가 주 스킬 하나와 필요한 보조 검토만 호출한다. Playwright CLI·Impeccable 엔진·shadcn MCP는 dependencies.json의 frontend_tools에 선택형으로 등록돼 있으며 필수 설치/검사에 포함되지 않는다. `scripts/frontend.py`의 프로젝트별 dry-run·로컬 설치·준비 검사와 [도구 준비](skills/fullops-frontend/toolchain.md)를 따른다. 기본 tools는 빈 목록이며 hook·MCP 연결·폴더 신뢰는 자동 변경하지 않는다. Grok 설치에서도 `--trust`를 자동 전달하지 않는다.

CUAWright의 `cuawright-web`은 `optional_skills`의 별도 최신 선택 스킬이다. 기본 설치/check와 공통 네 스킬에 포함하지 않는다. Python Playwright/Firefox 준비와 선택 호스트 실행은 [웹 PoC 계약](skills/fullops-test/web-engine.md)을 따른다. 준비 스크립트는 새 모델 키·브라우저 다운로드·생성 코드 실행을 자동 추가하지 않는다.
