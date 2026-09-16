---
name: setup-fullops
description: 사용자가 현재 레포에 FullOps Squad 하네스 setup 또는 초기화를 요청할 때 사용한다. 플러그인 설치만으로 실행하지 않는다.
---

# 레포별 setup

1. 사용자가 선택한 Git 레포 루트를 확인한다. 이 스킬 파일의 위치에서 `../../scripts/setup.py`를 찾는다. 플러그인 캐시 경로를 레포에 기록하지 않는다.
2. `python3 <setup.py 절대경로> --repo <레포 절대경로> --dry-run`으로 생성 건수와 충돌을 확인한다. 개별 경로가 필요하면 `--verbose`를 붙인다. 기존 하네스 충돌은 사용자 문서를 보존하며 통합하고, 원본 서비스의 코드·이력·remote·라벨·완료 상태를 복사하지 않는다.
3. 같은 명령에서 `--dry-run`을 빼고 실행한다. 사용자의 setup 요청이 해당 레포의 활성화 권한이다. 홈 디렉터리의 전역 AGENTS/CLAUDE 설정을 변경하지 않는다.
4. 생성한 `.fullops-squad/FULLOPS.md`와 `.fullops-squad/orca-agents.md`를 읽는다. 실제 브랜치·테스트 명령·문서 위치를 조회하고 `.fullops-squad/project.md`에 기록한다. 기존 보안·아키텍처·코딩 기준은 링크로 연결한다. 필요한 정보만 질문한다.
5. worker에 사용할 CLI 배정을 사용자에게 받아 `.fullops-squad/orca-agents.md`에 기록한다. 역할마다 Codex/Claude Code/grok/agy를 다르게 쓸 수 있다. 아직 배정되지 않은 worker는 시작하지 않는다. setup 자체는 터미널을 생성하지 않는다.
6. 외부 엔지니어링 스킬 설정은 `.fullops-squad/docs/agents/`가 정본이다. 이슈 트래커는 기본 로컬 파일이며 GitHub/Linear를 선택하면 이 레포의 실제 연결과 라벨을 조회해 바꾼다. `setup-matt-pocock-skills`를 중복 실행해 루트 `docs/agents/`에 사본을 만들지 않는다.
7. 생성 파일·미확정 배정·검증 불가 사항을 보고한다. `.fullops-squad/fullops.json`은 이 레포의 활성화 표식이다. 하네스 업데이트 시 프로젝트 기록은 보존하고 규약 변경만 diff로 검토한다.

설치와 setup은 별개다. 의존성이 없으면 `../../DEPENDENCIES.md`의 배포 저장소 설치기를 안내한다. 설치기는 codebase-memory-mcp와 Context7을 전역 설치하고, 호스트별 패키지의 MCP 설정으로 연결한다. 도구 목록만으로 미설치를 판정하지 말고 설치 경로·호스트 플러그인 목록도 확인한다. Context7 인증값은 호스트 환경에서 제공하고 레포에 기록하지 않는다.
