---
title: FullOps 1.18.0 레포 적용 기록
status: draft
updated: 2026-11-09
owner: dev
tasks: [FULLOPS-UPDATE-1.18.0]
summary: "이 PC 설치와 이 레포의 FullOps 적용 버전을 1.17.0에서 1.18.0으로 갱신한 기록. 릴리스 판정, 변경 파일, 검증, 보류 항목"
---

# FullOps 1.18.0 레포 적용 기록

## 버전

| 항목 | 값 |
|---|---|
| 업데이트 전 설치 버전 | fullops-squad 1.17.0, fullops-meter 0.12.0 |
| 업데이트 전 레포 적용 버전 | 1.17.0 |
| 대상 버전 | 1.18.0. fullops-meter는 바뀌지 않았다 |

## 설치

- `claude plugin marketplace update fullops-squad`, `claude plugin update fullops-squad@fullops-squad`: 1.17.0 → 1.18.0.
- `deps.py --host claude-code`, `deps.py --check --host claude-code`: 통과. hook 런타임 `current.json`이 1.18.0을 가리킨다.

## 릴리스별 판정

| 항목 | 판정 | 근거 |
|---|---|---|
| 필수 적용 3건(`project.md` 두 절, `delegation.md` verifier 절) | 적용 | `update.py --verify` 통과 |
| `작업 검증` 채우기 | 적용 | lint 명령과 실제 출력 줄을 적었다 |
| `자주 틀리는 것` | 적용 | 1·2차 리뷰가 반복 지적한 Orca `--full` 누락 1건만 적었다 |
| `FULLOPS.md` 지도 행, `_TEMPLATE.md` 줄 2개, `lint/README.md` 문구 | 적용 | 템플릿과 같게 맞췄다 |
| `subagent_level`·`test_level` 값 | 유지 | 릴리스 적용으로는 바꾸지 않는다. lite는 결정 D021로 이미 바꿨다 |

## 보류

| 항목 | 담당 | 재개 조건 |
|---|---|---|
| `/reload-plugins` | 사용자 | 스킬 문서를 1.18.0으로 읽으려면 필요하다 |
| `core.longpaths` 켜기 | 사용자 승인 후 dev | 1.16.1 기록에서 이어진다 |
