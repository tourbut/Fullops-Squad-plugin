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

원천 문서 맨 위에는 front matter를 둔다. 원천이 여러 파일이거나 폴더면 각 문서에 같은 `id`를 적는다.
**front matter는 손으로 쓰지 않고 `deliverables.py --stamp`로만 쓴다.** 필드 순서와 목록 표기가 고정되고, `updated`는 오늘 날짜, 과제 키는 `tasks`에 추가되며, 이 표의 상태도 같은 값으로 맞춰진다.

```text
python3 <플러그인>/scripts/deliverables.py --repo . --id D03 --stamp --task <과제 키> [--status draft|review|approved]
  처음 쓸 때: --owner <역할> --summary "<한 줄 요약>" [--title ...] [--upstream D02] [--downstream D05,D10]
  원천이 폴더이거나 여러 파일일 때: --path <.fullops-squad 기준 문서 경로>
```

결과는 아래 형식이다. 바뀐 원천 문서가 이 형식과 글자 그대로 같지 않으면 lint가 `DOC-002` ERROR로 막는다.

```yaml
---
id: D03
title: 아키텍처설계서
status: draft
updated: 2026-09-24
owner: arch
tasks: [JUMP-3]
upstream: [D02]
downstream: [D05, D10]
summary: 한 줄 요약
---
```

필수 필드는 `id`·`title`·`status`·`updated`·`owner`·`summary`다. 현황판과 Jev 산출물 라우팅이 `title`·`summary`를 읽는다. 개정이력은 본문에 기록한다.
산출물 `DNN_<slug>.md`는 원천 절 링크와 상태를 조립하는 인덱스다. 원문 수정은 원천에서 한다.
목업 승인이 필요한 프로젝트는 구현 전에 승인 근거를 확인한다. 미승인·미확정 내용은 그대로 표시한다.
요구사항 → 화면/API/CRUD → 모듈 → QA 결과의 추적성을 확인한다. 테스트 결과는 `docs/evaluations/qa-reports/`에 기록한다.
테이블 정의는 실제 스키마에서 생성한다. 생성 도구가 없으면 미구현으로 표시하며 가짜 검증 결과를 쓰지 않는다.
