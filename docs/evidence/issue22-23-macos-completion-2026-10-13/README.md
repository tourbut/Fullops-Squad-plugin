# #22·#23 macOS 완료 검증 — 2026-10-13

이슈 본문과 기존 코멘트를 읽고 보완 검증했다. 사용자는 **Claude 테스트 제외**, **추가 반복 측정 중단·최소 검사 후 이상 없으면 종료**, **테스트 결과 이슈 코멘트 등록**을 지시했다. 기존 Linux·macOS 기록과 실패/unknown은 수정하지 않았다. 최종 이슈 종료는 PR #26의 마지막 CI 확인 후 코멘트로 기록한다. 기본 브랜치 병합·배포는 이 검증의 완료 범위가 아니다.

## 소스 수정과 검증

최종 구현 SHA는 `5469cc96a2d49166817128aed5f552682f5d2407`이다. 최초 macOS 경로 정규화 수정에 이어 실제 Orca/Jev 호출에서 발견한 입력 결함을 수정했다.

- macOS `/var`·`/private/var` 별칭: repo를 먼저 resolve하여 정상 cwd를 레포 밖으로 오판하지 않게 했다.
- 독립 fan-out 질문이 다른 질문의 criteria/답을 볼 수 없는데, 동작·위험·유효성 질문에 실제 화면/값이 빠져 있었다. 정제된 요소·fixture 값·허용 동작을 공유하고 유효성 질문이 해당 상태와 역할을 직접 참조하게 했다.
- 허용되지 않은 `fill`과 허용된 `fill_submit`이 함께 제시되어 보류되던 선택지를 권한과 맞췄다. **실행 권한 gate는 별도로 유지**했다.
- 후보 254개에서 중복 payload가 입력 예산을 초과하던 중간 회귀를 보존하고, 후보를 중복 전송하지 않도록 수정했다. 예산·confidence·위험 임계값을 올리거나 낮추지 않았다.

[RED](jev-shared-state-red.log), [선택지 RED](jev-operation-policy-red.log), [GREEN](jev-operation-policy-green.log), [22개 엔진 회귀](web-engine-r07.log), [전체 npm test](npm-test-r07.log)가 있다. 생성물은 `scripts/build.py`로 재생성했다. 전체 회귀에는 시스템 Git 2.50.1을 사용했다. Homebrew Git 2.38.0의 기존 offline missing-blob 실패는 이전 기록에 남아 있다. [최신 OCR 1.13.0 게이트](review-check-latest-r07.json)는 최종 소스에서 통과했다. `review-check-r06.log`는 PATH 경로 오기 때문에 전역 OCR 1.12.12를 사용한 원본이며 최신 버전 증거로 취급하지 않는다. 실제 선택 경로·버전·exit 0은 새 r07 기록에 있다. 이는 아래 독립 리뷰와 별도 검사다.

최종 SHA의 [Standards 리뷰](source-review-standards-r07.json)와 [Spec 리뷰](source-review-spec-r07.json)는 독립 세션·clean detached readonly snapshot에서 수행했으며 발견 사항 0건이다. 권한 gate 음성 테스트는 upstream 결정만 주입하고 기존 `blocked_policy`·`acts=[]` oracle을 그대로 유지한다.

## #22 — 실제 호스트와 UI

