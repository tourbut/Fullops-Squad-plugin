# 이슈 자동 작업 운영과 검증

설정과 활성화는 별도이며 기본 OFF이다. 구현 또는 설치 요청으로 실제 저장소의 폴러를 켜지 않는다. `fullops-issues` 스킬이 초기 질문·명시 범위·CLI 순서의 정본이다.

```
사용자 설정 → API 사용자 ID/remote 확인 → configured_OFF
현재 coor 명시 enable → lease + 로컬 수집 폴러
이슈/댓글 수집 (모델 0회) → durable queue
동일 coor foreground wait → claimed → 실제 수신 receipt → running
  → 기존 route/인박스/packet/worker/test/독립 review → draft PR → completed
  → 질문 outbox → awaiting_author → 원 작성자 댓글 → coor 판단
       → sufficient → 새 attempt/digest/packet
       → insufficient/conflicting → 추가 정보 대기
```

`status`는 설정·소유자·큐 상태·최근 event를 반환하고 lease capability/원문 본문을 출력하지 않는다. 호스트 종료는 provider session ID로 추적한다. Orca structured session은 host가 확인한 Orca session ID를 사용하며, Orca TUI terminal agent는 native SessionStart가 기록한 provider session/terminal binding을 사용한다. 최신 binding이 이전 host 세션을 대체하며, 양쪽 모두 같은 Run과 terminal incarnation을 확인한다. 체크포인트는 snapshot과 allowlist를 다시 확인한다. pause는 새 수집/claim 중지, disable/종료/lease 만료는 신규 실행 차단이다. 미커밋 파일·기존 worker·질문·큐를 삭제하지 않는다.

동시 실행은 issue 하나이며 worker 병렬 wave는 기존 방식이다. 보류 이슈와의 독립성을 검토하지 않은 다음 이슈는 claim 후 실행을 보류한다. 이미 dispatch intent가 있는 과제의 답변 재개/재시도는 기존 Run의 task/worker 확정 종료를 `sync`로 확인한 뒤 queued checkpoint를 남긴다. 부재/unverifiable를 종료로 바꾸지 않는다. 새 coor의 `reconcile`도 같은 정본 조회로 인계하고 자동 재배정하지 않는다. draft PR 이후 worker의 integration receipt는 사용자 병합 판단/PR 링크로 hold한다.

보류/취소 상태라도 미종료 dispatch intent가 있으면 다른 이슈의 claim/실행을 막는다. worker는 native SessionStart receipt와 Orca의 dispatch/task/Run/terminal 작업 공간을 연결해 coor와 같은 범위·lease 제한을 적용한다. OFF/보류 시에도 같은 dispatch의 완료·escalation 보고는 허용한다. 작업 브랜치 push는 `git push origin HEAD:refs/heads/fullops/issue-<번호>-a<시도>`처럼 저장된 remote와 전체 대상 ref를 명시한다. 대상 ref를 생략하거나 축약한 push는 remote 기본 push 설정의 영향을 받으므로 허용하지 않는다.

인증은 `GH_TOKEN`/`GITHUB_TOKEN` 또는 `gh auth token`을 메모리에서만 사용한다. HTTPS의 api.github.com과 동일 페이지 endpoint만 조회한다. API 에러는 응답 본문/credential을 기록하지 않는다. 흔한 credential 문자열은 저장된 본문/댓글에서 제거하고 원문 digest로 변경을 추적한다. 질문/receipt에는 비밀정보·불필요한 로그를 넣지 않는다.

credential 문자열이 포함된 API 페이지는 ETag 캐시를 저장하지 않고 다음 주기에 재조회한다. 안전한 페이지의 304/Link 캐시는 유지한다. 종료 확인은 Orca의 `taskId`와 `projection.liveness.verdict=exited`를 사용하며, 관련 task마다 worker 증거가 있어야 한다.

## 호스트 승인과 lease 파일

`enable` 결과 JSON은 현재 coor 작업 공간 안의 Git 제외 파일에 저장한다. 예: `.fullops-squad/.env.issue-mode-lease.json` (`.env*` 제외 규칙 확인, POSIX에서는 현재 사용자 소유의 0600 파일을 미리 준비). 이후 `wait`, `claim`, `checkpoint`, `question`, `answers`, `sync`, `reconcile`, `complete`, `poll`에는 `--token-file <그 JSON 경로>`를 사용한다. CLI가 파일에서 token을 읽고 기존 lease/현재 coor 검증을 수행한다. token 값을 argv·모델 입력·보고서에 복사하거나 인라인 interpreter로 전달할 필요가 없다. 기존 `--token` 입력은 호환을 위해 유지한다.

