---
title: FullOps 1.22.0 레포 적용 기록
status: draft
updated: 2026-11-10
owner: dev
tasks: [FULLOPS-UPDATE-1.22.0]
summary: "ShinPC 설치와 이 레포의 FullOps 적용 버전을 1.21.0에서 1.22.0으로 갱신한 기록. 릴리스 판정, 검증, deps 검사 실패와 보류 항목"
---

# FullOps 1.22.0 레포 적용 기록

## 버전

| 항목 | 값 |
|---|---|
| 업데이트 전 설치 버전 | fullops-squad 1.21.0 |
| 업데이트 전 레포 적용 버전 | 1.21.0 |
| 대상 버전 | 1.22.0 |

## 설치

- `claude plugin marketplace update fullops-squad`, `claude plugin update fullops-squad@fullops-squad`: 1.21.0 → 1.22.0.
- `deps.py --host claude-code`: 종료코드 0.
- `deps.py --check --host claude-code`: 처음에 실패했다(`hook runtime missing or outdated`). 원인은 실행 중인 Claude Code가 설치 폴더에 만든 `.in_use/36020` 표지다. 이 파일 말고 런타임과 설치본의 내용 차이는 없었다. `deps.py --runtime-only` 뒤 통과했다. 표지는 지우지 않았다.
- 실제 동작: 이 세션의 Bash에서 1,000줄 출력이 줄어든 것을 확인했다(`/reload-plugins` 전).
- `/reload-plugins`: 사용자 실행 대기.

## 릴리스별 판정

| 항목 | 판정 | 근거 |
|---|---|---|
| 필수 적용 | 없음 | `update.py --verify` 0/0 충족 |
| `.fullops-squad/.gitignore`의 `local/` | 해당 없음 | 이미 있다(7행) |

## 보류

| 항목 | 담당 | 재개 조건 |
|---|---|---|
| `package_files`에서 `.in_use` 제외 | 사용자 승인 후 dev | 런타임 스냅샷에 표지가 들어가 있어 표지가 바뀌면 `--check`가 다시 실패할 수 있다 |
| `core.longpaths` 켜기 | 사용자 승인 후 dev | 1.16.1 기록에서 이어진다 |
