---
name: fullops-orca
description: FullOps setup이 완료된 레포에서 요청 라우팅·Orca worker 배정·bootstrap·dispatch·질문 전달·report·검토 및 병합을 운영할 때 사용한다.
---

# Orca 운영

현재 Git 레포 루트에 `.fullops-squad/fullops.json`이 있을 때만 진행한다. 없으면 `setup-fullops`를 안내하고 멈춘다.
`.fullops-squad/FULLOPS.md`와 `.fullops-squad/orca-agents.md`를 읽는다.

Orca 실행 파일은 `ORCA_CLI_COMMAND` → `ORCA_DEV_REPO_ROOT`가 있는 개발 세션의 `orca-dev` → Orca 외부 Linux의 `orca-ide` → 그 외 `orca` 순으로 환경에 맞게 선택한다. 실행 실패 시 다른 바이너리로 바꾸지 않는다.
선택한 실행 파일의 `skills get orca-cli`를 먼저 읽고 실제 버전의 명령을 사용한다. 오래된 핸들·repo id·워크트리 경로를 과거 로그에서 복사하지 않는다.
설치된 `orca-cli` 스킬이 있으면 해당 가이드를 사용한다. 이 플러그인은 Orca 앱이나 실행 파일을 번들하지 않는다.

`bootstrap`, `route`, `dispatch <role>`, `report`, `merge <role>` 중 요청한 모드를 수행한다.
flow-gate hook이 route 기록, `worker-start --run`, 설계 역할의 코드 수정 금지, worker의 `worker_done`을 강제한다. 차단되면 사유에 적힌 절차를 따르고 우회하지 않는다.
할당·회신은 Orca 에이전트 터미널 간 통신이며 사용자·고객에게 보내는 Slack/메일 권한을 뜻하지 않는다.
하위 worker에 대한 실제 작업 위임은 사용자의 위임 요청 또는 해당 레포의 합의된 작업 방식 안에서 한다.

## bootstrap

앱·런타임 도달 여부와 현재 레포 등록 상태를 확인한다. `fullops.json`의 등록 역할·원격·브랜치를 읽고 미정 CLI 배정을 해결한다. 기존 워크트리·브랜치를 조회한 뒤 필요한 역할의 상설 워크트리를 해당 원격 역할 브랜치에서 생성하고 추적 관계를 확인한다. 로컬 전용 setup이면 역할 브랜치를 합의된 기준에서 만든다. coordinator 체크아웃은 중복 생성하지 않는다. setup 이후 추가한 하네스 파일은 worker 브랜치에 자동 포함되지 않으므로 dispatch 전에 준비 커밋을 반영한다. grok을 배정한 역할이 있으면 이 스킬 기준 `../../scripts/grok_trust.py`로 `python3 <grok_trust.py> --repo <레포 루트> --check`를 실행한다. grok은 워크트리에서도 원본 레포 경로의 폴더 신뢰를 요구해, 신뢰되지 않으면 worker가 착수 전에 확인 화면에서 멈춘다. 신뢰되지 않았으면 사용자에게 한 번 확인받은 뒤 `--add`로 추가한다. 승인 없이 추가하지 않는다. 워크트리를 만든 뒤 이 스킬 기준 `../../scripts/env_link.py`로 `python3 <env_link.py> --all <레포 루트>`를 실행해 원본 체크아웃 루트의 `.env*`(git 미추적)를 각 워크트리에 링크한다. 워크트리에서 시작하는 세션마다 flow-gate SessionStart hook도 빠진 파일을 연결한다. 각 터미널 출력을 읽어 실제 CLI 프롬프트와 작업 경로를 확인한다.

## route — coordinator가 요청을 받을 때

coordinator는 비용이 낮은 모델로 운영한다. 설계는 직접 하지 않는다. `orca-agents.md`의 `## 라우팅 기준`을 읽는다. coordinator를 역할 워크트리에서 운영하면 라우팅 기준에 `- coordinator 역할: `<역할>`` 줄이 있어야 flow-gate가 coordinator로 판정하고 현황판을 갱신한다.

