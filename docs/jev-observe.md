# Jev 관찰 실험

`jev_observe.py`는 기존 검색/그래프가 찾은 소수 후보와 고정 SHA의 완료 근거를 평가해 JSON만 기록한다. worker 핸드오버, `review.py check`, 테스트, 승인, 병합에는 연결하지 않는다. 기본 검사는 오프라인이며 외부 호출은 CLI를 명시적으로 실행할 때만 발생한다.

```bash
python3 tests/jev-observe.py             # npm test에도 포함, 외부 호출 없음
python3 plugins/fullops-squad/scripts/jev_observe.py \
  --repo /path/to/active-service-repo --input /path/to/input.json \
  --output /path/to/new-observation.json --env-file /path/to/project/.env
```

CLI는 OpenRouter `https://openrouter.ai/api/v1/systemone`에 `~typesafe/jev-latest`를 요청한다. `OPENROUTER_API_KEY` 환경변수도 지원한다. env 파일은 코드 실행 없이 키만 읽고, 입력 검증이 통과해 호출할 때까지 열지 않는다. [OpenRouter 연동](https://openrouter.ai/docs/guides/community/typesafe-sdk)과 [Jev 튜토리얼](https://openrouter.ai/docs/guides/community/jev-tutorial)을 따른다.

```json
{
  "task": "로그인 오류 수정과 테스트",
  "head": "40자리 Git commit SHA",
  "required_paths": [".fullops-squad/handovers/to_backend.md"],
  "candidates": [
    {"id": "auth", "path": "src/auth.py", "summary": "인증 오류 처리",
     "source": {"sha256": "64자리 파일 SHA-256", "at_head": true,
                "span": {"start_line": 10, "end_line": 24}}}
  ],
  "claims": [
    {"id": "login", "criterion": "로그인 실패가 처리된다",
     "report": "로그인 실패 테스트가 통과했다", "test_command": "python3 -m pytest tests/login_test.py",
     "evidence_ids": ["test-log"]}
  ],
  "evidence": [
    {"id": "test-log", "path": "qa/login-test.txt", "kind": "test_log",
     "sha256": "64자리 파일 SHA-256", "at_head": false,
     "span": {"quote": "command=python3 -m pytest tests/login_test.py"}}
  ]
}
```

`source.span`과 증거의 `span`은 정확한 인용문 또는 1부터 시작하는 양 끝 포함 줄 번호다. 파일 전체 SHA-256을 먼저 검증하고 `at_head: true`면 커밋의 바이트와도 대조한다. 인용은 문자열 그대로 한 번만 존재해야 하며 앞뒤 최대 세 줄을 포함한다. 줄 구간은 최대 40줄·4,000자로 제한한다. 증거에 `span`이 없으면 첫 40줄만 보내고 `partial` 여부를 기록한다. 코드·로그의 공백은 정규화하지 않는다. quote를 못 찾으면 `unverified`와 이유를 남기며 `fabricated`라고 단정하지 않는다.

기존 그래프/검색으로 먼저 후보를 줄여 최대 20개 후보·12개 주장·12개 증거 파일을 입력한다. 공통 규칙 6개와 `required_paths`는 자동으로 후보에 포함한다. 필수 후보는 모델 결과로 제거할 수 없다. 원문 구간을 검증하지 않은 후보도 summary만으로 제외하지 않는다. 관련성과 작업 가정에 반대되는 근거를 독립적으로 묻고, 반대·불확실 후보는 유지한다. 모든 추천 ID는 `candidate_paths`로 원문 위치를 되찾을 수 있으며 추가 그래프 탐색도 계속 가능하다. 환경파일 변형·자격 증명 파일·키 파일·심볼릭 링크·레포 밖 경로는 후보와 증거 모두 거부한다. task·summary·criterion·report·인용 구간에는 명백한 키/비밀 패턴 검사를 적용한다. 이 검사는 임의 형식의 비밀을 완벽하게 탐지하지 못하므로, 입력 작성자가 전송 가능한 자료만 넣어야 한다.

결과는 모델의 `choice`·전체 `probabilities`·`confidence`를 그대로 보존하고, 별도 `decision`과 `status`를 기록한다. 관찰용 제외 추천은 검증된 원문이 있고 `irrelevant`와 `does_not_contradict`의 각 선택 확률이 0.9 이상, confidence가 각각 0.8 이상일 때만 낸다. 이는 정답률이 입증된 임계값이 아닌 보수적 실험 정책이다. 낮은 값은 유지한다. 증거가 없거나 검증되지 않으면 `insufficient_evidence`, 애매하면 `uncertain`, API/형식 실패면 `error`다. `test_log`는 파일 안의 단일 `command=<문자열>`·`exit_code=<정수>`를 코드가 읽고 기록한다. `supports` 상태에는 전체 로그, 종료코드 0, 주장에 지정한 `test_command`와의 일치가 필요하다. 일부 로그나 다른 명령의 성공을 전체 테스트 통과로 처리하지 않는다. 텍스트 로그의 진위와 실제 테스트 실행 여부는 별도 검증이 필요하다.

오프라인 검사는 필수 문맥, 반대 근거, 비밀 차단, 변조·인용 불일치, 부분 로그, 오류 응답을 다룬다. `tests/fixtures/jev-observe-cases.json`에는 이 저장소의 실제 0.3.1 완료 커밋에서 가져온 소수의 안전한 주장·근거와 사람이 붙인 라벨이 있다. 합성 stub 응답과 사례 라벨은 Jev 정확도 측정이 아니다. 실제 과제 비교에서는 자동판단률/보류율, 필수 문맥 누락, 근거 없는 `supports`, 후속 탐색·재작업, 토큰·비용·지연을 같은 SHA와 질문/입력 해시로 기록해야 한다. 현재 이러한 품질·총비용 지표는 미측정이다. 이전 합성 CLI 연결 실측은 `typesafe/jev-1.13-20260917`, 1,615 입력 토큰, 354 출력 토큰, $0.00006783, 0.481초였으며 현재 질문 버전의 품질 근거로 쓰지 않는다.
