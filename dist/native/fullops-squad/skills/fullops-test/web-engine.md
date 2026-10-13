# 웹 실행기 계약

기본 실행기는 Orca 내장 브라우저다. `--engine playwright`를 지정하면 선택 설치된 Playwright 런타임을 쓴다. 설치·브라우저 다운로드·다른 엔진으로의 자동 전환은 실행기가 수행하지 않는다. Windows와 macOS에서 같은 Python/Node 경로를 사용한다. 기존 프로젝트 E2E·보안·lint·done/review 게이트는 계속 실행한다.

## 실행

이 문서 기준 `../../scripts/jev_test_web.py`를 사용한다. 예시의 `<script>`는 그 절대 경로다.

```text
python3 <script> --repo <repo> --key W21 --scenario <scenario.json> --validate
python3 <script> --repo <repo> --key W21 --scenario <scenario.json>
python3 <script> --repo <repo> --key W21 --scenario <scenario.json> --page <Orca-page-id> --assert-only
python3 <script> --repo <repo> --key W21 --scenario <scenario.json> --engine playwright --replay <regression.json>
```

Orca는 기본 새 탭을 연다. 사용자가 기존 화면을 지정하면 `--page`로 그 ID에 연결한다. 시나리오 URL이 실제 URL과 정확히 같아야 하며 연결 시 이동하지 않는다. 탭은 결과 확인을 위해 남긴다. 작업 후 원래 스크롤·포커스 등 필요한 상태를 복구한다. Playwright는 별도 비영구 context를 만들고 종료 시 자신이 만든 프로세스만 정리한다.

Playwright 선택 준비는 `fullops-frontend/toolchain.md`를 따른다. 기본 package 경로는 `<repo>/.fullops-squad/tools/frontend/playwright/node_modules/@playwright/cli/package.json`이다. 기존 로컬 설치는 `--playwright-package <package.json>`로 재사용한다. 선택한 CLI와 연결된 Playwright의 패키지 정체성·실제 버전·실행 가능 여부를 확인한다. 고정 버전 일치는 요구하지 않는다. `--browser-executable <path>`로 설치된 Chromium 계열 브라우저를 재사용할 수 있고 `--headed`는 창을 표시한다. 브라우저가 없으면 명시적으로 준비한다. 실행 증거에는 실제 CLI·Playwright·브라우저 버전을 남긴다.

`--assert-only`는 모델·조작·setup 없이 독립 checks만 실행한다. `--replay`는 고정 경로를 모델 없이 재생한다. 두 모드에는 Jev 키가 필요 없다. 일반 Jev 조작에는 기존 `OPENROUTER_API_KEY`가 필요하다. 새 탐색은 `exploration: true` 또는 `--explore`로만 켠다. shadow 분석과 CUAWright도 기본 OFF다.

## 시나리오와 권한

기본 `url`, `goal`, `covers`, `values`, `checks`, `setup_js`, `max_steps` 형식은 repository의 `docs/evaluations/scenarios/README.md`를 따른다. 조작과 setup을 허용하려면 소유한 격리 fixture/tenant를 먼저 준비하고 아래 권한을 명시한다. 기존 조작 시나리오도 이 정보를 보완해야 한다. fixture 이름은 실제 격리를 대신하지 않는다.

```json
{
  "safety": {
    "fixture": "isolated-todo",
    "allowed_origins": ["http://127.0.0.1:3000"],
    "allowed_operations": ["fill_submit", "check"],
    "requests": [{"method": "POST", "path": "/api/test/todos"}]
  },
  "max_steps": 20,
  "max_seconds": 120,
  "max_cost": 0.05,
  "max_visits": 4,
  "candidate_limit": 80,
  "max_input_chars": 32000,
  "exploration": false
}
```

origin 기본값은 시작 URL의 origin 하나다. 포트까지 정확히 지정한다. 동작 기본값은 빈 목록이다. Jev의 위험 점수와 관계없이 권한을 검사한다. disabled·비밀 입력칸·관측되지 않은 대상·가려진 대상은 조작하지 않는다. 요청 규칙은 정확한 method/path이며 와일드카드는 허용하지 않는다. 실계정 로그인·결제·삭제·발송은 이 경로에 넣지 않는다.

