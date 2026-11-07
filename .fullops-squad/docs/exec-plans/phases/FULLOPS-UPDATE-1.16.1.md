---
title: FullOps 1.16.1 레포 적용 기록
status: draft
updated: 2026-11-07
owner: dev
tasks: [FULLOPS-UPDATE-1.16.1]
summary: "이 레포의 FullOps 적용 버전을 1.11.0에서 1.16.1로 갱신한 기록. 릴리스별 판정, 변경 파일, 검증, 보류 항목"
---

# FullOps 1.16.1 레포 적용 기록

## 버전

| 항목 | 값 |
|---|---|
| 업데이트 전 설치 버전 | 1.16.1 (Claude Code 플러그인 캐시) |
| 업데이트 전 레포 적용 버전 | 1.11.0 |
| 대상 버전 | 1.16.1 (최신 릴리스 v1.16.1) |
| 호스트 | Claude Code 2.1.319 |

## 의존성

- `deps.py --host claude-code`: 첫 실행은 실패했다. npm이 `@alibaba-group/open-code-review` 폴더를 옮기지 못했다(EBUSY). 프로세스를 끄지 않고 다시 실행해 통과했다.
- `deps.py --check --host claude-code`: 통과.
- setup dry-run(기존 역할): 생성 예정 파일 0개. 실제 setup은 실행하지 않았다.

## 릴리스별 판정

| 릴리스 | 기존 레포 적용 항목 | 판정 | 근거 |
|---|---|---|---|
| 1.11.1 | 세션 재시작, 자동 모드 재활성화, 워크트리에 링크된 lease 삭제 | 해당 없음 | 자동 모드를 쓰지 않는다. 새 `fullops/dev` 워크트리에 lease가 링크되지 않은 것을 확인했다. |
| 1.12.0 | 세션 재시작, fullops-meter 0.11.0 재로드 | 세션 재시작만 보류 | 레포 변경이 없다. 아래 보류 항목을 따른다. |
| 1.12.1 | 세션 재시작, held 이슈 질문 | 해당 없음 | 자동 모드를 쓰지 않는다. |
| 1.13.0 | 세션 재시작 | 세션 재시작만 보류 | 레포 변경이 없다. |
| 1.14.0 | `lint/README.md` 통합, `lint_tune.py` 실행 | 적용 | README는 템플릿과 본문이 같다. 차이는 front matter와 SLOP-004 레포 기록뿐이다. `lint_tune.py`는 리뷰 1건, 지적 0건, 제안 규칙 없음을 보고했다. |
| 1.14.1 | 세션 재시작 | 세션 재시작만 보류 | 레포 변경이 없다. |
| 1.15.0 | `lint/README.md` 통합, 시험 명령 자원 확인, 지시서 `--level` 제거 | 적용 | README는 위와 같다. 시험 명령은 임시 디렉터리에서 돌고 1.16.1 lint(446856f)의 병렬 실행이 통과해 `parallel_tests`를 바꾸지 않는다. 역할 인박스는 비어 있다. |
| 1.15.1 | 세션 재시작 | 세션 재시작만 보류 | 레포 변경이 없다. |
| 1.16.0 | `rules/delegation.md`·`lint/README.md` 통합 | 적용 | 두 파일 모두 본문이 템플릿과 같다. |
| 1.16.0 | pnpm 제외 추가 | 해당 없음 | 이 레포는 pnpm을 쓰지 않는다. |
| 1.16.0 | Unity JevPlay 갱신 | 해당 없음 | 서비스 Unity 프로젝트가 아니다. JevPlay 원본을 이 레포에서 관리한다. |
| 1.16.0 | `.fullops-squad/` CRLF를 LF로 변경 | 일부 유지 | CRLF 파일은 `qa-reports/GH-1369701248-109-A3-review/`의 `preview.json`·`result.json`·`rules.json` 3개뿐이다. 리뷰 증거의 해시를 보존하려고 바꾸지 않는다. |
| 1.16.0 | 섀도 판정 | 해당 없음 | 기본 정책을 쓴다. `fullops.json`에 `autonomy_policy`를 두지 않는다. |
| 1.16.1 | 서비스 레포 적용 | 해당 없음 | 릴리스 노트에 레포 적용 항목이 없다. |

## 템플릿 비교로 고친 파일

- `docs/agents/triage-labels.md`: 등록되지 않은 역할 목록을 지우고 `fullops.json`의 `roles`를 쓴다는 템플릿 문장으로 바꿨다.
- `board/index.html`: 1.16.1 양식으로 갱신했다.

## 사용자 지시로 고친 파일

- `orca-agents.md`: dev 주 담당의 직접 작업 위치를 `fullops/dev` 워크트리로 바꿨다. main 체크아웃은 병합과 릴리스에 쓴다.
- `fullops.json`: `plugin_version`을 1.16.1로 올렸다.
- `board/board.json`: 요약의 버전을 v1.16.1로 고쳤다.
- `PLANS.md`: 이 작업을 기록했다.

## dev 워크트리

- 경로: `C:/Users/shin/orca/workspaces/Fullops-Squad-plugin/dev`
- 브랜치: `fullops/dev` (기준 main 5161d7a). 아직 push하지 않았다.
- `policy.identity`는 `fullops/dev`를 주 담당 역할로 본다. `fullops.json`의 `primary_branch`는 바꾸지 않는다.
- `.fullops-squad/.env`는 `env_link.py --all`로 main 체크아웃에 링크했다.

## 검증

- `update.py --repo . --from 1.16.1 --verify`: 필수 적용 0/0 충족, 종료코드 0.
- lint: `lint.py --from main`을 `fullops/dev` HEAD에서 실행한다. 문서만 바뀌어 시험 명령은 건너뛴다.

## 보류

| 항목 | 담당 | 재개 조건 |
|---|---|---|
| 세션 재시작 또는 `/reload-plugins` | 사용자 | dev 워크트리에서 새 세션을 열 때 함께 처리된다. |
| `core.longpaths` 켜기 | 사용자 승인 후 dev | `env_link.py`가 긴 경로의 리뷰 snapshot 실패 가능성을 알렸다. 승인되면 `git config core.longpaths true`를 실행한다. |
| dev 워크트리의 `node_modules` 설치 | 사용자 승인 후 dev | `npm test`를 그 워크트리에서 돌릴 때 필요하다. npm을 빼는 방향은 #132에서 검토한다. |
| `fullops/dev`를 main에 병합 | 사용자 | 병합 전까지 main의 `plugin_version`은 1.11.0이다. |
