# Jev 관찰 실험

`jev_observe.py`는 기존 그래프/검색 후보와 완료 보고·증거를 같은 과제와 고정 SHA에서 평가한다. 결과 JSON만 쓰며 worker 전달, `review.py check`, 테스트, 권한, 병합을 바꾸지 않는다. 이 단계의 추천은 검토용이다.

```bash
python3 plugins/fullops-squad/scripts/jev_observe.py \
  --repo /path/to/service-repo --input /path/to/input.json \
  --output /path/to/jev-observation.json --env-file /path/to/project/.env
python3 tests/jev-observe.py
```

`OPENROUTER_API_KEY` 환경변수도 사용할 수 있다. env 파일은 실행하지 않고 해당 키만 읽는다. 키 파일은 커밋하지 않는다. OpenRouter `https://openrouter.ai/api/v1/systemone`과 요청 모델 `~typesafe/jev-latest`를 사용한다. [OpenRouter SDK 안내](https://openrouter.ai/docs/guides/community/typesafe-sdk), [Jev 튜토리얼](https://openrouter.ai/docs/guides/community/jev-tutorial).

입력 JSON 예시:

```json
{
  "task": "로그인 오류 수정과 테스트",
  "head": "40자리 Git commit SHA",
  "required_paths": [".fullops-squad/handovers/to_backend.md"],
  "candidates": [
    {"id": "auth", "path": "src/auth.py", "summary": "인증 오류 처리"},
    {"id": "spec", "path": "docs/login.md", "required": true, "summary": "완료 기준"}
  ],
  "claims": [
    {"id": "login", "criterion": "로그인 실패가 처리된다", "report": "수정하고 테스트했다", "evidence_ids": ["test-log"]}
  ],
  "evidence": [
    {"id": "test-log", "path": "qa/login-test.txt", "sha256": "64자리 파일 SHA-256", "at_head": false}
  ]
}
```

후보는 기존 검색/그래프로 먼저 좁히고, `summary`에 관련 코드나 문서의 짧은 원문 구절을 넣는다. 경로는 레포 안의 실제 파일이어야 한다. 공통 규칙 6개는 자동 포함되며 명시한 정본·완료 기준은 `required_paths` 또는 `required: true`로 지정한다. 누락·유효하지 않은 경로, API 오류, 잘못된 응답은 전체 후보를 유지한다. 결과의 `candidate_paths`와 ID로 원문을 다시 열고 추가 탐색할 수 있다. 낮은 확신은 후보를 유지하며, 0.8 이상으로 `irrelevant`인 선택지만 관찰용 추천에서 제외한다. 이 임계값은 합성 검사용이며 실제 과제에서 보정하지 않았다.

증거 파일은 존재와 SHA-256을 검사한다. `at_head: true`는 그 파일의 바이트가 지정한 Git 커밋과도 같아야 한다. 테스트 출력 등 커밋 밖 파일은 `false`로 두고 해시로 고정한다. 연결된 증거가 없거나 달라졌으면 `insufficient_evidence`로 기록한다. Jev는 `supports`·`contradicts`·`insufficient`만 판단한다. 실제 테스트 성공과 리뷰 수락은 별도 확인한다. JSON에는 기준선/추천 ID, 후보와 증거 검사 상태, 질문·입력 해시, 고정 SHA, 요청·응답 모델, 토큰·비용·지연을 남긴다. 전체 대화나 원문 파일을 바꾸지 않는다.

현재 검사는 합성 fixture다. CLI 연결 실측 한 건은 2026-09-23 기준 실모델 `typesafe/jev-1.13-20260917`, 1,615 입력 토큰, 354 출력 토큰, $0.00006783, 0.481초였다. 정답률·전체 비용 절감은 측정하지 않았다. 실제 비교에는 같은 완료 과제의 baseline 후보, 추천 후보, 검토자가 확인한 필수 문맥 누락·증거 판정, 후속 탐색·재작업, 기존 리뷰 결과를 함께 기록해야 한다.