Claude의 Bash 허용 규칙과 리다이렉트 대상 파일 권한은 별도다. i-Docs Claude 2.1.294에서 정확한 enable 명령을 허용해도 작업 공간 밖 `/tmp` 출력은 자동 심사에 거부됐고, 명령 인자·규칙을 유지한 채 작업 공간 안의 Git 제외 0600 출력 파일로 바꾸자 활성화됐다. [Claude 리다이렉트 권한](https://code.claude.com/docs/en/permissions#redirections)을 확인한다. 호스트가 명령을 거부하면 해당 명령/경로와 사용자 승인 범위를 확인하고 정상 승인 경로로 처리한다. 전역 정책이나 우회 모드를 변경하지 않는다.

## 실행한 검증

- `python3 tests/issue-mode.py`: 격리 Git 저장소, 결정적 GitHub/Orca 대역. 기본 OFF와 범위 선택, 60초 경계, remote/push 권한, stable ID, PR/과거/close 제외, FIFO/동시 claim, 네트워크 실패 cursor 보존, 질문 응답 유실 조정, 같은 계정의 질문 제외, 타인/중복 답변 제외, 충분성 판단과 새 attempt, 댓글 삭제/본문 변경 보류, native session 종료, 새 owner fencing/인계, scope/review 실패, 304 Link/외부 redirect 차단.
- 실제 read-only GitHub: 저장소/계정 stable ID, issue #10의 GraphQL `editor`/`lastEditedAt` 조회 성공. 실제 질문/상태 댓글은 전송하지 않았다.
- 실제 Windows Orca 1.4.222: 현재 대화는 `ORCA_TERMINAL_HANDLE`이 있는 Codex TUI terminal agent이다. 설치된 CLI의 `status-caller.js`는 structured session에서만 caller를 반환하며 terminal agent에는 Orca session ID가 아직 없다고 명시한다. 따라서 TUI는 native provider session/terminal binding으로 검증한다. `terminal show` 기본값은 실제 coor와 다른 pane을 반환했으므로 소유 handle을 명시해 조회하고, 같은 handle로 run-current를 확인한다. 현재 대화는 FullOps setup/native SessionStart receipt가 없어 활성화 blocked이며 새 플러그인으로 시작한 coor 세션이 필요하다. 실환경 질문·답변 검증은 아직 미완료다.
- 실제 Windows native Codex 0.160.1: 별도 QA `CODEX_HOME`에 로컬 빌드 1.1.0을 설치하고 app-server의 `hooks/list`에서 SessionEnd 포함 9개 hook, warnings 0/errors 0을 확인했다. native 종료 이벤트 발생 자체나 실제 coor wake 검증으로 취급하지 않는다. 종료 처리 로직은 위 격리 테스트의 실제 subprocess/stdin 경로로 검증했다.

## 실환경 수용 검증

미병합 PR을 다른 서비스 레포에서 시험할 때는 **PR head의 플러그인 코드**를 사용한다. main의 GitHub 마켓플레이스 설치는 미병합 변경을 포함하지 않는다. 해당 head 체크아웃의 `docs/development.md` 설치 절차를 따르고 기존 실행 세션의 cache를 보존한다. 테스트 서비스 레포에 setup/update를 적용한 뒤 새 coor 세션을 시작하여 native SessionStart receipt를 확인한다. configure의 `owner/repo`와 새 테스트 이슈·답변·draft PR은 그 서비스 레포의 실제 GitHub remote를 기준으로 한다.

연결된 coor에서 사용자가 자동 모드를 명시적으로 켠 전용 테스트 저장소/허용 작성자가 필요하다. 그 환경에서 아래 결과를 기록하기 전에는 #10 완료/wake 성공을 주장하지 않는다.

1. idle 적격 이슈가 같은 coor의 foreground wait로 반환되고 현재 task key/session 수신 receipt와 실제 worker-start receipt가 이어지는지 확인한다.
2. busy 동안 새 이슈/댓글은 큐에만 쌓이고 진행 대화·dirty inbox를 방해하지 않는지 확인한다. 비허용/중복/자기 댓글에서는 모델 호출이 없는지 확인한다.
3. 종료/absent 뒤 수집/dispatch가 멈추고, 새 coor의 명시 enable이 기존 worker/질문을 재조정하는지 확인한다.
4. 실제 질문 outbox→원 작성자 댓글→같은 coor의 충분성 판단→새 attempt/packet→테스트/독립 리뷰→draft PR을 확인한다. 불충분/충돌/편집/삭제/전송 실패도 보류되어야 한다.
5. main 병합/이슈 종료/배포/외부 전송을 하지 않고 호스트 승인 정책/사용량 측정 실패를 보류하는지 확인한다.

공식 API 참고: [Issues](https://docs.github.com/en/rest/issues/issues), [comments](https://docs.github.com/en/rest/issues/comments), [조건부 요청·rate limit](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).
