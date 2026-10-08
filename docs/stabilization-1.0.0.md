# FullOps Squad 1.0.0 안정화 검증 기록

기준: 이슈 [#6](https://github.com/tourbut/Fullops-Squad-plugin/issues/6),
`e564015b19271193ccc8857f4a2b8f75afcf8c9c` (plugin 0.9.14).
정본은 `plugins/fullops-squad/`이며 native 패키지는 빌드로 생성한다.

## 적용 범위

| 항목 | 구현·검증 경로 | 상태 |
|---|---|---|
| S1 | `lint.py`, `done_gate.py`; pass→실패 무효화·올바른 base·checkout별 직렬 실행·원자적 stamp | 회귀 통과 |
| S2 | `flow_gate.py post`, hooks; pre 전송은 미종결, 현재 dispatch/task/tool ID·exit/Orca receipt 확인 | 회귀 통과; 실제 host 이벤트 미수집 |
| W1/W2/E1 | `jev_test_web.py`, `jev_test_unity.py`, `test_record.py`; 동일 checks·invalid risk·flush·오류 report·실행 식별자 | 가짜 실행기 회귀 및 실제 Jev 응답 통과 |
| R1/R2 | `integration.py`, `review.py`; 명시 배정 경계·관리 snapshot·clean/release/evidence hash·live/historical·멱등 정리 | 임시 Git/Orca stub 및 실제 OCR 통과; 실제 worker release 미실행 |
| C1/C2/C3 | `fullops-orca`, `work.py`, find/context; 하나의 세션 선택·reopen/attempt·fingerprint/history | 문서 대조 및 회귀 통과 |
| D1/D2/D3/D4 | `deliverables.py`, `board.py`; 복수 ID/statuses·일부 전환 거부/명시 전체 전환·실제 md·인계 체크리스트 | 형식/상태 회귀 통과; 아래 의미 점검 별도 |
| I1–I6 | `deps.py`, npm wrapper, `setup.py`, `build.py`; 실제 파일/receipt·공식 손상 복구·대상 비교·journal/rollback·대상 실패 분리·dry-run 설명 | 주입 실패/재시도 회귀 통과; 실제 호스트 설치 미실행 |
| J1–J8 | route/find/context/observe/packet; 민감 fallback·전체 후보 배치·부분 원문 보존·관계 근거·partial docs·과거 지도/rename·한글/예산·known 비용/실측 시간 | stub/임시 Git 및 실제 Jev 검증 통과; 추천 정확도는 아래 지표 |
| U1 | C# bridge 0.1.2의 전체 active 그룹 수, 구 관측의 unknown 부재 판정 | Python/FakeGame 통과; Unity C# 컴파일/Player 미실행 |
| H1 | 실제 실행 Codex 0.160.1, Orca CLI 1.4.222, 설치 plugin 0.9.14·관련 로그 조회 | 오류 원문 없음; 미재현·원인 미확정 |

## 검증 구분

회귀는 임시 Git 저장소와 stub API/브라우저/게임을 사용한다.
실제 Orca worker 수명주기, Unity Player, 사용자 설치 및 기존 세션 업데이트는 별도 검증이다.
미실행을 PASS로 기록하지 않는다. Windows/macOS CI를 추가했으며 로컬 Linux 결과와 구분한다.
H1은 실제 오류 원문을 확보하기 전까지 원인 미확정으로 유지한다.

## 실행한 검사

- `npm ci --ignore-scripts`, `npm test`: 설치기·setup·공통 규칙·Jev·hook·handover·integration·보드·산출물·packaging/schema 통과. 설치기 13개 중 Windows 전용 1개는 Linux에서 skip. 추가 안정화 회귀 17개 통과. route→code/documents find→context→packet→worker 지시·dispatch→API/호출자/테스트 수정→handover archive→lint→review의 동일 과제·SHA 연결도 임시 Git에서 검사했다.
- `python3 tests/review-check.py`: 설치된 OCR 1.12.12의 실제 delegate prepare/rule 및 파일·SHA·lint·독립 snapshot 기록 검사 통과. 기존 coor 구성에서 관리 snapshot을 준비해도 독립 세션 정체성을 기록하는 경로를 확인했다.
- `python3 scripts/build.py`: portable 원본에서 native와 catalogs 재생성. 손으로 생성물을 수정하지 않음.
- `git diff --check`: 통과. 실제 `npm pack`의 1.0.0 manifest·4개 파일·env/key 파일 제외를 확인했다. native 124개 파일의 hash가 반복 빌드 전후 동일하다.
- `FULLOPS_JEV_CACHE_BYPASS=1 python3 tests/jev-observe.py --live-env-file <.env 절대경로>`: 실제 모델 `typesafe/jev-1.13-20260917`, 비용 $0.000082614, 관측 0.687초. 불충분한 증거를 성공으로 올리지 않았음.
- `python3 tests/jev-live.py --env-file <.env 절대경로> --output <새 경로>`: route/code/documents/context/web/Unity 응답의 공통 protocol 검사 및 동일 payload 캐시 대조 통과. 실제 브라우저/게임 조작 검증은 아님.

## PR #9 비공개 리뷰 보완 검증

리뷰의 네 결함을 `tests/stabilization.py`의 회귀 네 개로 재현했다. 수정 전에는 운영 정보 갱신 후 패킷 identity 불일치, Claude 공용 경로의 잘못된 설치 성공, 새 공유 ID의 승인 상속, 인용된 here-doc 문자열 뒤의 dispatch 누락을 확인했다. 수정 후 회귀 네 개와 기존 전체 인계·완료·리뷰 연결 검사 한 개가 Windows에서 통과했다.

목표·기준 SHA·attempt·본문 제약 변경의 해시 감지는 유지한다. Claude 기본 경로와 `CLAUDE_CONFIG_DIR` 경로에서 설치 receipt 기록·파일 삭제 감지·재시도를 검사했다. 기존 공유 ID 승인 보존과 새 ID의 draft 초기화, 명시적 review 전환을 검사했다. 작은따옴표·큰따옴표·여러 줄 인용·이스케이프된 `<<` 뒤의 Run 추적 및 `--run` 필수 검사와 실제 here-doc 본문 제외도 확인했다.

OCR 1.12.12를 격리된 테스트 경로에 설치해 `python3 tests/review-check.py`를 실행했다. 실제 delegate 준비와 독립 snapshot, 파일·SHA·lint·리뷰 기록 관문이 통과했다. 이번 회귀는 임시 저장소와 가짜 설치기를 사용하며, 실제 호스트 스킬 재설치나 Orca worker 세션을 새로 실행한 증거는 아니다.

## 실제 Jev 관측과 정확도 한계

키는 `.env`에서 읽었고 payload·출력·증거에는 넣지 않았다. 1회 합성 과제와 명시적 기대 경로를 사용했다.
최종 원본은 [Jev 결과](evidence/jev-1.0.0.json), 최초 매핑 오류의 원본은 [최초 결과](evidence/jev-1.0.0-initial.json)다.

최종 12호출(캐시 대조 포함)의 확인된 비용은 $0.000839664, 전체 경과는 4.166초다.
동일 payload 재사용은 cached=true·비용 0·동일 answers로 확인했다. 캐시 없는 API 재호출과 구분한다.
최초 테스트는 D05 인덱스가 `interface-design.md`인데 기대 문서를 `api.md`에 작성해 문서 update recall=0이었다.
인덱스 정본과 fixture/label을 일치시켜 다시 실행했다. 최초 비용 $0.000840126도 별도로 보존한다.
초기 세 실제 실행의 총 확인 비용은 $0.001762404이며 실패 응답의 비용을 0으로 추정하지 않았다.

| 명시적 기대 목록 범주 | recall | precision | 해석 |
|---|---:|---:|---|
| 직접 수정 | 1.0 | 1.0 | API 정의 파일 확인 |
| 영향 확인 | 1.0 | 0.667 | 호출자·테스트 확인, API 자체도 영향 후보에 중복 포함 |
| 문서 read | 1.0 | 0.059 | 기대 API 원천 확인; 필수 규칙/인박스·추천 문서가 포함되어 목록이 넓음 |
| 문서 update | 1.0 | 1.0 | 명시한 D05의 정본 원천 확인 |

이 값은 해당 fixture/label의 관측이다. 전체 레포 검색 품질·모든 언어의 참조 그래프나 근거 없는 영향 범위 완전성을 보증하지 않는다.
변경 파일 교집합 지표는 위 읽기·영향·갱신 기대 목록 평가와 별개다. label이 없으면 packet 평가는 not_run이다.
source를 일부만 보냈거나 민감/큰 원문을 못 보낸 파일은 유지/미확인으로 남긴다. 문자열 참조는 추정이며 실제 호출 의미는 검토한다.

## 대화 미참조 인계 점검

이 레포는 플러그인 개발 저장소이며 서비스 하네스를 활성화하지 않았다. README를 시작점으로 기존 문서와 아래 정본을 다시 읽었다.
서비스 D01–D13 템플릿의 형식 검사는 의미 점검을 대신하지 않는다.

| 항목 | 정본 경로 | 실제 결과 |
|---|---|---|
| 현재 요구·보존할 결정 | 이 문서, #6, `docs/releases/1.0.0.md` | 확인: coor 보존, #7 분리, H1 미확정 |
| 구조·수정 위치 | `AGENTS.md`, `docs/development.md`, portable scripts/skills | 확인: portable 정본·adapters·생성 dist 경계 |
| 구현/미완료 | 적용 범위 표, 릴리스 필수/조건부/보류 | 확인: 구현 회귀와 실제 환경 미실행 분리 |
| 실행·검증 | `package.json`, 이 문서의 검사 명령·Jev JSON | 확인: 새 작업자가 키를 재발급하지 않고 기존 env-file로 선택 검증 가능 |
| 운영·복구 | 릴리스 노트, fullops-review/work/orca, setup/deps journal | 확인: 부분 설치·setup 재시도·reopen·snapshot 정리/hold 경로 |
| 다음 작업·재개 조건 | H1·실제 환경 한계·#7 | 확인: H1 오류 원문/이벤트 확보 후 실제 세션 재현; 사용자 설치/전체 worker/Unity·CI 실행 별도 |
| 링크/원천 | README·릴리스·검증 결과 파일 | 로컬 파일 확인. 원격 페이지·Markdown fragment 의미는 이 점검에서 미확인 |
| 임시 공간 정리 후 증거 | 안정화 회귀·review-check | 임시 Git에서 정본 접근/역사 확인 및 변조 거부 확인. 실제 운영 reviewer 종료 미실행 |

## H1 진단 근거

- 실행 중 프로세스의 executable과 PATH CLI를 각각 확인: Codex 0.160.1. 남아 있는 다른 release 디렉터리 버전을 실행 버전으로 추정하지 않음.
- 고정 Orca CLI `/opt/Orca/resources/bin/orca-ide --version`: 1.4.222.
- Codex plugin list와 설치 manifest: 0.9.14. 이번 개발 결과의 1.0.0을 현재 사용자 설치 버전으로 보고하지 않음.
- 해당 레포의 제한된 Orca 로그에서 hook failure/FileNotFound/ModuleNotFound를 찾지 못함. 오류가 없다는 보증이나 업데이트 원인 확정은 아님.
- PostToolUse 계약은 [Codex hooks](https://learn.chatgpt.com/docs/hooks)와 [Claude hooks](https://code.claude.com/docs/en/hooks#posttooluse), 로컬 Orca send/read CLI 구현을 확인했다. post 이벤트 자체를 성공 전달로 가정하지 않고 exit/ok/message receipt를 검사한다. 실제 세션 payload가 다르면 unknown으로 기존 한 번 경고 정책을 유지한다.

## 작업 경계

coor 운영 구조와 기존 문서·사용자 설정을 보존한다. dev 모드 전환은 #7의 후속 작업이다.
이 작업은 소스 수정과 패키지 생성이며 사용자 설치·운영 배포를 포함하지 않는다.

## 동일 과제의 일반 검색/Jev 보조 비교

[비교 원본](evidence/jev-1.0.0-comparison.json)은 같은 합성 과제·40자리 SHA·명시적 API seed·D05 갱신 조건과 같은 기대 경로를 사용한다. 일반 검색은 모델 없이 정의/문자열/링크/원천 매핑을 사용하고, Jev 보조는 같은 검색에 code/documents find 추천과 context 신호를 추가한다.

| 범주 | 일반 검색 recall / precision | Jev 보조 recall / precision |
|---|---|---|
| 직접 수정 | 1.0 / 1.0 | 1.0 / 1.0 |
| 영향 확인 | 1.0 / 1.0 | 1.0 / 0.667 |
| 문서 read | 1.0 / 0.1 | 1.0 / 0.063 |
| 문서 update | 1.0 / 1.0 | 1.0 / 1.0 |

일반 검색 0.071초, Jev 보조 검색 2.266초. 보조 검색의 실제 API 입력 18,234·출력 1,060토큰, $0.000765828이며 일반 검색은 API 호출이 없다. 브라우저/Unity 응답·캐시 대조를 포함한 이번 전체 검증은 입력 19,936·출력 1,247토큰, $0.000837312, 3.702초다. 네 실제 실행의 총 확인 API 비용은 $0.002599716이다.

후속 작업자의 추가 검색·수정/재작업과 호스트의 전체 읽기/구현/리뷰 토큰·총비용은 not_run이다. 이번 작은 fixture에서는 Jev가 정확도나 총비용을 개선했다고 주장할 수 없다. 필수 문맥은 보존됐지만 불필요 읽기 후보의 선별이 필요하며, 모델 추천을 강제 게이트로 쓰지 않는다.

## 잔여 공간

실제 레포의 Git worktree는 현재 개발 체크아웃 하나다. 회귀·OCR·live 검증의 임시 Git/worktree는 테스트 종료 시 정리됐다. 사용자 상설 worktree·설치·세션은 수정/삭제하지 않았다. npm 패키지와 테스트 로그는 검증용 `/tmp`에 두었으며, 재현에 필요한 Jev 원본 JSON만 위 evidence에 보존한다.
