---
name: fullops-test
description: FullOps setup이 완료된 레포에서 구현된 동작을 검증하거나 테스트 코드·시나리오를 작성·실행하고 검증 증거를 남길 때 사용한다.
---

# 동작 검증

현재 Git 레포 루트의 `.fullops-squad/fullops.json`이 없으면 setup을 안내한다. 어느 역할이든 동작 검증에 이 도구를 쓸 수 있다. 라우팅 기준의 `- tester 역할:`로 지정된 역할은 세션 시작 때 이 스킬을 받으며, 받은 지시서의 확인할 동작과 통과 조건을 기준으로 검증한다. tester 역할은 제품 코드를 고치지 않고 테스트 코드, 시나리오, 검증 증거만 만든다.

## 도구와 순서

비용이 낮은 도구부터 쓴다. 앞 단계로 판정할 수 있으면 뒤 단계로 가지 않는다.

1. 확정 검사: 값·문구·상태처럼 코드로 판정할 수 있는 것은 테스트 코드로 검증한다. 레포의 테스트 명령(`project.md`)을 따른다. Unity는 `unity test <프로젝트> --mode PlayMode|EditMode --report-format nunit,junit`을 쓰고, 종료코드 0은 통과, 8은 테스트 실패, 6은 컴파일 오류·크래시·시간 초과로 구분해 보고한다. 웹은 레포의 Playwright 등 E2E 테스트를 쓴다.
2. 조작 테스트: 사람이 조작해야 드러나는 흐름은 Jev 조작 도구로 먼저 돌린다. 큰 모델이 화면을 한 단계씩 보며 조작하지 않는다.
   - 웹: 이 스킬 기준 `../../scripts/jev_test_web.py`. Orca 내장 브라우저에 새 탭을 열고, 스냅샷의 요소 번호 중에서 Jev가 동작·대상·입력값을 고른다. 입력할 글자는 시나리오 `values`에서만 고른다. `python3 <jev_test_web.py> --repo <레포 루트> --key <과제 키> --scenario .fullops-squad/docs/evaluations/scenarios/web/<기능>.json`. 시나리오 형식은 `scenarios/README.md`를 따른다. 종료코드 0은 checks 통과, 1은 실패다.
   - 시나리오는 `docs/evaluations/scenarios/`에 기능 단위로 두고 커밋한다. 과제가 끝나도 남아 회귀 테스트가 된다. 지시서가 가리킨 기존 시나리오는 먼저 다시 돌리고, 새 동작은 새 시나리오로 추가한다. 판정은 Jev의 done이 아니라 checks로 한다. 실패하면 `events.jsonl`을 읽고 goal·values·checks를 고쳐 다시 돌린다. 같은 페이지 상태의 Jev 답은 캐시되므로 재실행은 바뀐 스텝만 비용이 든다.
   - Unity: 게임에 브리지가 없으면 먼저 이 스킬 기준 `../../scripts/unity_bridge.py install --repo <레포 루트>`로 심는다. 브리지(`com.fullops.jevplay`)는 Unity 프로젝트의 `Packages/`에 embedded package로 복사되고, 게임별 설정 템플릿 `.fullops-squad/test/unity-play.json`이 생긴다. 설정에 플레이어·배우 그룹(이름 패턴)·읽을 필드(`타입.필드`)·키를 게임에 맞게 적는다. 브리지 코드는 고치지 않는다. 플러그인이 정본이며 `unity_bridge.py check`로 버전을 확인한다.
   - 브리지가 든 플레이어를 빌드한 뒤 `python3 <jev_test_unity.py> --repo <레포 루트> --key <과제 키> --scenario .fullops-squad/docs/evaluations/scenarios/unity/<기능>.json --player <실행 파일>`. 브리지는 결정마다 게임을 멈추고 상태(배우 거리·방향·사거리, 필드, 화면 문구, 가능한 행동)를 내보낸다. Jev는 그 행동 목록에서만 고른다. 필드 오류(`error: … not found`)는 설정의 이름이 게임 코드와 달라진 것이니 설정을 고친다. 게임이 스스로 멈춘 상태(레벨업 선택 등)는 상태의 `gamePaused`로 전달되며, 이때는 이동이 진행되지 않으니 메뉴 키를 설정의 keys에 넣어 둔다. Unity 에디터로 프로젝트를 열거나 빌드하면 `ProjectSettings/`, 렌더 파이프라인 에셋, `Packages/packages-lock.json`이 다시 저장될 수 있다. 과제 범위가 아니면 커밋하지 말고 되돌린다. 브리지 자체의 결함은 로컬에서 고치지 않고 재현 증거와 함께 보고한다(정본은 플러그인).
3. 큰 모델 판정: 이미지로만 판단할 수 있는 시각 품질과 앞 단계 실패의 원인 분석에만 쓴다. 캡처를 판정 근거로 쓰면 파일 경로를 남긴다.

## 시나리오 작성

조작 테스트의 품질은 시나리오가 정한다. `docs/evaluations/scenarios/README.md`의 작성 기준을 따른다. 지시서의 통과 조건을 `covers`로 옮기고, 모든 통과 조건이 어느 시나리오의 checks로 덮이는지 확인한다. goal은 상태에 보이는 이름으로 순서와 끝난 상태, 하지 말 것을 적는다. checks는 goal과 별개로 최종 상태를 구조적으로 확인하고, 일어나지 않아야 할 일도 확인한다. 출발 상태는 `setup_js`나 `player_args`로 고정한다. 정상 흐름과 실패 흐름을 따로 둔다. 실행 전에 `--validate`로 점검한다. 실패하면 Jev가 헤맨 것인지, 기능이 동작하지 않은 것인지, checks가 틀린 것인지 나눠 보고한다.

## 기록

Jev 조작 테스트는 실행마다 `qa-reports/<과제 키>-test/<web|unity>-<시각>/`에 `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용), `report.md`(사람이 읽는 요약)를 남기고 현황판의 테스트 결과에 나온다. 세 파일과 시나리오를 커밋한다. Unity 플레이어 전체 로그(`play/player.log`)는 커밋하지 않고, 실패한 실행은 끝 200줄을 `player-tail.log`로 남긴다. 확정 검사와 그 밖의 검증도 `qa-reports/<과제 키>-test/`에 실행한 명령, 종료코드, 리포트 파일, 통과·실패 항목, 재현 절차를 남긴다. 명령의 종료코드를 파이프로 가리지 않는다. 실패는 직접 고치지 않고 재현 절차와 증거로 완료 보고에 적는다. 지시서의 통과 조건을 바꿔야 한다고 판단하면 preamble의 `ask`로 묻는다.
