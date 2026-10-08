# Lint 게이트

코드 산출물의 품질을 일정하게 유지하려고 모든 코드 변경에 lint를 실행한다. 실행 도구는 플러그인의 `scripts/lint.py`이고, 설정 정본은 이 디렉터리의 `lint.json`이다.

## 실행

`python3 <lint.py> --repo <worker 체크아웃 루트> --from <기준 ref> [--out <경로>]`

- 커밋이 끝난 깨끗한 작업 트리에서만 실행한다. 결과는 HEAD SHA에 고정된다.
- 기준 ref와 HEAD의 merge-base 이후에 바뀐 파일만 검사한다. 기존 위반은 소급하지 않는다. 내용 규칙은 추가된 줄에만 적용하고, 줄 수 규칙은 상한을 넘으면서 줄 수가 늘어난 파일에만 적용한다.
- 종료 코드는 0(통과), 1(ERROR 또는 실행 불가), 2(실행 실패)다.

## 검사

| 코드 | 심각도 | 내용 |
|---|---|---|
| 프로젝트 명령 | ERROR | `commands`의 ruff·eslint·타입 검사 등. 실패하거나 시간 초과면 ERROR다. 실행 파일이 없으면 실행 불가로 기록한다. |
| SIZE-001 | `size.severity` (기본 WARNING) | 주석·docstring·빈 줄을 뺀 코드 줄 수가 `max_code_lines`를 넘는다. `.md`는 전체 줄 수를 `max_doc_lines`와 비교한다. ① 삭제 → ② 압축 → ③ 분할 순으로 처리하고, docstring이나 헤더를 깎아 줄 수를 맞추지 않는다. |
| SIZE-002 | WARNING | merge-base 이후 검사 대상 텍스트 파일의 추가 줄 합계가 `size.max_diff_added`(기본 400)를 넘음. 지시서의 예상 변경 규모와 실제 차이·분할하지 않은 이유를 검토한다. exclude·삭제·바이너리는 합계에서 제외한다. |
| DEP-001 | WARNING | `package.json`, `pyproject.toml`, `requirements*.txt`, `go.mod`, `build.gradle*` 변경. 파일 삭제·이름 변경도 포함한다. 완료 보고에서 실제 의존성 변경 여부와 필요성·표준 라이브러리 대안을 확인한다. |
| SLOP-001–004 | WARNING | any 우회, 조건부 객체 스프레드, 광범위한 예외의 pass, 디버그 출력 의심. 정상 코드도 잡을 수 있으므로 검토자가 판단한다. |
| DESIGN-001–003 | WARNING | 하드코딩 색(hex·숫자로 시작하는 CSS 색 함수), 인라인 style 속성, 임의 Tailwind 값 의심. 추가 줄만 검사하며 실제 테마·컴포넌트 계약 준수는 프로젝트 디자인 린트로 확인한다. |
| ANTI-002 | ERROR | `eval()`/`exec()` (Python·JS 계열) |
| ANTI-003 | ERROR | 범위 없는 억제: `# type: ignore`, `# noqa`, `# pyright: ignore`, `@ts-ignore`, `@ts-nocheck`, 규칙을 적지 않은 `eslint-disable`. 오류 코드나 규칙 이름을 적어 범위를 좁히면 허용한다. |
| ANTI-004 | ERROR | 테스트 파일에 skip·only 표식 추가(`.skip(`, `.only(`, `xit(`, `@pytest.mark.skip`, `t.Skip(`, `#[ignore]`, `@Disabled` 등) |
| ANTI-005 | WARNING | 테스트 케이스 수 감소 또는 테스트 파일 삭제. 대체 테스트나 삭제 이유를 검토자가 확인한다 |
| SEC-001 | ERROR (테스트·`.md`는 WARNING) | 하드코딩 비밀값 의심. `test`·`example`·`dummy` 등 더미 값과 환경변수 참조는 예외다. |
| DOC-001 | WARNING | 새 코드 파일에 무엇을 하는지 적은 헤더 설명(docstring·주석 1~3줄)이 없음. 이 설명이 `jev_find.py`의 코드 지도가 된다 |
| DOC-002 | ERROR | 바뀐 산출물 원천 문서의 front matter가 없거나, 필수 필드·id·상태·날짜가 틀리거나, 인덱스 상태와 다르거나, `deliverables.py --stamp` 출력 형식과 다름. `--stamp`로 다시 쓴다 |
| DOC-003 | ERROR | 바뀐 FullOps 일반 Markdown의 front matter가 없거나 필수 필드·상태·날짜·형식이 틀림. `deliverables.py --stamp --path <경로>`로 쓴다. 빈 인박스·템플릿·외부 공통 규칙은 제외한다. 문서 검사는 코드 lint의 exclude와 별도로 적용한다 |
| LINT-000 | WARNING | 프로젝트 lint 명령이 등록되지 않음 |
| LINT-001 | WARNING | 검사 대상 브랜치가 `lint.json`을 바꿈. 변경은 병합 후 적용된다 |
| CUSTOM-NNN | 규칙별 | `rules`에 등록한 레포별 정규식 규칙 |

