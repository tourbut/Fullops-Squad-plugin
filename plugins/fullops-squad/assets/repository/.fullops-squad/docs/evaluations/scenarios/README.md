# 테스트 시나리오

다시 실행할 수 있는 조작 테스트 시나리오의 정본이다. 과제가 끝나도 남아 회귀 테스트 묶음이 된다. 실행 결과는 `../qa-reports/<과제 키>-test/`에 남고, 결과의 `result.json`에 실행한 시나리오 경로가 기록된다.

- `web/<기능>.json`: `jev_test_web.py` 시나리오.
- `unity/<기능>.json`: `jev_test_unity.py` 시나리오. 게임별 브리지 설정은 `../../../test/unity-play.json`이다.

파일 이름은 검증하는 기능으로 짓는다(예: `web/todo-add-complete.json`). 지시서에는 실행하거나 새로 만들 시나리오 경로만 적는다. 실행 전에 `--validate`로 점검한다. 점검은 필수 칸, checks 모양, 비밀값을 확인하며 통과해야 실행된다.

## 형식

| 칸 | 웹 | Unity | 설명 |
|---|---|---|---|
| `goal` | 필수 | 필수 | Jev에게 주는 목표. 영어로 쓴다 |
| `covers` | 필수 | 필수 | 이 시나리오가 검증하는 요구사항 ID나 지시서 통과 조건 |
| `checks` | 필수 | 필수 | 통과 판정. 하나 이상 |
| `url` | 필수 | | 시작 주소 |
| `values` | 선택 | | `{키: 입력할 글자}`. Jev는 여기서만 입력값을 고른다 |
| `setup_js` | 선택 | | 시작 전에 실행할 식(하나 또는 목록). 저장 데이터 초기화 등 |
| `player_args` | | 선택 | 플레이어에 넘길 인자. 테스트 씬·세이브 폴더 지정 등 |
| `max_steps` | 선택 | 선택 | 최대 결정 횟수 |

checks 종류:
- 웹: `{"text": "보일 글자"}`, `{"url": "주소 일부"}`, `{"js": "<식>", "equals": <값>}`
- Unity: `{"field": "<설정의 필드 이름>", "op": "<=", "value": 0}`, `{"text": "화면 문구"}`, `{"actor": "<그룹>", "absent": true}`

## 잘 쓰는 법

**하나의 흐름만.** 한 시나리오는 사용자 흐름 하나를 검증한다. 추가와 삭제를 함께 확인하고 싶으면 파일을 나눈다. 실패했을 때 어느 흐름이 깨졌는지 바로 드러난다.

**covers는 지시서의 통과 조건을 그대로.** 지시서 `완료 기준과 검증`의 항목이나 요구사항 ID(D02)를 옮겨 적는다. 지시서의 모든 통과 조건은 적어도 한 시나리오의 checks로 덮여야 한다. 덮을 수 없는 조건(시각 품질 등)은 완료 보고에 "시나리오 밖"으로 적는다.

**goal은 상태에 보이는 말로.** Jev는 화면을 보지 못하고 요소 목록(웹)이나 배우·필드 목록(Unity)만 본다. 버튼 문구, 입력칸 이름, 배우 이름과 그룹을 상태에 나오는 그대로 쓴다. 순서가 있으면 순서대로 쓰고, 끝난 상태가 무엇인지 적는다. 방해 요소나 범위 밖 행동은 "하지 말 것"으로 적는다.
- 나쁜 예: `할 일 기능 테스트`
- 좋은 예: `Add two todos: '우유 사기' and '보고서 제출'. Then mark only '우유 사기' as completed. Do not delete anything.`

**checks는 goal과 따로 요구사항을 확인한다.** Jev의 done은 판정이 아니다. 끝난 뒤 실제 상태를 코드로 읽어 판정한다.
- 글자가 보이는지만 보지 말고 구조를 확인한다. 예: 목록 항목과 완료 여부를 한 줄로 만들어 `equals`로 비교한다.
- 일어나지 않아야 할 일도 확인한다. 예: 다른 항목이 완료되지 않았는지, 적이 아닌 NPC가 그대로인지.
- 값 비교는 필드나 식으로 한다. 화면 문구는 바뀌기 쉬우니 보조로 쓴다.

**출발 상태를 고정한다.** 재실행해도 같은 결과가 나와야 한다. 웹은 `setup_js`로 저장 데이터를 비우고 다시 불러온다(예: `"localStorage.clear(); location.reload()"`). Unity는 `player_args`로 테스트 씬과 세이브 폴더를 지정한다.

**입력값은 values에.** 입력할 글자는 모두 `values`에 적는다. 비밀번호·토큰은 넣지 않는다(점검에서 거절된다). 로그인이 필요하면 테스트 전용 계정과 별도 절차를 쓴다.

**실패 흐름도 쓴다.** 잘못된 입력, 경계값, 거절·취소 흐름을 별도 시나리오로 둔다. 기능 추가 과제라면 정상 흐름 하나와 실패 흐름 하나 이상을 권한다.

**max_steps는 여유 있게.** 사람이 하는 단계 수의 1.5~2배로 잡는다. 너무 크면 헤매는 실행이 비용을 쓴다.

**실패하면 원인을 나눈다.** `events.jsonl`에서 Jev의 선택과 확률, `lastOutcome`을 읽는다.
- Jev가 헤맸다(확률이 낮고 같은 행동을 반복): goal을 보강하거나, Unity라면 브리지 설정의 이름과 설명을 고친다.
- 기능이 실제로 동작하지 않았다: 시나리오를 고치지 말고 재현 절차로 보고한다.
- checks가 틀렸다: 식을 고치고, 고친 이유를 완료 보고에 적는다.

## 예시

```json
{
  "goal": "On this TodoMVC page, add two todos: '우유 사기' and '보고서 제출'. Then mark only '우유 사기' as completed. Do not delete anything.",
  "covers": ["TODO-1 할 일을 추가할 수 있다", "TODO-2 할 일을 완료로 표시할 수 있다"],
  "url": "https://demo.playwright.dev/todomvc/",
  "setup_js": "localStorage.clear(); location.reload()",
  "values": {"milk": "우유 사기", "report": "보고서 제출"},
  "checks": [
    {"js": "[...document.querySelectorAll('.todo-list li')].map(li => li.innerText.trim() + (li.classList.contains('completed') ? ':done' : ':open')).join('|')", "equals": "우유 사기:done|보고서 제출:open"}
  ],
  "max_steps": 10
}
```

```json
{
  "goal": "Defeat the enemy (group enemy). Walk to it, then attack until it is gone. Do not approach the npc.",
  "covers": ["M3-COMBAT-1 근접 공격으로 적을 처치한다"],
  "player_args": ["--test-scene", "combat-basic"],
  "checks": [
    {"actor": "enemy", "absent": true},
    {"field": "enemy_hp", "op": "<=", "value": 0},
    {"actor": "npc", "absent": false}
  ],
  "max_steps": 12
}
```
