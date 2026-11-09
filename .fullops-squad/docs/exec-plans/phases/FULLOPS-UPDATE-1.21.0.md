---
title: FullOps 1.21.0 레포 적용 기록
status: draft
updated: 2026-11-09
owner: dev
tasks: [FULLOPS-UPDATE-1.21.0]
summary: "이 PC 설치와 이 레포의 FullOps 적용 버전을 1.20.0에서 1.21.0으로 갱신한 기록. 릴리스 판정, 변경 파일, 검증, 보류 항목"
---

# FullOps 1.21.0 레포 적용 기록

## 버전

| 항목 | 값 |
|---|---|
| 업데이트 전 설치 버전 | fullops-squad 1.20.0 |
| 업데이트 전 레포 적용 버전 | 1.20.0 |
| 대상 버전 | 1.21.0 |

## 설치

- `claude plugin marketplace update fullops-squad`, `claude plugin update fullops-squad@fullops-squad`: 1.20.0 → 1.21.0.
- `deps.py --host claude-code`, `deps.py --check --host claude-code`: 통과.
- `/reload-plugins`: 레포 적용 뒤 사용자가 실행했고 오류가 없다. 에이전트가 실행할 수 없어, 레포 적용은 새 패키지의 스크립트 경로를 직접 지정해 먼저 진행했다.

## 릴리스별 판정

| 항목 | 판정 | 근거 |
|---|---|---|
| 필수 적용 | 없음 | `update.py --verify` 0/0 충족 |
| intent 템플릿 `배경` 문장 | 적용 | 새 템플릿과 같은 문장으로 맞췄다 |
| `board/index.html` | 적용 | `board.py`가 새 양식으로 맞춘다 |

## 보류

| 항목 | 담당 | 재개 조건 |
|---|---|---|
| `core.longpaths` 켜기 | 사용자 승인 후 dev | 1.16.1 기록에서 이어진다 |