## 설정

설정은 검사 대상 HEAD가 아니라 **merge-base 시점**의 `lint.json`을 쓴다. 브랜치가 스스로 규칙을 끄거나 `exclude`를 넓혀 통과할 수 없다. 설정 변경은 별도 과제로 병합한 뒤 적용된다.

- `commands`: `[{"name": "ruff", "run": ["ruff", "check", "."], "cwd": "backend"}]` 형식이다. 셸을 거치지 않는 인자 배열이며, `cwd`는 레포 안이어야 한다. setup은 기존 도구를 우선 연결하고 부족한 설정은 아래 레포별 구성 절차로 보완한다.
- 프로젝트 테스트 명령도 `{"name":"test","kind":"test","run":["npm","test"]}`처럼 등록한다. 실제 프로젝트 명령과 cwd를 사용한다. lint는 각 명령의 kind·종료코드·결과를 같은 HEAD에 기록한다. 테스트 명령이 없으면 미정과 영향을 보고하고, 테스트를 실행했다고 표시하지 않는다.
- 기존 린터가 있으면 미사용 규칙(ruff F401/F841, eslint no-unused-vars, oxlint)을 기존 설정에서 활성화해 연결한다. 기본 SLOP 규칙은 미사용 코드 분석을 대신하지 않는다.
- `size`, `exclude`(glob), `timeout_seconds`는 프로젝트 기준에 맞게 조정한다. 기준을 낮추는 변경은 이유를 지시서에 남긴다.
- `rules`는 반복되는 실수를 규칙으로 쌓는 곳이다. 형식은 `{"code": "CUSTOM-001", "description": "…", "pattern": "<Python 정규식>", "file_extensions": [".py"], "severity": "ERROR|WARNING", "suggestion": "…", "exclude_patterns": [], "exclude_paths": [], "enabled": true}`다. `exclude_patterns`는 줄 내용(여러 줄 규칙은 일치 구간)의 정규식이고, `exclude_paths`는 레포 상대경로 glob이다. 규칙별 경로 예외는 다른 보안·테스트 검사를 끄지 않는다. 규칙을 끌 때는 삭제하지 않고 `enabled: false`로 둔다. 추가·변경한 이유는 이 문서 아래에 한 줄씩 남긴다.
- `size.max_diff_added: 0`은 추가 줄 예산 검사를 끈다. 여러 줄을 검사하는 정규식은 `multiline: true`로 등록한다. 일치한 구간에 추가 줄이 있을 때만 경고한다. 기존 레포의 사용자 rules는 자동 교체하지 않는다.

## 레포별 lint 구성

`setup.py`는 새 설정을 만들 때 루트 package.json의 기존 `lint`(없으면 `lint:design`)·`typecheck`·`test` 스크립트를 연결한다. packageManager와 lockfile로 npm·pnpm·yarn·bun을 고른다. 기존 lint.json은 그대로 유지한다. 스크립트를 실행하거나 프로젝트 린터를 설치하는 작업은 setup 스킬이 아래 순서로 수행한다.

