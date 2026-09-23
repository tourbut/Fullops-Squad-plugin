# FullOps Squad — 하네스 지도

현재 레포 루트의 `.fullops-squad/fullops.json`이 있을 때만 이 규약을 적용한다.
규약은 한국어로 관리하고 식별자·코드베이스의 기존 언어 규칙은 유지한다.

| 작업 | 먼저 읽을 문서 (`.fullops-squad/` 기준) |
|---|---|
| 공통 코딩·테스트·보안 기준과 우선순위 | [rules/common/README.md](rules/common/README.md) 및 연결된 세 규칙 |
| 기술 기준·검증 명령·문서 정본 | `project.md` |
| 역할·워크트리·에이전트 배정 | `orca-agents.md` |
| 현재 할 일·우선순위 | `PLANS.md` |
| 역할별 작업 명세와 완료 처리 | `handovers/_TEMPLATE.md` · `fullops-work` 스킬 |
| Orca 착수 확인·회신·검토 | `orca-agents.md` · `fullops-orca` 스킬 |
| 코드 변경의 lint 게이트 | `lint/README.md` · `lint/lint.json` |
| 병합 전 delegate 코드·문서 검토 | `review/rule.json` · `fullops-review` 스킬 |
| 과거 결정·교훈 | `contexts/<role>.md` |
| 산출물과 원천 매핑 | `docs/deliverables/README.md` |
| 외부 스킬 설정 | `docs/agents/{issue-tracker,triage-labels,domain}.md` |

작업의 흐름은 요구사항 → 설계 → 역할별 핸드오버 → worker 구현·검증 → 직접 회신 → 검토·병합이다.
문서에 적힌 코드·API·브랜치·도구의 존재는 작업 전에 직접 확인한다.
코드 탐색은 지시서의 `먼저 읽을 문서`에서 시작하고, 필요한 범위만 검색해 읽는다. 레포 전체를 훑어 읽지 않는다.
라이브러리·SDK·프레임워크의 API나 설정을 확인할 때는 프로젝트 버전을 기준으로 Context7의 `resolve-library-id` → `query-docs`를 사용한다. 확인한 library ID·버전·출처·필요한 API 근거를 지시서에 남기고 같은 근거는 재사용한다. 버전 변경·근거 부족 시 다시 조회하며, 미지원·연결 실패 시 공식 문서로 확인한다. 비공개 코드·비밀값을 조회문에 포함하지 않는다.
실질적 개발 작업은 지시서에 목적·범위·완료 기준·산출물·복귀 주소를 남긴다.
이미 허가된 작업은 다시 승인받지 않는다. 미승인 외부 발송·배포 등은 실행 직전에 별도로 확인한다.
작업자와 검토자는 `rules/common/README.md` 및 연결된 세 규칙을 읽고 `project.md`의 정본과 함께 적용한다. 지시서에 규칙 식별자·프로젝트 문서 경로·기준 커밋 또는 스냅샷·예외를 기록하고 worker와 검토자가 같은 버전을 읽는지 확인한다.
프로젝트 보안·아키텍처·테스트 기준이 외부 스킬보다 우선하며, 충돌은 지시서에 기록한다. 공통 기본값으로 기존 기준을 낮추지 않고 보안·권한·미해결 critical/high 차단을 임의 완화하지 않는다.
ponytail full을 적용하되 검증·산출물·핸드오버 기록은 생략하지 않는다.
하네스 플러그인 캐시는 읽기 전용 자원으로 취급한다. 개발 산출물은 이 레포에 Git으로 관리한다.
