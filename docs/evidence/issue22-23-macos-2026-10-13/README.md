# #22·#23 macOS 실환경 검증 — 2026-10-13

[이슈 #22](https://github.com/tourbut/Fullops-Squad-plugin/issues/22#issuecomment-6141377338)와 [이슈 #23](https://github.com/tourbut/Fullops-Squad-plugin/issues/23#issuecomment-6141382278)의 본문·코멘트를 읽고 macOS에서 실행했다. 기존 Linux 기록은 수정하지 않았다. **두 이슈는 OPEN이며, 아래 결과는 확인한 범위에만 적용한다.**

## 소스와 환경

- 시작 SHA: `1bf607826b5f806d27d11ab278319c63528edae7`.
- 최종 검사·독립 코드 리뷰 SHA: `2c562905d5bd274dd6ff50fe4af0c163a4c2a362`.
- 작업 브랜치: `test/macos-issues-22-23`. 기본 브랜치 병합·push·배포·이슈 댓글 게시·종료는 하지 않았다.
- macOS 26.6.2, build 25G83, ARM64. Node 22.21.1, npm 10.9.4, Python 3.13.2, Orca 1.4.224.
- Codex 0.162.1, Claude Code 2.1.296, Grok 1.0.52. 플러그인 검사 대상 버전은 1.4.1이다.

macOS의 `/var`·`/private/var` 경로 별칭 때문에 `lint.load_config()`가 정상 명령 cwd를 레포 밖으로 오판했다. 공유 함수에서 repo를 먼저 정규화하고, 내부 cwd 허용·외부 cwd 거부 회귀를 추가했다. 운영정책 fixture 한 곳과 모션 fixture 두 곳도 canonical 경로로 맞췄다. 기존 assertion은 유지했다. portable source를 수정한 뒤 `scripts/build.py`로 dist를 생성했다.

## 소스 검사

| 검사 | 판정 | 근거 |
| --- | --- | --- |
| `npm ci --ignore-scripts`, `npm test` | PASS, exit 0 | [최종 argv·종료코드](final-source-checks/checks.json), [전체 회귀](final-source-checks/npm-test.log) |
| `python3 scripts/build.py`, 생성물 diff | PASS, exit 0 | [최종 검사 기록](final-source-checks/checks.json) |
| OCR 1.12.12 실제 delegate 게이트 회귀 | PASS, exit 0 | [로그](final-source-checks/review-check.log) |
| 최신 OCR 1.13.0을 임시 npm prefix에 설치한 실제 게이트 회귀 | PASS, exit 0 | [명령 기록](ocr-latest-checks.json), [버전](ocr-latest-version.log), [로그](ocr-latest-review.log) |
| 실제 최신 shadcn/ESLint 디자인 lint | PASS, invalid exit 1·valid exit 0 | [버전·검사 결과](design-lint.json), [명령 기록](design-checks.json) |
| 고정 SHA 독립 코드 리뷰 | Standards 0건, Spec 0건 | [별도 두 리뷰 세션 기록](independent-review.json) |

전체 회귀 PASS에는 **시스템 Git 2.50.1**을 사용했다. 기존 기본 PATH의 Homebrew Git 2.38.0에서는 missing promisor blob의 offline 무-fetch 회귀가 실패했다. 네트워크 transport는 차단됐으나 Git trace에 fetch 시도가 남았다. 전역 Git·PATH는 바꾸지 않았다. 해당 실패와 각 경로 수정 전 실패 로그를 보존했다. `motion-alias-green.log`라는 초기 파일도 실제로는 두 번째 fixture에서 실패한 로그이며, 이름으로 PASS를 판단하지 않는다. 두 fixture 수정 후 `motion-alias-r02.log`와 최종 전체 회귀가 통과했다.

독립 리뷰는 별도 두 에이전트 세션이 clean detached, filesystem readonly snapshot에서 수행했다. 리뷰어는 전체 회귀를 재실행하지 않았다. OCR 게이트 회귀와 이 독립 코드 리뷰는 별도 근거다.

## 실제 호스트 설치 수명주기

각 CLI에 임시 설정 루트와 고정 SHA 패키지를 사용했다. 이는 전역 의존성 전체 설치 완료 기록이나 실제 UI 작업 성공과 다르다.

| 호스트 | 확인한 범위 | 한계 |
| --- | --- | --- |
| Codex | 설치·중복 설치, GitHub의 고정 ref marketplace refresh·재설치, enabled 설정 전환과 CLI 관측, 없는 플러그인 설치 실패 후 설정 동일 | 로컬 marketplace upgrade는 Git 출처가 아니라 명시적으로 거부됐다. `file://` 출처도 거부됐으며 GitHub 고정 ref로 검증했다. 버전 간 migration은 미검증이다. |
| Claude Code | 의존 marketplace 두 개 선등록, 플러그인·의존 플러그인 실제 설치, 중복 실행, up-to-date 갱신, 비활성화·재활성화, 설치 실패 후 설정 동일 | 임시 인증 루트는 로그인되지 않았으며, 인증된 사용자 환경의 UI 호출도 사용량 제한으로 중단됐다. |
| Grok | 신뢰 미승인 설치 거부, 사용자 승인 후 임시 설정에만 `--trust` 설치, 중복 설치 명시적 거부와 기존 설치 보존, local symlink 갱신, 비활성화·재활성화 설정 확인, 없는 경로 설치 실패 후 inventory 동일 | 실제 버전 교체 migration·호스트 hook 승인 거부 전체는 미검증이다. |

근거: [초기 수명주기](host-lifecycle.json), [Codex GitHub refresh](codex-remote-lifecycle.json), [Grok 승인 후 실행](grok-approved-lifecycle.json), [Grok enabled/disabled 실제 설정](grok-enable-disable-states.json), [Codex·Claude 실패 보존](failed-install-preservation.json), [Grok 실패 보존](grok-failed-install-preservation.json).

## 인증된 작은 UI 작성과 실제 QA

Codex `gpt-6.1-sol / medium`과 Grok `grok-4.6 / medium`의 native CLI에 같은 [brief](native-ui/brief.txt)와 [디자인 정본](native-ui/DESIGN.md)을 전달했다. 두 호스트가 plan·HTML·critique를 실제 응답했다. Grok의 실제 usage model은 `grok-4.6-build`였다. 도구를 통한 파일 편집·브라우저 제어는 이 호스트 호출에 요청하지 않았다. 응답 파일 저장과 QA는 진행 에이전트가 수행했다. 따라서 세 호스트 전체의 FullOps 설계·편집·비평·QA 통합 수락은 아니다.

Claude 호출은 `You've hit your session limit · resets 9:40pm (Asia/Seoul)`로 실패했다. 한도를 우회하거나 자동 재시도하지 않았다. 최초 Codex 호출도 Git 저장소가 없는 경로에서 거부됐으며, 임시 Git 저장소를 만든 뒤 성공했다. 성공한 Codex 호출에는 wiki MCP 인증 오류가 stderr에 별도로 남았다. 이를 MCP 연결 성공으로 처리하지 않는다.

초기 UI SHA `432a7d514baf7b59dc418f4fb31ce7e0e6dce64f`의 Grok 출력에는 다음 결함이 있었다.

- 실제 모바일 context 320·390px에서 viewport가 980px로 잡혔다.
- 독립 리뷰가 입력 경계의 light/dark 대비 부족을 발견했다.

원본 HTML·리뷰·[실패 결과](native-ui/qa-original/result.json)를 보존하고 **같은 Grok 세션**에서 R01을 생성했다. 최종 UI SHA는 `8282999e4b674da3c0720f77f0f37cd3b0a936dd`다. 별도 독립 코드 리뷰에서 경계 대비는 light 6.69:1/6.07:1, dark 4.94:1/5.24:1로 확인돼 원래 지적을 해소했다. Codex 결과물은 변경하지 않았다.

- [Playwright R01 QA](native-ui/qa-r01/result.json): 두 호스트 × 320·390·1280px × 17개 검사, **102개 PASS**. viewport·가로 넘침·초기 빈 상태·테마 왕복·Enter/Space·포커스·reduced-motion·단일 제출·checkbox·반복 제출·disabled control·runtime 오류를 확인했다.
- [실제 Orca R01 재생](native-ui/orca-qa/result.json): 두 HTML에서 테마·단일 제출·checkbox의 독립 checks 각 3개 PASS. 해당 재생의 Jev 호출은 0이다. 테스트가 만든 탭만 닫았다.
- light/dark screenshot 12개를 R01 폴더에 보존했다. 진행 에이전트는 Codex 320 light, Grok 320 light·1280 dark를 직접 열어 잘림·겹침·가독성을 확인했다. 전 캡처의 별도 시각 검수나 제품 디자인 승인은 아니다.
- 브라우저는 새 credential 없는 context·loopback fixture를 사용했다. Playwright는 fixture GET 외 모든 요청을 차단했다. Orca는 요청 차단 기능이 없어 독립 리뷰한 코드와 사전 허용 DOM 동작만 실행했고, 외부 링크·form·POST probe는 실행하지 않았다.

계획된 예산을 실제 강제한 CUAWright 작업은 아니다. 초기·R01 native 응답의 token/usage는 각 원본 로그에 있다. Grok 두 완료 호출의 CLI 보고 비용 합은 **$0.04349824**다. Codex 비용은 CLI가 보고하지 않아 `unknown`이다. Claude 실패 응답의 CLI 보고 비용은 0이며 전체 provider 청구액·진행 에이전트 비용을 뜻하지 않는다.

## Orca·Playwright 반복 회귀

[요약](browser-summary.json)은 각 실행기에서 정상 3회·알려진 제출 횟수 결함 3회, 총 6개 `elapsed_s`를 집계한다. 두 실행기는 각 iteration 안에서 같은 loopback fixture·scenario SHA·독립 checks를 사용했다. iteration 간 임시 포트가 달라 scenario SHA는 동일하다고 주장하지 않는다.

| 실행기 | 정상 PASS | 결함 검출 | false PASS / false failure | p50 / nearest-rank p95 |
| --- | --- | --- | --- | --- |
| Orca 1.4.224 | 3/3 | 3/3 | 0 / 0 | 32.8645s / 37.839s |
| Playwright CLI 0.1.22, runtime 1.64.0-alpha-1790635538000, Chromium 155.0.8059.12 | 3/3 | 3/3 | 0 / 0 | 0.6035s / 4.395s |

이는 시작 SHA의 모델 없는 한 종류 결함 재생이다. 최종 변경은 lint와 테스트 fixture이며 웹 실행기 코드는 바꾸지 않았다. 실제 브라우저 재생·native UI QA·CUAWright는 구분한다. stale DOM, occlusion, 외부 origin/form 목적지 거부와 Playwright의 미승인 동일-origin POST 차단도 반복 확인했다. 실행기별 브라우저 버전이 다르고 cache·cold/warm을 통제하지 않았다. 속도 우열·일반적 재현율·비용 개선을 주장하지 않는다. 결함 분류는 에이전트가 삽입 변이를 확인한 것이며 사람 ground truth와 shadow 라벨은 수집하지 않았다. 이 회귀의 Jev 호출·API 비용은 0이고 native UI 생성 비용은 별도다.

## 설정 보존과 남은 조건

[검증 전](global-config-before.json)·[검증 후](global-config-after.json) 8개 파일의 byte hash를 비교했다. 6개는 동일했고 **`.codex/config.toml`과 `.claude.json`은 달랐다.** 정확한 검증 전 원문을 별도로 보존하지 않아 두 파일의 원인 귀속·완전 보존을 확정할 수 없다. 사용 중인 사용자 설정을 임의로 복원하지 않았다. 기존 자동 backup과의 비교에는 프로젝트·hook trust·runtime cache/metrics 등이 포함됐지만, 그 backup은 시작 hash와 일치하지 않아 전후 diff의 대체 근거로 쓰지 않는다. Codex 설정에 이번 임시 프로젝트 경로가 등록되지는 않았다. 전역 설정 전체 보존 조건은 UNVERIFIED다.

[macOS CUAWright 준비](cuawright-prepare-r01.json)는 **BLOCKED**다. 활성 호스트의 `cuawright-web`, Python Playwright·Firefox가 없으며 host의 총 token 예산 강제도 확인하지 못했다. 90초·20,000 token은 준비 메타데이터의 계획값이지 실행된 한도가 아니다. 생성·생성 코드 실행·시각 검수·결정적 회귀 승격은 `not_run`으로 남긴다. 앞선 `cuawright-prepare.json`은 harness 경로 오류로 CLI가 시작되지 않은 기록이며, 실제 준비 결과와 구분한다.

#22의 남은 범위는 Claude 완료 세션, 세 호스트의 실제 도구 편집·브라우저 QA 통합, 신규/기존 설치의 실제 버전 교체·의존성 완료/provenance, 실제 auth·hook 거부 전체, React/비 React 전체 작업과 선택한 경우의 MCP/Impeccable 실연결, loading/error/cancel/back 및 실제 제품 상태 전체, 전역 설정 보존 확인이다. 실제 TSX lint 검사를 전체 React 앱 수락으로 확대하지 않는다. i-docs 코드는 수정하거나 QA하지 않았다.

#23의 남은 범위는 CUAWright 실제 생성·수정·리뷰·실행·승격, 기존 E2E/Jev/CUAWright까지 조건을 맞춘 비교, 사람 라벨·shadow 수정 사유, 일반적 결함 표본·실제 청구 비용·API 실패·통제된 cold/warm 반복 측정이다. macOS의 Orca 연결과 위 두 native 호스트 fixture 실행 범위만 새 근거로 추가한다.

## 재현과 파일 무결성

원본 stdout/stderr와 실행 argv·exit를 보존했다. harness 일부는 실행 당시 임시 경로를 포함하므로 새 환경에서는 같은 고정 SHA snapshot과 로컬 tool prefix를 준비해 경로를 대입해야 한다. `sha256.json`은 자기 자신을 제외한 이 폴더의 모든 파일을 검증한다.

```text
npm ci --ignore-scripts
npm test
python3 scripts/build.py
python3 tests/review-check.py
python3 tests/shadcn-lint.py --tools <latest local lint tools> --out <new result.json>
python3 tests/web-browser.py --engine both --playwright-package <local @playwright/cli/package.json> --worktree <connected Orca checkout> --out <new output>
```

회귀의 Git에는 2.50.1을 선택했고 OCR 최신 검증에는 임시 prefix의 1.13.0을 PATH 앞에 배치했다. 전역 toolchain을 업데이트하지 않았다.
