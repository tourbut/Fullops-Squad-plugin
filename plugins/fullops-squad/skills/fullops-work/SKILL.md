---
name: fullops-work
description: FullOps setup이 완료된 레포에서 기능 개발을 역할별로 나누거나 worker 핸드오버 작성·완료 기록을 처리할 때 사용한다.
---

# 핸드오버와 작업 기록

현재 Git 레포 루트에 `.fullops-squad/fullops.json`이 있는지 확인한다. 없으면 `setup-fullops`를 안내한다. 이 스킬의 `../../scripts/work.py`가 레포 활성화·과제 키·역할·중복 기록을 검증한다.

활성 레포에서는 `.fullops-squad/FULLOPS.md`를 읽는다.
역할은 `fullops.json`에 등록된 ID를 사용한다. 작업자는 자기 역할의 `contexts/<role>.md`와 받은 지시서만 먼저 읽는다.

## 작성과 전달

코드·운영 상태를 확인하고 주 역할과 과제 키를 정한다. 여러 worker의 파일 소유권·선행 조건을 분리한다. 같은 역할에 진행 중인 지시서가 있으면 후속 과제는 `PLANS.md`에 대기시킨다.

`python3 <work.py> new --repo <레포 루트> --role <역할> --key <과제 키> --goal <한 줄 목표>`로 빈 역할 인박스에 템플릿을 만든다. 그 파일에 확인 근거·범위·완료 기준·산출물·복귀 주소·승인 범위를 채운다. 이미 허가된 실행은 진행한다. `fullops-orca` dispatch 전에 worker가 자기 체크아웃에서 같은 과제 키의 지시서와 원천 문서를 읽을 수 있어야 한다.

## 작업과 완료

구현과 함께 영향을 받는 원천 문서와 QA 결과를 `.fullops-squad/docs/`에 갱신한다. 상세 결정·검증은 직접 작업을 포함해 `docs/exec-plans/phases/<과제키>.md`에 기록한다.

인박스의 `## 완료 보고`에 변경 이유, 지시와 달라진 판단·범위, 충돌, 검증한 것과 못 한 것, 산출물·후속을 전문으로 쓴다. `python3 <work.py> finish --repo <레포 루트> --role <역할> --key <과제 키>`가 지시서와 결과를 날짜별 로그에 append·검증한 뒤 인박스를 비운다. 실패하면 인박스를 유지하고 기록을 확인한다.
`contexts/<role>.md`에는 날짜·결정·교훈을 항목당 3줄 이내로 append하고 상세 로그를 연결한다. 150줄 또는 10KB를 넘으면 전문을 `contexts/archive/`에 보관하고 유효한 원칙만 요약한다. `PLANS.md` 상태도 갱신한다.

변경 파일과 산출물을 커밋해 브랜치·SHA를 확보한다. 커밋이 허가되지 않았거나 실패하면 미커밋 상태를 명시한다.
worker는 지시서의 복귀 주소로 `fullops-orca` report를 직접 실행한다. 전송 실패 시 보존한 로그는 유지하고 회신 재시도를 남긴다. 검토자는 같은 과제를 다시 아카이빙하지 않는다.