Playwright는 허용 origin의 문서·정적 자원 GET/HEAD와 명시한 요청만 통과시킨다. service worker·WebSocket·popup·download는 허용하지 않는다. 차단된 요청이 있으면 checks가 참이어도 PASS로 처리하지 않는다. GET 자체가 효과를 내는 앱과 서버의 후속 효과까지 격리하는 장치는 아니다. 테스트 tenant와 서버 측 권한을 함께 제한한다.

Orca CLI에는 이 adapter의 요청 차단 기능이 없다. 원격 사이트의 효과가 있는 동작은 차단한다. 읽기·스크롤·assertions는 가능하며, 조작 회귀는 외부 효과가 없는 loopback fixture에서만 수행한다. 원격 격리 tenant를 조작하려면 요청 제한이 있는 Playwright를 명시적으로 선택한다. 엔진이 바뀌면 새 context의 인증·fixture 조건을 따로 확인한다.

`setup_js`와 checks의 `js`는 시나리오 작성자가 검토한 신뢰 코드다. 페이지 문구·모델 답으로 생성하거나 외부 페이지에서 복사해 자동 실행하지 않는다. JS 평가기는 보안 sandbox가 아니다. 비밀값·개인정보를 읽는 식을 쓰지 않는다. 모델에는 URL query/fragment·원시 DOM·현재 입력 필드 값·HTML을 보내지 않는다. 시나리오 fixture 값은 선택지 설명으로 제공하되 이메일·전화번호·비밀 패턴을 마스킹하고 실제 입력은 로컬의 원래 값 ID에서 가져온다. 요소 이름·인접 문구·증거도 제한·마스킹한다. 마스킹은 보조 수단이므로 민감한 실제 데이터가 있는 화면을 모델 탐색 대상으로 삼지 않는다.

## 관측과 판정

전체 로컬 후보와 이번 모델 후보를 구분한다. choice 한 묶음은 최대 254개 후보와 `_NONE_`/`_STOP_` 하나다. 상태별 `state_id`, `candidate_id`, 전체·관측·남은 후보·지원하지 않는 영역을 기록한다. 탐색을 켜면 `observe_more`로 다음 후보 묶음을 읽을 수 있다. iframe·shadow root·canvas·select/custom widget은 완전한 탐색 범위로 주장하지 않는다. 보조 DOM 검사는 secure context(HTTPS 또는 loopback)가 필요하다.

조작 직전에 URL·DOM/입력 상태 digest·현재 참조·가시성·가림·비활성·목적지를 다시 확인한다. 화면이 바뀌면 재관측하고, 검증이 안 되는 대상은 멈춘다. 동일 HTML로 노드를 교체해도 mutation revision이 달라진다. Playwright는 node handle도 고정한다. 이는 임의의 악성 페이지나 모든 조작 중 경쟁 조건을 막는 보안 경계는 아니다. 자주 갱신되는 화면은 보수적으로 중단될 수 있다.

타깃 존재 Noul과 choice 확신이 낮으면 보류한다. 초기 임계값은 프로젝트 사례로 보정해야 한다. 입력은 시나리오 값 ID에서만 고른다. 폼 Enter는 한 제출 경로만 실행한다. 시간·비용·동일 상태 방문·스텝 제한을 적용하고 API 실패의 비용은 `unknown`으로 보존한다. `max_cost`는 확인한 응답 비용 기준의 중단선이며 이미 시작한 한 요청의 과금을 미리 상한 보장하지 않는다.

DONE은 독립 checks 실행 요청이다. PASS는 해당 scope의 checks가 모두 통과하고 완료 조건을 충족한 경우뿐이다. 예산 소진·보류·반복·지원하지 않는 탐색 영역은 전체 PASS가 아니다. `assertions_passed`와 실행 결과를 따로 읽는다. 검사된 화면과 조건을 넘어 사이트 전체의 정상 동작이나 시각 품질을 주장하지 않는다. Jev는 이미지 시각 판정을 맡지 않는다.