| 항목 | 확인 결과 / 근거 |
|---|---|
| Codex·Grok 설치 수명주기 | 이전 실제 설치·반복·비활성화·실패 보존 기록을 유지했다. [Codex 버전 전환](version-transition/runs.json)에서 실제 inventory 1.4.0→1.4.1 확인. Grok updater는 exit 0인데 inventory 1.4.0 유지하는 host 한계가 재현됐고, owned 임시 설치만 `--keep-data` 제거·승인된 1.4.1 재설치하여 [inventory 1.4.1](version-transition/grok-recovered-inventory.json)로 복구했다. 이를 updater 정상 PASS로 쓰지 않는다. |
| 외부 스킬·도구 출처와 완료 기록 | 전용 HOME·CLI 설정·npm prefix에서 실제 deps 설치와 check 수행: [Grok](deps-real/runs.json), [Codex](deps-real-r01/runs.json) 모두 최종 exit 0. receipt와 skill source lock을 보존했다. 첫 Codex 빈 home 오류도 원본 유지. |
| 설계→파일 구현→비평→브라우저 QA | 같은 DESIGN/tokens/fixture로 native Codex와 Grok이 실제 파일 도구와 QA 명령을 실행했다. host QA 각 48개 통과. [Codex 소스](ui-source/codex/index.html), [Grok 소스](ui-source/grok/index.html), [native 명령](native-workflow/runs.json), [Grok QA 재개](native-workflow/grok-resume-run.json). 처음 허용 명령 뒤 echo를 붙여 거부된 결과는 보존했다. |
| 호스트 전환 보존 | [Codex→Grok 실제 handoff](host-handoff/result.json)에서 디자인·토큰·코드·테스트·기존 증거 해시 동일, 새 QA 통과. |
| React/비 React 실제 디자인 lint | 이전 TSX shadcn/ESLint invalid exit 1·valid exit 0. 새 [비 React Stylelint 17.16.0](nonreact-design-lint/result.json)은 두 최종 UI CSS 모두 valid exit 0·토큰 위반 invalid exit 2. 선택하지 않은 shadcn MCP·Impeccable engine 연결은 성공으로 주장하지 않는다. |
| 모바일·키보드·상태 흐름과 독립 QA | 최종 Codex UI SHA `3a361d576441b9bd7633b4641911c3388416e7b1`: [독립 60개 검사/화면 리뷰](ui-independent-codex-r02/review.json). Grok UI SHA `7e7a4d2f5830233317abcca787ec180b3041625e`: [독립 114개 검사/화면 리뷰](ui-independent-grok-r02/review.json). 320/390/1280, focus·modal·theme·reduced motion·loading/empty/error·retry/cancel/back 등을 실제 확인했다. 넓은 제품 전체 QA는 아니다. |
| 실패·설정·gate 보존 | 실제 Codex 무인증 요청은 401, 임시 설정 동일. Grok 미신뢰 hook/MCP 패키지 설치 거부, 없는 도구·설치 실패 기록 유지. Grok 빈 home의 headless/TTY 문제·자동 로그인은 실제 인증 실패 PASS로 취급하지 않는다. 최종 필수 회귀와 gate는 유지했다. |

[UI 소스 git bundles](provenance/)에 고정 SHA를 복원할 수 있는 원본을 보존했다. Claude는 사용자가 제외했으며 성공으로 처리하지 않는다. 이전 실행의 Codex 전역 설정 변경 원인 `UNKNOWN`도 그대로다.

새 완료 단계의 보호 파일은 8개 중 7개 해시가 동일했다. `.claude.json`은 외부 프로젝트 실행 통계·feature/usage cache 등이 변경됐다. [키 이름만 기록한 비교](claude-project-metadata-diff.json), [해시 원본](global-preservation.json)을 보존했다. 사용자 권한·trust 설정 변경을 관측하지 않았으나 **전체 8개 byte 보존 PASS는 주장하지 않으며 원인을 단정하거나 자동 복원하지 않았다**. raw 설정과 인증 값은 게시하지 않았다.

## #23 — CUAWright와 비교

공식 CUAWright `ff44a0524e0812b69814efcec5e583f0d8cdde0c` / 0.2.0의 스킬을 임시 환경에서 적용했다. Python Playwright 1.63.0, Firefox 155.0을 사용했다. 새 API 키나 Jev 이미지 판정은 추가하지 않았다.