1. 과제 키를 정한다. 이 스킬 기준 `../../scripts/jev_route.py`로 `python3 <jev_route.py> --repo <레포 루트> --key <과제 키> --request "<요청 원문>"`을 실행한다. 비밀값이 섞인 요청은 원문 대신 요약을 넘긴다. 결과는 `docs/evaluations/jev/<과제 키>-route.json`에 남는다.
출력의 `갱신할 산출물`(route.json의 `deliverables`)은 이 요청으로 쓰거나 고쳐야 할 D01–D13이다. 추천일 뿐이며 판단으로 더하거나 뺄 수 있다.
2. `route: simple → <역할>`이면 `fullops-work`로 그 역할 인박스에 짧은 지시서를 쓰고 dispatch한다. 지시서의 `갱신할 산출물`에 route 결과를 옮긴다. 지시서를 쓰다가 파일 소유권·완료 기준·검증 명령 중 하나라도 정할 수 없으면 design으로 바꾼다. Jev 결과보다 이 판단이 우선한다.
3. `route: design → <설계 역할>`이면(오류·키 없음 포함) 설계 역할을 dispatch한다. spec에는 과제 키, 요청 원문 파일 경로, 대상 역할 인박스(`handovers/to_<역할>.md`), route의 갱신할 산출물을 넣는다. 설계 역할은 산출물 목록을 확정해 각 지시서의 `갱신할 산출물`에 나눠 적는다. 설계 역할은 설계 문서와 역할별 지시서를 쓰고 커밋한다. 그다음 `worker_done` body에 `[설계] <과제 키> | 지시서: <경로들> | 역할: … | SHA …`를 보낸다. 코드는 구현하지 않는다.
4. 설계 `worker_done`을 받으면 설계 역할을 `worker-retain`으로 남긴다. 이어서 적힌 지시서마다 해당 역할을 dispatch한다. 설계 역할은 그 과제의 병합이 끝나면 `worker-release`한다. 다음 설계는 새 세션에서 시작해 컨텍스트가 과제 단위로 끊기게 한다.

## dispatch

1. 역할 인박스의 과제, 권한, 선행 조건을 확인한다.
2. coordinator와 worker의 실제 repo id·워크트리·터미널 핸들을 조회해 지시서에 넣는다. 과거 핸들을 재사용하지 않는다.
3. worker가 지시서와 원천 문서를 읽을 수 있는 버전을 전달하고 과제 키·내용을 확인한다. `.fullops-squad/rules/common/README.md` 및 연결된 세 규칙과 지시서가 지정한 프로젝트 정본도 같은 버전으로 전달하고 실제 경로·기준 커밋 또는 스냅샷을 확인한다. 누락·불일치를 해소하기 전 착수시키지 않는다. 워크트리는 파일을 자동 공유하지 않는다. 기본은 준비 커밋을 worker에 반영하는 방식이며, 미커밋 지시서는 명시한 절대경로의 스냅샷으로 제공한다. 진행 중 변경을 덮어쓰지 않는다.
4. 보고를 받을 Run을 정한다. 내 세션에 Task·Dispatch ID가 든 preamble이 있으면 나도 dispatched worker다. 이때 상위 Run에 하위 worker를 띄우면 완료 보고가 상위 coordinator에게 간다. 먼저 `orchestration run-create`로 내 Run을 만들고 그 run id를 쓴다. preamble이 없으면 내가 최상위 coordinator다. 별도 coordinator 없이 한 역할(예: 아키텍처)이 다른 역할 worker를 띄우는 구성도 같다. 이 경우 기존 Run을 쓰거나 `run-create`로 새로 만든다. `nested_worker_depth_exceeded`면 하위 worker를 띄우지 말고 상위에 `escalation`으로 알린다.
5. 대상 역할이 grok이면 `grok_trust.py --check`로 원본 레포 신뢰를 먼저 확인한다(bootstrap 규칙). `orchestration worker-start --run <run id> --spec "<한 문단>" --worktree <worker 워크트리> --agent <CLI>`로 현재 작업과 분리된 새 세션을 시작한다. 한 문단에는 과제 키·지시서 실제 경로·worker 경로를 넣고, 긴 내용은 파일로 제공한다. Orca가 넣는 preamble이 `worker_done` 복귀 경로다. 터미널 주입(`terminal send`, `dispatch --inject`)으로 착수시키면 worker가 `worker_done`을 보낼 수 없으므로 쓰지 않는다. 읽을 범위는 지시서의 `먼저 읽을 문서`로 한정하고, 원천 문서 전체를 붙이지 않는다. 권한 모드는 임의로 완화하지 않는다. 진행 중인 세션을 임의로 중단하지 않는다.
6. 반환된 run id·task id·dispatch id·worker 핸들을 지시서의 복귀 항목과 카드에 남긴다. terminal read로 worker가 지시서를 읽고 착수했는지 확인한다. send 성공이나 idle 상태만으로 판단하지 않는다.
7. 착수를 확인하면 결과를 기다리며 턴을 유지하지 않고 dispatch를 마친다. 아래 대기 규칙대로 `--run <run id>`를 지정해 기다린다.

