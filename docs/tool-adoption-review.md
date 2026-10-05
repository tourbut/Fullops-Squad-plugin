---
title: shadcn 디자인 린트 적용
status: approved
updated: 2026-10-06
owner: maintainer
summary: Tailwind 서비스의 shadcn 연계와 레포별 setup lint 구성·디자인 경고 검증
---

# shadcn 디자인 린트 적용

Tailwind v4 서비스에 `@shadcn/lint`를 적용할 수 있도록 FullOps setup·lint·UI 작업 기준을 보강했다. 서비스의 개발 의존성과 설정으로 구성하며 FullOps 공통 런타임 의존성에는 넣지 않는다. 사용자 요청에 따라 영상 제작 도구는 적용 범위에서 제외했다.

## 공식 기능과 적용 조건

`@shadcn/lint`는 일반 코드 품질 검사기가 아니라 Tailwind 디자인 시스템의 사용 규칙을 검사하는 ESLint/Oxlint 플러그인이다. shadcn/ui 자체는 필수가 아니다. Node.js 20.19 이상, ESLint 9.30 이상 또는 Oxlint 1.80 이상이 필요하다. Vue·Svelte 템플릿 검사는 해당 parser를 사용하는 ESLint로 구성한다. [공식 README](https://github.com/shadcn-ui/lint/blob/ee9391038b5dc025f01777d8dbd0f72d5b885ab4/README.md)

플러그인 등록과 규칙 활성화는 별개다. 기본 preset은 없으므로 프로젝트 디자인 기준을 확인해 규칙을 구성해야 한다. `no-restyle`은 공용 컴포넌트 계약을 기준으로 적용하고, 컴포넌트 구현 경로의 예외는 공식 규칙 안내를 따른다. [설치 안내](https://github.com/shadcn-ui/lint/blob/ee9391038b5dc025f01777d8dbd0f72d5b885ab4/SETUP.md), [규칙](https://github.com/shadcn-ui/lint/blob/ee9391038b5dc025f01777d8dbd0f72d5b885ab4/docs/rules.md)

Context7은 사용량 한도 초과로 조회에 실패했다. 공식 GitHub 문서·소스와 npm에 실제 배포된 `@shadcn/lint@0.2.0`으로 확인했다. 이 검토에서 사용한 공식 소스 기준은 `ee9391038b5dc025f01777d8dbd0f72d5b885ab4`다.

## 적용한 동작

- 새 setup 설정은 루트 package.json의 기존 lint·typecheck·test 스크립트를 npm·pnpm·yarn·bun에 맞춰 연결한다. 기존 lint.json은 유지한다.
- setup 스킬은 언어·프레임워크·정본·기존 설정·모노레포 범위를 확인하고 필요한 lint 설정·개발 의존성을 구성한다. 다른 스택은 해당 스택의 실제 도구를 사용한다. 실제 명령 실행과 종료코드 확인이 완료 조건이다.
- Tailwind UI는 기존 ESLint/Oxlint에 shadcn을 통합한다. 기존 정책이 없으면 색·임의 값·알 수 없는 클래스 규칙을 warn부터 적용한다. 중복 lint 명령은 만들지 않는다.
- 기본 DESIGN-001–003은 하드코딩 색·인라인 style 속성·임의 Tailwind 값의 추가 줄에 WARNING을 남긴다. 프로젝트는 severity·내용 예외·규칙별 경로 예외를 조정할 수 있다.
- UI 핸드오버와 리뷰에는 테마·토큰·공용 컴포넌트 정본, 예외 근거, 디자인 lint 재실행과 테마 전환 검증을 연결한다.

설정 정본은 [lint 안내](../plugins/fullops-squad/assets/repository/.fullops-squad/lint/README.md), [setup 스킬](../plugins/fullops-squad/skills/setup-fullops/SKILL.md), [코딩 기준](../plugins/fullops-squad/assets/repository/.fullops-squad/rules/common/coding-style.md)에 있다.

## 검증과 한계

[tests/shadcn-lint.py](../tests/shadcn-lint.py)를 실제 `@shadcn/lint 0.2.0`, `ESLint 9.33.0`, `@typescript-eslint/parser 8.40.0`, `Tailwind CSS 4.3.3`, Node.js 24.13.0 환경에서 실행했다. 임시 Tailwind 샘플에서 setup이 기존 디자인 lint 스크립트를 등록하고, 임의 padding 위반을 shadcn 규칙으로 검출해 종료코드 1을 기록했다. 정상 스케일 값으로 수정하면 종료코드 0과 현재 HEAD의 게이트 통과 기록을 확인했다. 이 버전은 재현용이며 서비스에서는 호환되는 지원 버전을 선택한다.

[tests/lint.py](../tests/lint.py)는 외부 디자인 린터가 없는 경우의 기본 경고, 기존 줄 비소급, 토큰 참조, 내용·경로 예외, 보안 검사 유지와 severity 변경을 검증한다. setup의 dry-run·패키지 매니저 선택·기존 사용자 설정 보존도 확인한다.

기본 DESIGN 규칙은 정규식 휴리스틱이다. 주석·CSS 선택자·동적 스타일에 오탐할 수 있고 실제 토큰 존재나 컴포넌트 계약을 추론하지 않는다. CSS custom property 선언과 일부 토큰 참조 문법만 기본 예외로 처리한다. 명시적 파일 예외는 개별 DESIGN 규칙에 적용되어 다른 보안 검사를 유지한다. 전체 스타일 경로·화면 품질·접근성·실제 서비스의 테마 전환은 이 샘플 검증으로 보증하지 않는다. 해당 레포에서 별도로 검증한다. [공식 분석 범위](https://github.com/shadcn-ui/lint/blob/ee9391038b5dc025f01777d8dbd0f72d5b885ab4/docs/how-it-works.md)
