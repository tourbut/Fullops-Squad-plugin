# 산출물 인덱스

아래 경로는 `.fullops-squad/` 기준 기본 매핑이다. 기존 원천이 있으면 실제 경로로 바꾼다.
원천 문서는 필요할 때 작성한다. 생성 전 링크를 완료 산출물로 보고하지 않는다.

| ID | 단계 | 산출물 | 원천 | 상태 |
|---|---|---|---|---|
| D01 | 착수 | 사업계획서 | `docs/planning/business-plan.md` | 미작성 |
| D02 | 분석 | 요구사항정의서 | `docs/planning/product-specs/` | 미작성 |
| D03 | 설계 | 아키텍처설계서 | `docs/design-docs/architecture.md`, `docs/design-docs/tech-stack.md` | 미작성 |
| D04 | 설계 | 화면설계서 | `docs/design-docs/mockups/` | 미작성 |
| D05 | 설계 | 인터페이스설계서 | `docs/design-docs/interface-design.md` | 미작성 |
| D06 | 분석 | 엔티티정의서 | `docs/design-docs/data-model.md` 엔티티 절 | 미작성 |
| D07 | 설계 | 데이터베이스설계서 | `docs/design-docs/data-model.md` DB 절 | 미작성 |
| D08 | 구현 | 테이블정의서 | `docs/generated/db-schema.md` | 미작성 |
| D09 | 설계 | CRUD정의서 | `docs/design-docs/data-model.md` CRUD 절 | 미작성 |
| D10 | 설계·구현 | 프로그램설계서 | `docs/design-docs/module-design.md` | 미작성 |
| D11 | 이행 | 사용자설명서 | `docs/operations/user-guide.md` | 미작성 |
| D12 | 이행 | 운영자설명서 | `docs/operations/ops-guide.md` | 미작성 |
| D13 | 이행 | 인수인계서 | `docs/operations/transition.md` | 미작성 |

원천에 상태(draft/review/approved)·갱신일·개정이력·상위 입력·하위 영향을 기록한다.
산출물 `DNN_<slug>.md`는 원천 절 링크와 상태를 조립하는 인덱스다. 원문 수정은 원천에서 한다.
목업 승인이 필요한 프로젝트는 구현 전에 승인 근거를 확인한다. 미승인·미확정 내용은 그대로 표시한다.
요구사항 → 화면/API/CRUD → 모듈 → QA 결과의 추적성을 확인한다. 테스트 결과는 `docs/evaluations/qa-reports/`에 기록한다.
테이블 정의는 실제 스키마에서 생성한다. 생성 도구가 없으면 미구현으로 표시하며 가짜 검증 결과를 쓰지 않는다.
