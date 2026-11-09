---
title: FullOps 1.20.0 레포 적용 기록
status: draft
updated: 2026-11-09
owner: dev
tasks: [FULLOPS-UPDATE-1.20.0]
summary: "이 PC 설치와 이 레포의 FullOps 적용 버전을 1.19.0에서 1.20.0으로 갱신한 기록. 릴리스 판정, 변경 파일, 검증, 보류 항목"
---

# FullOps 1.20.0 레포 적용 기록

## 버전

| 항목 | 값 |
|---|---|
| 업데이트 전 설치 버전 | fullops-squad 1.19.0 |
| 업데이트 전 레포 적용 버전 | 1.19.0 |
| 대상 버전 | 1.20.0 |

## 설치

- `claude plugin marketplace update fullops-squad`, `claude plugin update fullops-squad@fullops-squad`: 1.19.0 → 1.20.0.
- `deps.py --host claude-code`, `deps.py --check --host claude-code`: 통과. hook 런타임 `current.json`이 1.20.0을 가리킨다.
- `/reload-plugins`: 사용자가 실행했고 오류가 없다.

## 릴리스별 판정

| 항목 | 판정 | 근거 |
|---|---|---|
| 필수 적용 3건(`주요 흐름` 표, `testing.md` 문구, 규칙 묶음 0.3.7) | 적용 | 적용 전 `update.py --verify` 0/3, 적용 뒤 3/3 |
| `FULLOPS.md`, `lint/README.md`, `scenarios/README.md`, intent 템플릿 문구 | 적용 | 템플릿과 같은 문구로 맞췄다 |
| `주요 흐름` 표 채우기 | 빈 표 유지 | 이 레포에는 반복해 돌린 사용자 흐름 기록이 없다. 시나리오도 0개다 |
| `lint.json`, `test_level` | 유지 | 릴리스 적용으로 바꾸지 않는다 |

## 보류

| 항목 | 담당 | 재개 조건 |
|---|---|---|
| `core.longpaths` 켜기 | 사용자 승인 후 dev | 1.16.1 기록에서 이어진다 |