## 대기 — coordinator

- Orca는 `--types`가 붙은 대기가 받지 않는 메시지(heartbeat·status)마다 idle 터미널에 "You have N orchestration message" 알림을 넣어 세션을 깨운다. worker heartbeat는 Orca가 5분마다 보내므로 `check --wait --types …`를 직접 걸지 않는다.
- orchestration Run을 기다릴 때는 이 스킬 기준 `../../scripts/orca_wait.py`를 사용한다: `python3 <orca_wait.py> --orca <실행 파일> --run <dispatch에서 쓴 run id> [--ack <처리한 delivery id>]`. 자기 Run을 만든 dispatched worker가 `--run`을 빼면 상위 Run을 보게 되어 하위 보고를 받지 못한다. `--types` 없이 대기해 알림을 막고, heartbeat·status만 있는 묶음은 모델을 부르지 않고 ack한다. 처리할 메시지가 오면 ack하지 않은 묶음과 흡수한 내용 요약을 반환한다.
- 호스트의 백그라운드 실행으로 한 번 걸고 턴을 끝낸다. 백그라운드 실행이 없으면 포그라운드에서 실행한다. 반환된 `actionable` 묶음은 오케스트레이션 규칙대로 모두 처리한 뒤, 다음 대기를 `--ack <deliveryId>`로 이어 건다. `absorbed`의 status도 확인한다.
- 새 coordinator 세션(재시작·플러그인 갱신 후)은 터미널이 바뀌어 기존 Run 연결이 끊긴다. `orchestration check`가 "no longer bound"를 반환하면 PLANS.md·현황판에 기록한 run id로 `orchestration run-use --id <run id>`를 실행해 다시 연결한다.
- 분류(`jev_route.py`)한 과제는 같은 세션에서 배정하거나 PLANS.md에 보류 사유를 적는다. flow-gate Stop hook이 배정되지 않은 route를 한 번 막는다. 대화가 요약된 뒤에는 route 기록을 다시 읽고 이어서 진행한다.
- `idle_timeout`(기본 45분)은 실패가 아니다. `absorbed.heartbeats`로 생존을 확인하고, 없으면 `worker-list`로 상태를 확인한다. `error`면 `pending_ack`를 보존하고 오류를 보고한다.
- orchestration을 쓰지 않는 터미널 전달은 `terminal wait`을 긴 타임아웃으로 백그라운드에서 한 번 건다.
- 짧은 타임아웃 반복, sleep 루프, 주기적인 terminal read로 폴링하지 않는다. 완료 판정은 worker의 `worker_done`·`[완료]` 보고, 보고된 브랜치·SHA, 산출물 파일로 한다. terminal read는 착수 확인과 오류 진단에만 쓰고, 실제 버전의 범위 옵션(예: `--limit`, `--cursor`)으로 필요한 최근 출력만 읽는다.

## 질문 — coordinator가 전달

- worker의 `question`이 경로·핸들·순서·재시도 같은 운영 문제면 coordinator가 `reply`로 직접 답한다.
- 설계·범위·공유 계약·지시서 해석 문제면 답하지 않고 설계 역할에게 넘긴다. 그 과제에 retain된 설계 역할 터미널이 있으면 그 터미널에 후속 Dispatch를 보낸다. 없으면 새로 dispatch한다. spec에는 질문 원문, message id, 지시서 경로를 넣는다. 설계 역할은 답을 `worker_done` body에 쓴다. 지시서를 바꿨으면 커밋하고 경로와 SHA를 함께 적는다.
- coordinator는 그 답을 줄이거나 해석하지 않고 원래 질문의 message id로 `reply`한다. 답이 지시서 변경을 포함하면 worker에게 해당 SHA를 반영하라고 적는다.
- 설계 역할도 판단할 수 없는 사용자 결정은 사용자에게 묻는다. 답을 받을 때까지 worker의 질문은 열어 둔다.

## 메시지 — worker

