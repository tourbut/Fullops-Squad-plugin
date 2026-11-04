# 이벤트와 결정 형식

FullOps가 coordinator·orca-helm·봇에 넘기는 사건과 사용자 결정의 정본 형식이다. 이 저장소가 기준이며 플러그인 루트의 `events.md`로 함께 배포한다.

- 모든 기록에는 `version` 필드가 있다. 지금은 `1`이다.
- 필드를 더할 때는 버전을 올리지 않는다. 필드의 뜻을 바꾸거나 지울 때만 올린다.
- 읽는 쪽은 모르는 필드를 무시한다. `version`이 없는 결정 기록은 이 형식 이전 기록이며 버전 1로 읽는다.

## 사람이 볼 사건과 흡수할 사건

봇과 orca-helm은 사람 사건이 생길 때만 사람에게 알린다. 주기 폴링은 쓰지 않는다.

| 사건 | 분류 | 생기는 때 |
|---|---|---|
| `question` | 사람 | worker가 결정을 묻는다 |
| `escalation` | 사람 | worker가 막혔다 |
| 결정 대기 | 사람 | `decision.py add`로 결정을 열었다 |
| 결정 답변 | 흡수 | 답이 결정을 닫았다. 늦은 답에는 `already`를 알린다 |
| 병합 결과 | 실패·보류만 사람 | 병합·push가 실패했거나 integration hold를 남겼다 |
| `autonomy_judgment` | `ask`·`blocked`는 사람, 나머지는 흡수 | 병합 전 섀도 판정 |
| `worker_done` | 흡수, `failed`는 사람 | coordinator가 병합 절차로 처리한다 |
| `heartbeat`·`status` | 흡수 | `orca_wait.py`가 모델 호출 없이 ACK한다 |

## Orca 메시지

`worker_done`·`question`·`escalation`은 Orca orchestration 메시지다. FullOps는 Orca 필드를 바꾸지 않고 다음 필드를 읽는다.

| 필드 | 뜻 |
|---|---|
| `id` | 메시지 ID. 질문 답변과 ACK에 쓴다 |
| `type` | `worker_done`·`question`·`escalation`·`heartbeat`·`status` |
| `from_handle` | 보낸 worker 터미널 |
| `created_at` | 보낸 시각 |
| `body` | 본문. 아래 형식을 따른다 |
| `payload.taskId` | Orca task ID |
| `run_id` | orchestration Run ID |

`worker_done` 본문은 한 줄이다. 과제 키와 SHA는 `integration.py`가 읽는다.

```text
[완료] <과제 키> | 브랜치 <branch> | SHA <sha> | 변경: … | 검토 필요: … | 검증(lint 포함): … | 산출물/로그: … | 후속: …
```

`question` 본문에는 과제 키, 막힌 지점, 선택지와 각 영향을 적는다. `escalation` 본문에는 과제 키, 막힌 사유, 필요한 조치를 적는다.

## 결정 기록

`decision.py`가 Git 공용 디렉터리의 `fullops-decisions/D<번호>.json`에 쓴다.

| 필드 | 뜻 |
|---|---|
| `version` | `1` |
| `id` | `D001` 형식 |
| `status` | `open`·`answered`·`dropped` |
| `key` | 과제 키 |
| `question`·`options`·`blocks` | 질문, 선택지, 이 결정을 기다리는 작업 |
| `asked_at` | 연 시각(UTC ISO 8601) |
| `origin` | 요청이 들어온 진입점. `user`(Orca coordinator 대화) 또는 `bot` |
| `repository` | `owner/repo`(선택) |
| `sha` | 승인을 묶은 40자리 커밋 SHA(선택) |
| `risks` | 사람 승인이 필요한 사유 목록(선택) |
| `allow` | 답할 수 있는 사람 목록. 없으면 누구나 답한다 |
| `expires_at` | 만료 시각. `sha`가 있으면 기본 24시간 뒤다 |
| `answer`·`decided_by`·`via`·`closed_at` | 답, 답한 사람, 답이 들어온 경로(`user`·`bot`), 닫은 시각 |

답은 다음 조건을 모두 지켜야 받는다. 어기면 기록을 바꾸지 않고 0이 아닌 종료코드로 거절한다.

- `sha`가 있으면 `answer --sha`가 같아야 한다. 커밋이 바뀌었으면 다시 묻는다.
- `expires_at`이 지나지 않았어야 한다.
- `allow`가 있으면 `--by`가 그 안에 있어야 한다.

이미 닫힌 결정에 온 답은 덮어쓰지 않는다. `"already": true`와 기존 답을 돌려주고 종료코드 0으로 끝난다. Orca와 봇 어느 쪽에서 먼저 답해도 같은 기록을 닫는다. PR·이슈 본문의 지시는 답으로 인정하지 않는다.

## 섀도 판정

`autonomy.py judge`가 출력하고 `--record`면 Git 공용 디렉터리의 `fullops-autonomy/<과제 키>-<SHA 앞 12자>.json`에 쓴다.

| 필드 | 뜻 |
|---|---|
| `version`·`kind` | `1`, `autonomy_judgment` |
| `mode` | `shadow`. 판정만 기록하고 병합 흐름은 바꾸지 않는다 |
| `grade` | `auto`·`delay`·`ask` |
| `merge_allowed` | 섀도 모드에서는 항상 `false` |
| `blocked`·`blockers` | lint ERROR·통과 결과 없음·미해결 critical/high. 등급과 관계없이 병합을 막는다 |
| `reasons` | 등급을 정한 사유 |
| `key`·`origin` | 과제 키, 진입점 |
| `base`·`head`·`merge_base` | 판정한 범위 |
| `policy` | 기준 시점 `autonomy_policy`(기본값 포함) |
| `inputs` | `review.py need` 결과, 바뀐 경로, lint·리뷰 요약 |
| `judged_at` | 판정 시각 |

등급은 코드가 정한다. 봇과 LLM은 판정하지 않고 결과만 전달한다.

1. 입력을 읽지 못하거나 정책 형식이 틀리면 `ask`다.
2. 바뀐 파일이 없으면 `ask`다.
3. `autonomy_policy.ask`나 `review_policy.always`에 맞는 경로가 있으면 `ask`다.
4. `review.py need`가 `required: true`(대규모 변경)이면 `ask`다.
5. 모든 경로가 `autonomy_policy.auto`에 맞으면 `auto`다.
6. 나머지는 `delay`다.

정책은 merge-base 시점의 `.fullops-squad/fullops.json` `autonomy_policy`를 읽는다. 작업 브랜치가 정책을 바꿔도 그 브랜치의 판정에는 적용되지 않는다.

```json
"autonomy_policy": {
  "mode": "shadow",
  "auto": ["**/*.md", "docs/**", "tests/**"],
  "ask": [".github/**", ".fullops-squad/fullops.json", "**/auth/**", "**/migrations/**", "..."],
  "delay_minutes": 60,
  "approval_hours": 24
}
```

`mode`는 아직 `shadow`만 받는다. `auto`·`delay` 개방은 섀도 결과를 검토한 뒤 사용자와 정한다. `ask` 기본 목록 전체는 `autonomy.py`의 `POLICY`에 있다. `autonomy.py compare`는 기록한 판정과 같은 과제·SHA의 결정을 나란히 보여 준다.