- Grok `grok-4.6`→실제 `grok-4.6-build`, effort medium에서 계획→생성→수정했다. 최종 [bounded 생성](cua-bounded-reproduction-run.json)은 180초·max 2 turns·completion 8192 설정에서 실제 model calls 2, output 2013으로 완료했다. input/cache token 수는 별도 기록하며 total-token hard cap을 주장하지 않는다. 응답 preface와 한 번 과도하게 escape된 ASCII 문자열을 결정적으로 복구했으며 **기존 독립 리뷰 코드와 byte-identical**임을 해시로 확인했다. 원본 응답도 보존했다.
- 처음 4096 completion 예산을 넘긴 output 5310과 same-session 180초 timeout 비용/사용량 unknown을 보존했다. 새로운 성공으로 이전 위반을 PASS로 바꾸지 않았다.
- 최종 CUA 코드 SHA `6c900b2b7d5ad1dbcc6f86a95e7efa86a6f762dd`, script SHA-256 `bd0133331419ab3f247be515f4e9bb289c2b139855048298576100711c50d6d2`. [실행 전 독립 승인](cua-preexecution-standards-r03.json), [별도 화면 리뷰](cua-visual-r03.json), [원본 bundle](provenance/cua-source.bundle).
- macOS 중첩 sandbox 때문에 첫 Firefox 실행이 실패했다. Firefox 자체 sandbox를 끄지 않고, 새 browser broker와 OS sandbox 안의 Python client를 분리해 재실행했다. 외부 파일 쓰기·보호 파일 읽기·외부 TCP 거부 [probe](sandbox-probes.json), fresh context·loopback GET allowlist·WebSocket 차단·비밀 없는 fixture를 사용했다. Firefox background traffic은 client OS 제한 밖이라는 [한계](cua-topology-review-r01.json)를 명시한다.
- 외부 oracle이 정확한 테마·제출 수·행 수·행 문자열·체크 상태를 검사했다. 생성 코드의 FINAL_RESPONSE나 exit 0만으로 PASS를 만들지 않았다.
- [모델 없는 회귀로 고정한 경로](cuawright/regression-manifest.json)를 default milk·alternate bread 및 seeded cases에서 재생했다. 정상 5 PASS·결함 9 FAIL, 새 bounded 생성 후 fresh run19도 PASS. [명령/로그/캡처](cuawright/)와 [독립 판정](cua-replay/runs.json)이 있다.

[사람 라벨](human-ground-truth.json)은 실제 상태 요약을 보고 사용자가 답한 **A 정상, B·C·D 결함**이다. blinded visual 연구나 넓은 제품 결함 recall로 확대하지 않는다.

| 완료된 표본 | 정상 | 알려진 삽입 결함 | false PASS |
|---|---|---|---|
| 직접 결정적 E2E | 3/3 PASS | 9/9 외부 invariant 검출 | 0 |
| CUAWright 모델 없는 재생 | 3/3 PASS | 9/9 외부 invariant 검출 | 0 |
| 기존 선택형 Playwright | 3/3 PASS | 3개 invariant 검출, 6개 ambiguity/action failure로 검사가 미완료 | 0 |
| 기존 Orca replay | 3/3 PASS | 6개 invariant 검출, 3개 ambiguity로 검사 미완료 | 0 |
| 최종 수정 Orca/Jev | 3/3 PASS | 완료된 6개에서 각 seeded invariant 위반 확인 | 0 |

[항목별 p50/p95·호출·token/bytes·비용과 이전 실패](comparison-summary.json)를 보존했다. 최종 R07은 9개 완료 결과이며 43개 실제 응답의 비용에는 중단된 다음 실행의 호출도 포함한다. 중단된 결과를 PASS/0회로 채우지 않았다. **추가 반복·조건 정렬은 사용자의 최소화 지시로 중단**했다. 도구/브라우저 버전·viewport 차이가 있어 속도·비용 우열을 주장하지 않는다. 추가 정렬 단계의 일부 기록도 별도 파일에 보존했다.

[cache cold/warm](cache-api/cache-runs.json)은 앱 응답 cache만 새 경로로 통제한 3쌍이며 OS·provider cache는 통제하지 않았다. [API 실패 15개](cache-api/failure-runs.json)는 local 401/429/503/malformed/timeout의 요청 실패·무재시도 검사다. 실제 외부 provider 장애로 주장하지 않는다. 이전 실제 timeout 비용은 unknown이다. shadow 원본·사람 fixture 라벨·수정 사유는 각 comparison 폴더에 별도 key로 보존했으며 기존 결과/gate를 덮어쓰지 않았다.

## 재검증과 보존

`harness/`는 실행한 임시 harness 원본이며 절대 경로·port가 당시 환경에 묶여 있다. 안전한 재실행은 새 임시 venv/browsers/loopback fixture와 paths를 준비한 뒤 고정 code hash를 확인하고 trusted oracle/broker와 함께 수행한다. 그대로 다른 tenant에 실행하는 명령은 아니다. CUAWright는 기본 OFF이며 npm test의 필수 유료/브라우저 의존성을 늘리지 않았다.

[최종 범위와 항목별 판정](result.json), [사용자 범위 축소](user-scope-reduction.json), [독립 종료 조건 검토](issue-closure-spec-audit-r02.json), [파일 해시](sha256.json)를 함께 본다. 인증 파일·raw 개인 설정·npm token·새 유료 키는 증거 디렉터리에 포함하지 않았다.
