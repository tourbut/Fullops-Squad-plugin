---
title: FullOps 1.19.0 레포 적용 기록
status: draft
updated: 2026-11-09
owner: dev
tasks: [FULLOPS-UPDATE-1.19.0]
summary: "이 PC 설치와 이 레포의 FullOps 적용 버전을 1.18.0에서 1.19.0으로 갱신한 기록. 릴리스 판정, 변경 파일, 검증, 보류 항목"
---

# FullOps 1.19.0 레포 적용 기록

## 버전

| 항목 | 값 |
|---|---|
| 업데이트 전 설치 버전 | fullops-squad 1.18.0, fullops-meter 0.12.0 |
| 업데이트 전 레포 적용 버전 | 1.18.0 |
| 대상 버전 | 1.19.0. fullops-meter는 바뀌지 않았다 |

## 설치

- `claude plugin marketplace update fullops-squad`, `claude plugin update fullops-squad@fullops-squad`: 1.18.0 → 1.19.0.
- `deps.py --host claude-code`, `deps.py --check --host claude-code`: 통과. hook 런타임 `current.json`이 1.19.0을 가리킨다.

## 릴리스별 판정

| 항목 | 판정 | 근거 |
|---|---|---|
| 필수 적용 | 없음 | `update.py --verify`: 필수 적용 0/0 충족 |
| `review/_REPORT.md` 사본의 3곳 | 적용 | 이 레포는 템플릿과 같은 사본을 유지해 왔다 |

## 보류

| 항목 | 담당 | 재개 조건 |
|---|---|---|
| `/reload-plugins` | 사용자 | 스킬 문서를 1.19.0으로 읽으려면 필요하다 |
| `core.longpaths` 켜기 | 사용자 승인 후 dev | 1.16.1 기록에서 이어진다 |