- 작업 중 설계·범위·공유 계약 판단이 필요하면 추측하지 말고 preamble의 `ask`로 묻는다. 질문에는 과제 키, 막힌 지점, 선택지와 각각의 영향을 적는다. 답은 설계 역할이 하지만 경로는 항상 coordinator다. 형제 worker에게 직접 보내지 않는다. timeout이 나면 같은 message id로 다시 기다린다.
- coordinator에게는 `worker_done`, 결정이 필요한 `question`(`ask`), 막힘을 알리는 `escalation`만 보낸다. 진행 상황은 완료 보고와 산출물에 남기고, 진행 알림용 status는 보내지 않는다. `send`는 `--type`을 생략하면 status가 되므로 항상 타입을 명시한다.
- heartbeat는 preamble이 정한 주기를 따른다. coordinator 쪽 `orca_wait.py`가 흡수하므로 줄이려고 규칙을 어기지 않는다.
- coordinator도 worker에게 보내는 지시는 모아서 보낸다. idle worker에게 보내는 메시지는 그 세션을 깨운다.

## report — worker가 직접 실행

`fullops-work`의 기록·아카이브·커밋 절차를 마친다. 실제 브랜치와 SHA를 조회해 preamble의 `worker_done` 명령으로 한 번 보낸다. `--from`·capability·task id·dispatch id는 preamble 값을 그대로 쓰고 `--outcome succeeded` 또는 `failed`를 명시한다. body는 아래 한 줄로 쓴다:

`[완료] <과제 키> | 브랜치 <branch> | SHA <sha 또는 미커밋> | 변경: … | 검토 필요: … | 검증(lint 포함): … | 산출물/로그: … | 후속: …`

preamble이 없으면 오케스트레이션 없이 착수한 것이다. `worker_done`을 만들어 보내지 않는다. 지시서의 복귀 터미널 핸들로 위 줄을 `terminal send` 하고, 이 경로는 요청자가 `terminal wait`으로 기다릴 때만 도달한다고 보고에 적는다. 핸들이 만료됐으면 같은 repo id와 복귀 워크트리에서 다시 조회한다. 전송 오류와 재시도 여부를 기록·보고하고 카드를 갱신한다. `worker_done` 뒤에는 턴을 끝내고 idle로 둔다.

## 현황판 — coordinator

사람이 진행 상황을 눈으로 보는 `.fullops-squad/board/index.html`은 플러그인이 제공하는 고정 양식이다. 고치지 않는다.
coordinator는 `.fullops-squad/board/board.json`만 관리한다. `title`·`summary`와 `phases`(각 항목 `name`, `status`: done/active/blocked/todo, `deliverables`: D01–D13 ID 목록, `note`)를 적는다. 프로젝트 단계가 시작·완료·추가되면 바로 고치고 기본 브랜치에 커밋한다. 산출물 상태는 `docs/deliverables/README.md`에서 읽으므로 board.json에 중복해서 적지 않는다.
역할별 과제, PLANS.md, 완료 이력, route, 리뷰 결과, 산출물은 이 스킬 기준 `../../scripts/board.py`가 레포 기록에서 모아 `board/board-data.js`를 만든다. coordinator 세션이 끝날 때 flow-gate hook이 자동으로 실행하고, 즉시 보려면 `python3 <board.py> --repo <레포 루트>`를 실행한다. board-data.js는 커밋하지 않는다.

## merge — 병합 책임자

`fullops-review`로 현재 기준/worker SHA의 delegate 리뷰를 완료하고 보고서·check 결과·skipped 사유·lint·테스트 결과를 확인한다. 파일 누락이나 미해결 critical/high가 있으면 수락을 보류한다. check 통과만으로 수락하지 않는다. coordinator가 낮은 모델이면 기계적 기준(check·lint·테스트·critical/high)만 직접 판단한다. 설계와 다르게 구현한 것, 범위 이탈, 트레이드오프 판단은 설계 역할이나 사용자에게 넘긴다. 수정 커밋 이후에는 최신 SHA의 리뷰가 필요하다.

보고된 SHA의 브랜치 포함 여부, diff, 커밋 본문, 문서·검증 근거를 확인한다. 허가된 병합을 수행하고 필요한 검증을 실행한다. 실패하면 `PLANS.md`에 미완료 상태를 유지한다.
worker가 쉬고 있고 작업 트리가 깨끗할 때만 기본 브랜치 변경을 상설 브랜치에 merge 또는 fast-forward로 동기화한다. 작업 중이면 동기화를 예약한다. 강제 reset이나 진행 중 작업 삭제를 복구 절차로 쓰지 않는다. 인박스·아카이브가 완료 커밋에 포함됐는지 확인하고 중복 기록하지 않는다.
