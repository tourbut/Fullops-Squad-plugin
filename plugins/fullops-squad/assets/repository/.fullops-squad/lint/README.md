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
| ANTI-002 | ERROR | `eval()`/`exec()` (Python·JS 계열) |
| ANTI-003 | ERROR | 범위 없는 억제: `# type: ignore`, `# noqa`, `# pyright: ignore`, `@ts-ignore`, `@ts-nocheck`, 규칙을 적지 않은 `eslint-disable`. 오류 코드나 규칙 이름을 적어 범위를 좁히면 허용한다. |
| ANTI-004 | ERROR | 테스트 파일에 skip·only 표식 추가(`.skip(`, `.only(`, `xit(`, `@pytest.mark.skip`, `t.Skip(`, `#[ignore]`, `@Disabled` 등) |
| ANTI-005 | WARNING | 테스트 케이스 수 감소 또는 테스트 파일 삭제. 대체 테스트나 삭제 이유를 검토자가 확인한다 |
| SEC-001 | ERROR (테스트·`.md`는 WARNING) | 하드코딩 비밀값 의심. `test`·`example`·`dummy` 등 더미 값과 환경변수 참조는 예외다. |
| DOC-001 | WARNING | 새 코드 파일에 무엇을 하는지 적은 헤더 설명(docstring·주석 1~3줄)이 없음. 이 설명이 `jev_find.py`의 코드 지도가 된다 |
| LINT-000 | WARNING | 프로젝트 lint 명령이 등록되지 않음 |
| LINT-001 | WARNING | 검사 대상 브랜치가 `lint.json`을 바꿈. 변경은 병합 후 적용된다 |
| CUSTOM-NNN | 규칙별 | `rules`에 등록한 레포별 정규식 규칙 |

## 설정

설정은 검사 대상 HEAD가 아니라 **merge-base 시점**의 `lint.json`을 쓴다. 브랜치가 스스로 규칙을 끄거나 `exclude`를 넓혀 통과할 수 없다. 설정 변경은 별도 과제로 병합한 뒤 적용된다.

- `commands`: `[{"name": "ruff", "run": ["ruff", "check", "."], "cwd": "backend"}]` 형식이다. 셸을 거치지 않는 인자 배열이며, `cwd`는 레포 안이어야 한다. setup에서 레포에 이미 있는 도구·설정·스크립트만 연결한다. 새 도구를 설치하거나 설정 파일을 새로 만들지 않는다.
- `size`, `exclude`(glob), `timeout_seconds`는 프로젝트 기준에 맞게 조정한다. 기준을 낮추는 변경은 이유를 지시서에 남긴다.
- `rules`는 반복되는 실수를 규칙으로 쌓는 곳이다. 형식은 `{"code": "CUSTOM-001", "description": "…", "pattern": "<Python 정규식>", "file_extensions": [".py"], "severity": "ERROR|WARNING", "suggestion": "…", "exclude_patterns": [], "enabled": true}`다. 규칙을 끌 때는 삭제하지 않고 `enabled: false`로 둔다. 추가·변경한 이유는 이 문서 아래에 한 줄씩 남긴다.

## 게이트

- 세션 안: 플러그인의 Stop hook(`done_gate.py`)이 이 세션에서 코드를 바꿨는데 현재 HEAD의 `lint.py` 통과 기록(`<git dir>/fullops-gate/pass.json`)이 없으면 종료를 한 번 막는다. 아무것도 바꾸지 않고 다시 끝내면 경고만 하고 통과한다. 이 체크아웃에서 직접 만든 커밋과 미커밋 변경만 보므로 fast-forward로 받은 커밋은 해당하지 않는다. hook 오류는 종료를 막지 않는다.
- worker는 완료 보고 전에 실행한다. ERROR를 모두 고치고, 결과 요약(HEAD·ERROR·WARNING·실행 불가와 사유)을 완료 보고의 검증 항목에 적는다.
- 검토자는 리뷰 디렉터리에 `lint.json`을 남긴다. `review.py check`는 lint 결과가 없거나 SHA·설정이 다르거나, ERROR가 남아 있거나, 실행 불가 명령에 `reason`이 비어 있으면 실패한다.
- 실행 불가(폐쇄망·도구 미설치)는 사유를 `reason`에 적고, 대신 수행한 정적 검사와 CI·스테이징에서 실행해야 한다는 점을 보고서에 남긴다. WARNING은 보고서에 기록하고 검토자가 판단한다.

## 규칙 변경 기록
