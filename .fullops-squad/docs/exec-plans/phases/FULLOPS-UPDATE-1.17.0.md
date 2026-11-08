---
title: FullOps 1.17.0 레포 적용 기록
status: draft
updated: 2026-11-08
owner: dev
tasks: [FULLOPS-UPDATE-1.17.0]
summary: "이 PC 설치와 이 레포의 FullOps 적용 버전을 1.16.1에서 1.17.0으로 갱신한 기록. 릴리스 판정, 변경 파일, 검증, 보류 항목"
---

# FullOps 1.17.0 레포 적용 기록

## 버전

| 항목 | 값 |
|---|---|
| 업데이트 전 설치 버전 | fullops-squad 1.16.1, fullops-meter 0.11.0 (user scope) |
| 업데이트 전 레포 적용 버전 | 1.16.1 |
| 대상 버전 | 1.17.0, fullops-meter 0.12.0 |
| 호스트 | Claude Code 2.1.319, Git 2.52.0, Orca 1.4.251 |

## 설치

- `claude plugin marketplace update fullops-squad`: 통과.
- `claude plugin update fullops-squad@fullops-squad`: 1.16.1 → 1.17.0.
- `claude plugin update fullops-meter@fullops-squad --scope user`: 0.11.0 → 0.12.0.
- `deps.py --host claude-code`(1.17.0 패키지): 통과. hook 런타임 `current.json`이 1.17.0을 가리킨다.
- `deps.py --check --host claude-code`: 통과.
- setup dry-run(기존 역할): 생성 예정 파일 0개. 실제 setup은 실행하지 않았다.
- project scope의 fullops-squad 1.9.0·fullops-meter 0.10.1은 다른 프로젝트의 설치라 건드리지 않았다.

## 릴리스별 판정

| 릴리스 | 기존 레포 적용 항목 | 판정 | 근거 |
|---|---|---|---|
| 1.17.0 | `.gitkeep`만 있는 setup 폴더 6개 삭제 | 적용 | 6개 모두 `.gitkeep`만 있었다. |
| 1.17.0 | SHA 없이 hold한 완료 기록에 `set-sha`·`resume` | 해당 없음 | PLANS.md에 해당 hold가 없다. |
| 1.17.0 | 리뷰어 보고가 `pending`에 남은 기록 hold | 해당 없음 | `integration.py status`의 `pending`이 비어 있다. |
| 1.17.0 | 시작되지 않은 dispatch intent `reconcile --not-dispatched` | 해당 없음 | 이슈 자동 모드 상태(`fullops-issues/state.sqlite`)가 없다. |
| 1.17.0 | Windows `ocr.cmd`와 cmd 메타문자 경로 | 해당 없음 | 레포 경로에 `& | < > ^ % "`가 없다. |

## 변경 파일

- `.fullops-squad/docs/design-docs/diagrams/.gitkeep` 외 5개 삭제(위 6개 폴더).
- `fullops.json`: `plugin_version`을 1.17.0으로 올렸다.
- `PLANS.md`: 이 작업을 기록했다.

## 검증

- `update.py --repo . --from 1.16.1 --verify`: 필수 적용 0/0 충족, 종료코드 0.

## 보류

| 항목 | 담당 | 재개 조건 |
|---|---|---|
| `/reload-plugins` | 사용자 | 스킬 문서를 1.17.0으로 읽으려면 필요하다. hook은 고정 런타임으로 이미 1.17.0이다. meter 0.12.0은 새 세션부터 적용된다. |
| `core.longpaths` 켜기 | 사용자 승인 후 dev | 1.16.1 기록에서 이어진다. |
