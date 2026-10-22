---
name: fullops-test
description: FullOps setup이 완료된 레포에서 구현된 동작을 검증하거나 테스트 코드·시나리오를 작성·실행하고 검증 증거를 남길 때 사용한다.
---

# 동작 검증

`fullops.json.test_level`과 지시서의 선택 레벨을 읽고 rules/common/testing.md의 minimal·lite·standard·full·exhaustive 범위를 적용한다. 필수 검사와 독립 QA·최종 수락은 유지하며 범위 밖·미실행 검사는 사유를 남기고 PASS로 표시하지 않는다. 정한 검사가 통과하면 인계하고 새 변경·실패·증거 결함이 있을 때만 반복한다. 하위 검증을 나누면 rules/delegation.md의 선택 범위·동시 예산을 적용하며 테스트 레벨을 높여 해석하지 않는다.

문서를 작성하거나 검토할 때 `.fullops-squad/docs/agents/document-writing.md`의 front matter와 한국어 STE 작성 원칙을 적용한다. 기존 레포에 이 파일이 없으면 `setup-fullops` 갱신으로 추가한다.

현재 Git 레포 루트의 `.fullops-squad/fullops.json`이 없으면 setup을 안내한다. 어느 역할이든 동작 검증에 이 도구를 쓸 수 있다. 라우팅 기준의 `- tester 역할:`로 지정된 역할은 세션 시작 때 이 스킬을 받으며, 받은 지시서의 확인할 동작과 통과 조건을 기준으로 검증한다. tester 역할은 제품 코드를 고치지 않고 테스트 코드, 시나리오, 검증 증거만 만든다.

## 도구와 순서

프런트엔드 UI/UX 검증은 `fullops-frontend/delivery.md`의 상태·디자인 정본·선택 도구·QA 계약을 현재 지시서에서 확인한다. Jev 키가 없으면 기존 프로젝트 E2E나 선택한 로컬 브라우저 도구로 가능한 검사를 수행하고 대안·미실행을 구분한다. CLI 존재나 디자인 비평으로 브라우저 QA를 통과 처리하지 않는다.

웹 실행기의 기본 Orca, 선택 Playwright·ego, 현재 탭 연결, 권한/예산, 고정 회귀와 기본 OFF 탐색·shadow·CUAWright는 [web-engine.md](web-engine.md)를 따른다. 실제 실행기·격리 fixture·허용 origin/효과·독립 assertions·검사 완료 범위를 지시서와 증거에 기록하고 필수 회귀·보안 검사를 유지한다. 도구 설치나 PoC 준비 완료를 브라우저 QA 통과로 보고하지 않는다.

모션그래픽 영상 산출물의 검수는 `fullops-motion`의 `delivery.md`를 읽고 파일 규격·장면/전환/마지막 프레임·텍스트 구간·음성 기술/실제 청취·내용 정확성을 별도 판정한다. 결과는 이 스킬의 기존 QA 경로에 남긴다.

`.fullops-squad/rules/common/testing.md`의 `담당과 반복 범위`를 읽고 지시서의 검사별 담당·대상·시점·통과 조건을 확인한다. DEV의 관련 회귀와 tester의 전체 수락 QA를 구분한다. 재사용할 증거와 이번에 실행할 범위를 정하며, 캡처·영상은 지정된 시각 판정에 필요한 자료만 만든다.

비용이 낮은 도구부터 쓴다. 앞 단계로 판정할 수 있으면 뒤 단계로 가지 않는다.