1. 언어·프레임워크·패키지 매니저, 기존 lint 설정·CI·스크립트와 검사 범위를 확인한다. 모노레포는 루트 집계 명령을 우선하고 없는 경우 패키지별 실제 cwd를 등록한다. 생성물·외부 코드만 제외한다.
2. 기존 린터·포매터·타입 검사의 기준을 유지하고 누락된 연결을 보완한다. 도구가 없으면 프로젝트 정본·호환 버전에 맞는 최소 개발 의존성과 설정을 만든다. Python은 기존 ruff 설정, JS/TS는 기존 ESLint/Oxlint 설정처럼 스택의 실제 도구를 확인한다. 포매터는 검사 모드로 연결한다. 미사용 규칙도 프로젝트 관례에 맞게 설정한다.
3. 디자인·테마 린트가 있으면 동일 `commands`에 등록한다. 예: 이미 설정된 shadcn 플러그인을 실행하는 `{"name":"design-lint","kind":"lint","run":["npm","run","lint:design"],"cwd":"apps/web"}`. shadcn은 독립 실행 파일이 아니라 ESLint/Oxlint 플러그인이다. 기존 lint가 이를 포함하면 별도 중복 명령을 만들지 않는다.
4. 테스트 명령을 `kind: test`로 연결하고 각 명령을 실제 cwd에서 실행한다. 결과의 name·run·cwd·exit_code·미실행 사유와 정본 경로를 project.md에 기록한다. 커밋 후 같은 HEAD에서 lint.py를 실행해 게이트 연계도 확인한다. 도구·설정이 부족하면 빈 commands로 완료하지 않고 미완료 사유와 남은 구성을 보고한다.

## shadcn 디자인 린트

Tailwind v4와 React·Vue·Svelte UI가 있는 레포에 적용한다. Node.js 20.19 이상과 ESLint 9.30 이상 또는 Oxlint 1.80 이상이 필요하다. Vue·Svelte 템플릿은 해당 parser를 사용하는 ESLint로 검사한다. 일반 CSS나 Tailwind가 없는 레포는 해당 스택의 기존 스타일 검사 도구를 사용한다. 호환성을 확인하려고 Tailwind·프레임워크를 임의로 마이그레이션하지 않는다.

setup 요청에서 필요한 서비스 개발 의존성 `@shadcn/lint`와 설정을 구성할 수 있다. 기존 parser·ignore·규칙을 보존해 플러그인을 등록하고, 프로젝트에 이미 정해진 디자인 기준을 우선한다. 새 디자인 정책이 없으면 `no-raw-colors`, `no-arbitrary-values`, `no-unknown-classes`를 warn부터 연결한다. `no-restyle`은 공용 컴포넌트 계약이 있는 경우에 설정한다. 컴포넌트 구현 경로의 restyle·arbitrary/static 예외와 사용자 승인 예외는 범위를 좁혀 남긴다. 초기 warning을 임의의 error로 올리거나 기존 error를 낮추지 않는다.

ESLint는 `import { plugin as shadcn } from "@shadcn/lint"` 후 UI 파일의 기존 설정 블록에 다음 항목을 통합한다. 아래는 규칙 예시이며 parser·files·테마·컴포넌트 구현 경로는 해당 레포에서 확인한다. Oxlint는 공식 문서의 jsPlugins 설정을 사용한다.

```js
plugins: { shadcn },
rules: {
  "shadcn/no-raw-colors": "warn",
  "shadcn/no-arbitrary-values": "warn",
  "shadcn/no-unknown-classes": "warn",
},
```

등록만 하고 규칙을 켜지 않으면 디자인 검사가 되지 않는다. 의도적인 위반과 정상 토큰 사용 예제로 검출·정상 통과를 모두 확인하고 예제는 검증 후 제거한다. 실제 디자인 린터의 error는 기존 종료코드 게이트가 차단한다. FullOps 기본 DESIGN WARNING은 정규식 휴리스틱이며 주석·CSS 선택자·동적 스타일에도 오탐할 수 있다. 토큰의 존재나 컴포넌트 계약을 자동 추론하지 않는다.

