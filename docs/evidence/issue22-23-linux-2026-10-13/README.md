# #22·#23 Linux 검증 기록

2026-10-13에 기존 배포 SHA `6cc213882fc4b1d69d4a619e8ee62bb790a17cba`를 임시 Git 저장소에 고정해 검증했다. 검증 중 사용자 요청으로 모든 외부 의존성의 설치 정책을 latest로 변경했다. 정책 구현 SHA는 `011edc0ec7120ba4624aec389544d9aadf202bd3`이며 최종 패키지는 1.4.1로 준비한다.

## 판정

**#22와 #23은 OPEN이다.** 아래 통과 항목은 기록된 범위에만 해당한다. 패키지·스킬 설치나 모델 없는 회귀를 인증된 호스트 UI 작업·CUAWright 실행·일반적 결함 재현율로 해석하지 않는다.

- `baseline-*`: 변경 전 전체 회귀, 의존성 검사 실패, Orca·Playwright 반복 실행 기록이다. 스킬 출처 기록, OCR 고정 버전 불일치, 일부 호스트의 완료 기록 때문에 기존 의존성 검사가 실패했다.
- `latest-*`: latest 정책 코드의 전체 회귀·OCR 게이트·브라우저·npm 도구 확인·프로젝트 범위 스킬 설치 기록이다. 실제 설치된 OCR의 고정 버전 불일치는 새 정책에서 사라졌다. 기존 전역 스킬의 출처와 호스트 완료 기록은 별도 복구 대상이다.
- `frontend-*`: 최신 Playwright CLI를 임시 레포 안에 설치하고 재실행, 세 호스트 준비 상태 조회, 비활성화, 실행 파일 누락·원복, npm 실행 불가를 검사했다. CLI 도구 상태는 확인했지만 호스트 인증·브라우저 QA·MCP 연결은 계속 `not_run`으로 남았다.
- `global-config-*`: 검증 전후 사용자 설정 다섯 파일의 해시 차이는 0이다. 이 검증은 전역 도구 설치·플러그인 캐시 교체·i-Docs 수정을 수행하지 않았다.

## 반복 브라우저 검사

두 실행기는 같은 loopback fixture에서 같은 시나리오 SHA와 독립 checks를 사용했다. 각 실행기에서 정상과 제출 횟수 삽입 결함을 각각 3회 재생했다. 정상 통과 3회, 알려진 결함 검출 3회이며 이 표본의 false PASS와 false failure는 0이다. Jev 호출과 API 비용은 0이다.

`baseline-browser-summary.json`의 p50·p95는 실행기별 정상 3회와 결함 3회를 합친 6개 기록의 `elapsed_s` 통계다. p95는 nearest-rank다. 서로 다른 브라우저 버전을 사용했고 시작 시점의 OS 캐시를 통제하지 않았으므로 성능 개선이나 cold/warm 결과로 주장하지 않는다. 정상/결함 분류는 fixture 코드와 삽입 변이를 에이전트가 확인한 것이며 사람 라벨 수집은 수행하지 않았다.

latest 정책 변경 후에도 `tests/web-browser.py --engine both`를 실행했다. 정상 통과, 삽입 결함 검출, stale DOM, 가림, 외부 origin·form 목적지 제한, Playwright의 미승인 POST 차단을 확인했다. `latest-browser-comparison.json`이 근거다.

## 재현 명령

```text
npm ci --ignore-scripts
npm test
python3 tests/review-check.py
python3 scripts/build.py
python3 tests/web-browser.py --engine both --playwright-package <로컬 @playwright/cli/package.json> --worktree <연결된 Orca 워크트리> --out <새 증거 폴더>
```

브라우저·선택형 도구는 별도 준비가 필요하다. 최초 Chromium 캐시는 ICU 데이터 오류로 실행하지 못해 임시 경로에 새 headless browser를 받았다. 새 브라우저 검증은 통과했다. `baseline-cuawright-poc.json`은 변경 전 준비 결과이며 `BLOCKED`를 보존한다. Python Playwright·Firefox와 활성 호스트 스킬이 없어 생성·실행·시각 검수는 수행하지 않았다. 이 파일의 후보 host/model/effort는 실행 증거가 아니다.

## 남은 완료 조건

#22는 세 호스트의 실제 설치·업데이트·비활성화·실패 복구 세션, 같은 UI 과제의 설계·구현·비평·QA, React/비 React 실제 디자인 lint, 전체 상태·상호작용, 인증·hook 승인 실패, 최종 SHA의 독립 리뷰가 남았다.

#23은 CUAWright 생성·수정·재실행과 고정 SHA 독립 리뷰·격리·시각 검수, 생성 경로의 결정적 회귀 승격, 기존 E2E·Jev·Playwright·CUAWright의 조건을 맞춘 비교, 사람 ground truth·shadow 라벨, 실제 호출 비용·API 실패·cold/warm 측정이 남았다. 사용자는 사용할 macOS 환경이 없다고 답했으므로 macOS는 미검증으로 남긴다.

이슈를 닫거나 댓글을 게시하지 않았다. 코드와 증거를 검토 가능한 브랜치에 준비하며, 기본 브랜치 병합·배포와 설치본 갱신은 이 검증 결과와 구분한다.