1. 확정 검사: 값·문구·상태처럼 코드로 판정할 수 있는 것은 테스트 코드로 검증한다. 레포의 테스트 명령(`project.md`)을 따른다. Unity는 `unity test <프로젝트> --mode PlayMode|EditMode --report-format nunit,junit`을 쓰고, 종료코드 0은 통과, 8은 테스트 실패, 6은 컴파일 오류·크래시·시간 초과로 구분해 보고한다. 웹은 레포의 Playwright 등 E2E 테스트를 쓴다.
2. 조작 테스트: 사람이 조작해야 드러나는 흐름은 Jev 조작 도구로 먼저 돌린다. 큰 모델이 화면을 한 단계씩 보며 조작하지 않는다.
   - 웹: 이 스킬 기준 `../../scripts/jev_test_web.py`. 기본 Orca에서 Jev가 관측한 요소 중 동작·대상·시나리오 값 ID를 고른다. `python3 <jev_test_web.py> --repo <레포 루트> --key <과제 키> --scenario .fullops-squad/docs/evaluations/scenarios/web/<기능>.json`. 사용자가 연 탭은 `--page <ID>`, 독립 검사만은 `--assert-only`, 모델 없는 고정 회귀는 `--replay <JSON>`, 선택 실행기는 `--engine playwright`와 `--engine ego`다. 시나리오 형식은 repository의 `docs/evaluations/scenarios/README.md`를 따른다. 종료코드 0은 기록된 범위의 통과, 1은 실패·중단이다.
   - 시나리오는 `docs/evaluations/scenarios/`에 기능 단위로 두고 커밋한다. 지시서가 가리킨 기존 시나리오는 먼저 다시 돌리고, 새 동작은 새 시나리오로 추가한다. 판정은 Jev의 done이 아니라 checks와 완료 범위로 한다. 실패하면 `events.jsonl`에서 제품·시나리오·환경·탐색 결함을 구분하고 해당 담당자가 고친다. 통과시키려고 checks를 약화하지 않는다. 정확히 같은 요청만 캐시를 재사용하며 상태 ID 변경 시 캐시 재사용은 보장하지 않는다.
   - Unity: 게임에 브리지가 없으면 먼저 이 스킬 기준 `../../scripts/unity_bridge.py install --repo <레포 루트>`로 심는다. 브리지(`com.fullops.jevplay`)는 Unity 프로젝트의 `Packages/`에 embedded package로 복사되고, 게임별 설정 템플릿 `.fullops-squad/test/unity-play.json`이 생긴다. 설정에 플레이어·배우 그룹(이름 패턴)·읽을 필드(`타입.필드`)·키를 게임에 맞게 적는다. 브리지 코드는 고치지 않는다. 플러그인이 정본이며 `unity_bridge.py check`로 버전을 확인한다.
   - 브리지가 든 플레이어를 빌드한 뒤 `python3 <jev_test_unity.py> --repo <레포 루트> --key <과제 키> --scenario .fullops-squad/docs/evaluations/scenarios/unity/<기능>.json --player <실행 파일>`. 브리지는 결정마다 게임을 멈추고 상태(배우 거리·방향·사거리, 필드, 화면 문구, 가능한 행동)를 내보낸다. Jev는 그 행동 목록에서만 고른다. 필드 오류(`error: … not found`)는 설정의 이름이 게임 코드와 달라진 것이니 설정을 고친다. 게임이 스스로 멈춘 상태(레벨업 선택 등)는 상태의 `gamePaused`로 전달되며, 이때는 이동이 진행되지 않으니 메뉴 키를 설정의 keys에 넣어 둔다. Unity 에디터로 프로젝트를 열거나 빌드하면 `ProjectSettings/`, 렌더 파이프라인 에셋, `Packages/packages-lock.json`이 다시 저장될 수 있다. 과제 범위가 아니면 커밋하지 말고 되돌린다. 브리지 자체의 결함은 로컬에서 고치지 않고 재현 증거와 함께 보고한다(정본은 플러그인).
3. 큰 모델 판정: 이미지로만 판단할 수 있는 시각 품질과 앞 단계 실패의 원인 분석에만 쓴다. 캡처를 판정 근거로 쓰면 파일 경로를 남긴다.

## 시나리오 작성

조작 테스트의 품질은 시나리오가 정한다. `docs/evaluations/scenarios/README.md`의 작성 기준을 따른다. 지시서에서 이번 조작 테스트가 맡는 통과 조건을 `covers`로 옮기고, 각 조건이 어느 시나리오의 checks로 덮이는지 확인한다. 자동 검사·시각 검수·후속 QA가 맡는 조건은 해당 근거와 담당을 연결한다. goal은 상태에 보이는 이름으로 순서와 끝난 상태, 하지 말 것을 적는다. checks는 goal과 별개로 최종 상태를 구조적으로 확인하고, 일어나지 않아야 할 일도 확인한다. 출발 상태는 `setup_js`나 `player_args`로 고정한다. 정상 흐름과 실패 흐름을 따로 둔다. 실행 전에 `--validate`로 점검한다. 실패하면 Jev가 헤맨 것인지, 기능이 동작하지 않은 것인지, checks가 틀린 것인지 나눠 보고한다.

## 기록

Jev 조작 테스트는 실행마다 `qa-reports/<과제 키>-test/<web|unity>-<시각>/`에 `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용), `report.md`(사람이 읽는 요약)를 남기고 현황판의 테스트 결과에 나온다. 세 파일과 시나리오를 커밋한다. Unity 플레이어 전체 로그(`play/player.log`)는 커밋하지 않고, 실패한 실행은 끝 200줄을 `player-tail.log`로 남긴다. 확정 검사와 그 밖의 검증도 `qa-reports/<과제 키>-test/`에 실행한 명령, 종료코드, 리포트 파일, 통과·실패 항목, 재현 절차를 남긴다. 커밋하는 파일은 보고서의 판정 항목이 링크하는 것만이다. 통과 항목 캡처, 첫 실행 실패본, HTML·DOM 스냅샷, 완료 SHA 이전의 gate 로그는 `qa-reports/<과제 키>-test/raw/`(gitignore)에 둔다. 같은 화면의 시각 검수 캡처는 지시서가 정한 한 역할만 만든다(`rules/common/testing.md`의 `담당과 반복 범위`). 캡처 폭·테마 수와 독립 QA·시각 검수 배정은 테스트 레벨을 넘지 않는다. 같은 과제의 재검증은 기존 report.md에 절을 덧붙인다. 커밋 때 hook이 report가 링크하지 않은 qa-reports 캡처와 같은 과제의 차수 폴더(`-FIX`·`-RECHECK`·`-R2` 등)를 막는다. 명령의 종료코드를 파이프로 가리지 않는다. tester는 제품 결함을 직접 고치지 않고 재현 절차와 증거로 완료 보고에 적는다. 구현 담당자는 자기 소유 범위의 결함을 수정하고 관련 회귀를 실행한다. 지시서의 통과 조건을 바꿔야 한다고 판단하면 preamble의 `ask`로 묻는다.