DESIGN-001은 줄 처음의 CSS custom property 선언을 토큰 정의로 허용하고, DESIGN-003은 `var(...)`·`env(...)`·`--token`으로 시작하는 임의 값 문법을 제외한다. 다른 토큰 정의 파일·브랜드 SVG 예외는 해당 DESIGN 규칙의 `exclude_paths`(예: `["src/theme/tokens.css", "assets/brand/*.svg"]`)로 지정한다. 내용 예외는 `exclude_patterns`로 지정하고 이유를 이 문서에 남긴다. 필요한 프로젝트는 규칙별 severity를 ERROR로 올릴 수 있다. 기존 레포의 rules는 유지하면서 필요한 DESIGN 항목만 명시적으로 통합한다.

공식 설정·계약: [shadcn README](https://github.com/shadcn-ui/lint#get-started), [규칙](https://github.com/shadcn-ui/lint/blob/main/docs/rules.md), [설치 안내](https://github.com/shadcn-ui/lint/blob/main/SETUP.md).

## 게이트

dev 주 담당자의 직접 구현은 현재 HEAD·세션 시작 기준 SHA의 lint와 다른 세션의 고정 SHA 독립 리뷰가 필요하다. 배정된 dev worker는 기존 worker 게이트를 따른다. 직접 구현의 누락·잘못된 리뷰 기록은 반복 Stop으로 생략할 수 없다. 정상 snapshot 정리 후에는 동일 SHA·작성자 세션의 이미 수락한 cleanup 영수증과 증거 hash를 확인한다. 신규 수락은 live snapshot 검사다. 잘못된 운영 정책이나 중단된 모드 전환은 복구 또는 새 세션 전까지 작업을 차단한다.

- 세션 안: 플러그인의 Stop hook(`done_gate.py`)이 이 세션에서 코드를 바꿨는데 현재 HEAD의 `lint.py` 통과 기록(`<git dir>/fullops-gate/pass.json`)이 없으면 종료를 한 번 막는다. 아무것도 바꾸지 않고 다시 끝내면 경고만 하고 통과한다. 이 체크아웃에서 직접 만든 커밋과 미커밋 변경만 보므로 fast-forward로 받은 커밋은 해당하지 않는다. hook 오류는 종료를 막지 않는다.
- worker는 완료 보고 전에 실행한다. ERROR를 모두 고치고, 결과 요약(HEAD·ERROR·WARNING·실행 불가와 사유)을 완료 보고의 검증 항목에 적는다.
- 검토자는 리뷰 디렉터리에 `lint.json`을 남긴다. `review.py check`는 lint 결과가 없거나 SHA·설정이 다르거나, ERROR가 남아 있거나, 실행 불가 명령에 `reason`이 비어 있으면 실패한다.
- 등록된 `kind: test` 명령의 실행 증거가 없거나 중복되거나 통과 종료코드가 0이 아니면 review check가 실패한다. 테스트 실패·시간 초과는 기존 ERROR 경로로 차단한다. 실행 불가는 아래 예외 기록을 따른다.
- SIZE-002가 있으면 지시서의 예상 변경 규모와 실제 차이를 확인한다. DEP-001이 있으면 완료 보고의 의존성 변경 이유를 확인한다. 누락이면 리뷰 수정 요청으로 남기고 수락하지 않는다.
- UI 작업은 핸드오버의 테마·토큰·공용 컴포넌트 경로, 디자인 lint 결과·예외, 테마 전환 검증을 확인한다. 해당 없으면 근거가 필요하다. DESIGN WARNING과 누락 항목은 검토자가 판단하고 report.md에 기록한다.
- 실행 불가(폐쇄망·도구 미설치)는 사유를 `reason`에 적고, 대신 수행한 정적 검사와 CI·스테이징에서 실행해야 한다는 점을 보고서에 남긴다. WARNING은 보고서에 기록하고 검토자가 판단한다.

## 규칙 변경 기록
