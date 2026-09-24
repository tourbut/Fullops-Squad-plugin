---
name: setup-fullops
description: 사용자가 현재 레포에 FullOps Squad 하네스 setup 또는 초기화를 요청할 때 사용한다. 플러그인 설치만으로 실행하지 않는다.
---

# 레포별 setup

재실행의 remote·기준 브랜치는 명시적 옵션 → 저장된 `fullops.json` 설정 → 최초 origin/원격 HEAD 순으로 선택한다. 원격 연결된 레포에서 `--local-only`는 기존 역할의 파일 유지에만 사용한다. 새 역할은 원격 setup으로 추가해야 하며 로컬 전용 추가는 변경 전에 실패한다. `--local-only`와 `--remote/--base`는 함께 사용하지 않는다.

setup 후 `.fullops-squad/review/rule.json`을 제품별로 구성한다. 기본 문서·일부 테스트 패턴에 더해 레포의 테스트 경로와 게임 씬·셰이더 등 필요한 자산을 include하고 실제 생성물만 exclude한다. 기존 OCR 규칙이 있으면 명시적으로 통합한다. `fullops-review`가 항상 이 파일을 --rule로 전달한다. 기존 setup 재실행 시 추가된 리뷰 파일은 생성되고 기존 규칙과 기록은 보존된다.

0. 이 스킬 기준 `../../scripts/deps.py --check`로 필수 CLI(OCR·Context7 MCP)를 확인한다. 빠졌거나 사용자 범위 스킬(caveman·typesafe-ai·open-code-review-delegate 등)이 없으면 사용자 승인 뒤 `python3 <deps.py> --host <지금 쓰는 CLI>`로 설치하고, 새 세션이 필요하다고 알린다.
1. 사용자가 선택한 Git 레포 루트를 확인한다. 이 스킬 기준 `../../scripts/setup.py`를 사용한다. 플러그인 캐시 경로는 레포에 기록하지 않는다.
2. 제품·기술·작업 규모에 필요한 역할과 책임을 구성한다. 고정 역할 세트는 없다. 역할 ID는 영문 소문자로 시작하고 소문자·숫자·밑줄·하이픈으로 최대 64자다. 기존 역할은 `fullops.json`에서 재사용하며 `--roles`는 추가만 한다.
3. GitHub remote의 push URL과 기준 브랜치를 확인한다. `python3 <setup.py> --repo <레포 루트> --roles <역할 ID들> --remote <remote 이름> --dry-run`으로 계획을 확인한 뒤 같은 명령에서 `--dry-run`을 빼고 실행한다. 기본 remote는 origin, 기준은 원격 HEAD이며 `--base <브랜치>`로 지정한다. setup 요청은 선택한 레포의 역할 구성과 원격 역할 브랜치 생성 범위다. 원격이 없으면 연결에 필요한 정보만 질문한다. 로컬 구성만 요청받았으면 `--local-only`를 사용한다. 인증 실패나 빈 원격은 실패로 보고한다.
4. 생성한 `.fullops-squad/FULLOPS.md`와 `.fullops-squad/rules/common/README.md` 및 연결된 세 규칙을 읽고 실제 기술 기준·검증 명령·문서 위치를 `project.md`에 기록한다. 기존 보안·아키텍처·코딩 기준은 링크로 연결한다. 레포에 이미 있는 lint·format·타입 검사 도구의 설정과 스크립트(`pyproject.toml`, `package.json`, eslint·ruff 설정 등)를 확인해 `.fullops-squad/lint/lint.json`의 `commands`에 인자 배열로 등록한다. 등록한 명령은 한 번 실행해 결과를 보고한다. 새 도구를 설치하거나 설정 파일을 만들지 않는다. 도구가 없으면 비워 두고 미정으로 보고한다. 기존 레포의 `lint.json`은 보존한다. 공통 기본값으로 기존 기준을 낮추지 않는다. 기존 레포에서는 없는 규칙과 MIT 고지만 추가되며 수정된 규칙·FULLOPS.md·project.md·로컬 템플릿은 자동 교체되지 않는다. 이전 연결 문서는 차이를 확인하고 사용자 내용과 진행 중 작업을 보존해 필요한 링크와 적용 기준 절만 명시적으로 보강한다. `fullops.json`의 기존 plugin_version만으로 규칙 적용 여부를 판정하지 않는다.
5. 등록 역할마다 책임·CLI·모델·기동 명령을 `orca-agents.md`에 기록하고 기존 배정은 보존한다. 기획·설계는 고성능 모델, 명확한 구현 과제는 비용이 낮은 모델에 배정한다. 미정인 사용자 선호만 질문한다. 역할별 원격 브랜치는 `fullops/<역할 ID>`다. setup은 기존 브랜치를 이동하거나 워크트리·터미널을 생성하지 않는다.
6. `.fullops-squad/board/board.json`의 `title`·`summary`를 레포에 맞게 쓰고, 기본 단계(기획·설계·구현·QA·이행)를 레포의 실제 진행 단계와 상태로 고친다. 이미 있는 산출물 원천이 있으면 해당 단계의 `deliverables`에 연결한다. 이 스킬 기준 `../../scripts/board.py`로 현황판 데이터를 한 번 만들고 `board/index.html` 경로를 보고한다.
7. 외부 스킬 설정은 `.fullops-squad/docs/agents/`가 정본이다. 이슈 트래커는 기본 로컬이며 GitHub/Linear 선택 시 실제 연결을 기록한다. 원격 브랜치 생성만으로 GitHub Issues나 Projects 연동이 완료됐다고 보고하지 않는다.
8. 생성 파일·원격 브랜치·미정 배정·검증 불가 사항을 보고한다. `fullops.json`은 활성화 표식과 역할/브랜치 정본이다. 기존 버전은 `--roles`로 역할을 명시해 전환하고 인박스·컨텍스트·로그를 보존한다. 역할 삭제·이름 변경·기존 브랜치 변경은 자동으로 하지 않는다. 원격 생성 뒤 파일 쓰기가 실패하면 같은 명령으로 재시도한다. 생성 파일은 별도 커밋 대상이며 setup이 자동 커밋하지 않는다.

의존성이 없으면 0단계의 `../../scripts/deps.py`로 설치한다. Context7 MCP 실행 파일도 이 스크립트가 npm으로 설치한다. 도구 목록만으로 미설치를 판정하지 말고 설치 경로와 플러그인 목록도 확인한다. 인증값은 호스트 환경에서 제공하고 레포에 기록하지 않는다.