## 선택 분석과 고정 회귀

`../../scripts/web_analysis.py --record <run-dir> --shadow`는 별도 `shadow.json`에 참고 분류를 쓴다. 기존 result·게이트·검사 범위를 변경하지 않는다. 환경/탐색/미확정 분류는 가설이며 `human_label`과 수정 이유를 별도로 검토한다. 실제 제품 결함을 자동 확정하거나 실패 검사를 건너뛰지 않는다.

`web_analysis.py --record <run-dir> --promote --scenario <original.json>`는 통과한 조작 기록을 `regression.json`으로 승격한다. role/name/near와 fixture 값 ID, 후보 묶음을 넘기는 `observe_more` 순서를 남기고 원래 scenario SHA에 결합한다. 탐색 관측은 원래 시나리오에서 exploration을 명시한 경우에만 재생한다. 이 JSON은 `jev_test_web.py --replay`에서 Orca 또는 Playwright로 재생하며 모델 호출이 없다. 대상이 없거나 둘 이상이면 중단한다. 수정한 시나리오·마스킹된 대상은 사람이 다시 검토한다. 프로젝트의 독립 Playwright E2E 코드로 옮길 수도 있다. 모델 회귀를 필수 의존성으로 만들지 않는다.

## CUAWright PoC — 기본 OFF

CUAWright는 별도 Python Playwright/호스트 스킬 실험이며 Orca/Playwright 기본 실행기를 교체하지 않는다. 최신 선택 스킬은 dependencies.json의 `optional_skills`에만 있다. 기본 설치·deps check에 포함되지 않는다.

`../../scripts/web_poc.py --repo <repo> --key W21 --scenario <isolated.json> --host <codex|claude-code|grok> --model <model> --effort <effort>`는 기본 준비 계획만 출력한다. `--install-skill`만 선택 호스트에 최신 스킬을 설치하며 Python/브라우저/모델 키는 설치하지 않는다. `--prepare`는 준비 상태를 검사하고 별도 `cuawright-poc-*/` 지시서와 메타데이터를 만든다. Python Playwright와 Firefox가 없으면 BLOCKED다. `--python`으로 선택 환경을 지정한다.

준비 완료도 UNVERIFIED다. 이 스크립트는 모델 생성·코드 실행을 자동화하지 않는다. 생성/수정/재실행은 선택 호스트의 스킬 세션에서 시간·토큰 제한을 확인한 뒤 진행한다. 생성 코드는 실행 전 독립 SHA 리뷰를 받고 격리 tenant/네트워크 환경에서만 실행한다. 고정 checks와 별도 시각 검수 경로, 캡처·로그·미실행을 기록한 뒤 사람이 PASS/FAIL/BLOCKED/UNVERIFIED를 판정한다. Jev 이미지 판정·새 유료 키·desktop/VM 실행을 필수로 추가하지 않는다.

## 검증 증거

기존 `result.json`, `events.jsonl`, `report.md`에 scope·실행기 버전·실행 파일 SHA·시나리오 SHA·상태/후보 ID·관측 범위·예산·assertions·비용을 추가한다. 같은 폴더를 덮어쓰지 않는다. 탐색/비용 절감 수치는 같은 fixture·검사·예산·실행기 버전의 반복 측정과 사람이 라벨한 정상/결함 사례가 있어야 주장한다. 모델 없는 재생의 비용 0을 모델 탐색의 성능 개선으로 해석하지 않는다.

플러그인 개발 검사는 `python3 tests/web-engine.py`(모델/브라우저 불필요)와 `python3 tests/web-browser.py --engine playwright --playwright-package <package.json>`(격리 로컬 실제 브라우저)다. 로컬 Orca가 연결돼 있으면 `--engine both`로 동일 정상/삽입 결함 fixture를 비교한다. 실제 OS에서 실행한 결과와 CI 설정만 추가한 OS를 구분해 기록한다.
