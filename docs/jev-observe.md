# Jev 관찰 실험

`jev_observe.py`는 기존 검색/그래프가 찾은 소수 후보와 고정 SHA의 완료 근거를 평가해 JSON만 기록한다. `review.py check`, 테스트, 승인, 병합에는 연결하지 않는다. 핸드오버에는 아래 dispatch 문맥 분류의 추천으로만 쓰인다. 기본 검사는 오프라인이며 외부 호출은 CLI를 명시적으로 실행할 때만 발생한다.

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

`source.span`과 증거의 `span`은 정확한 인용문 또는 1부터 시작하는 양 끝 포함 줄 번호다. 파일 전체 SHA-256을 먼저 검증하고 `at_head: true`면 커밋의 바이트와도 대조한다. 인용과 줄 구간 모두 선택 범위 앞뒤 최대 세 줄을 포함하되 실제 전송 범위는 최대 40줄·4,000자다. 결과의 `selected_start_line`·`selected_end_line`은 원래 선택 범위, `start_line`·`end_line`은 전송 범위다. 선택 범위 자체가 상한을 넘으면 거부하고, 주변 문맥만 상한에 맞게 줄인다. 증거에 `span`이 없으면 첫 40줄을 선택한다. 로그의 `coverage`는 주변 문맥이 아니라 선택 범위로 판단한다. 코드·로그의 바이트와 공백은 정규화하지 않는다. quote를 못 찾으면 `unverified`와 이유를 남기며 `fabricated`라고 단정하지 않는다.

기존 그래프/검색으로 먼저 후보를 줄여 최대 20개 후보·12개 주장·12개 증거 파일을 입력한다. 공통 규칙 6개와 `required_paths`는 자동으로 후보에 포함한다. 필수 후보는 모델 결과로 제거할 수 없다. 원문 구간을 검증하지 않은 후보도 summary만으로 제외하지 않는다. 관련성과 작업 가정에 반대되는 근거를 독립적으로 묻고, 반대·불확실 후보는 유지한다. 모든 추천 ID는 `candidate_paths`로 원문 위치를 되찾을 수 있으며 추가 그래프 탐색도 계속 가능하다. 환경파일 변형·자격 증명 파일·키 파일·심볼릭 링크·레포 밖 경로는 후보와 증거 모두 거부한다. task·summary·criterion·report·인용 구간에는 명백한 키/비밀 패턴 검사를 적용한다. 이 검사는 임의 형식의 비밀을 완벽하게 탐지하지 못하므로, 입력 작성자가 전송 가능한 자료만 넣어야 한다.

결과는 모델의 `choice`·전체 `probabilities`·`confidence`를 `judgment`에 그대로 보존하고, 별도 `decision`과 `status`를 기록한다. 관찰용 제외 추천은 검증된 원문이 있고 `irrelevant`와 `does_not_contradict`의 각 선택 확률이 0.9 이상, confidence가 각각 0.8 이상일 때만 낸다. 이는 정답률이 입증된 임계값이 아닌 보수적 실험 정책이다. 낮은 값은 유지한다. 검증되지 않은 증거나 결정적 증거 결함은 `insufficient_evidence`와 `reason`, 모델 확신 부족은 `uncertain`, API/형식 실패는 `error`다. 일치하는 명령의 완전한 로그가 0이 아닌 종료코드를 기록하면 `contradicts`와 `test_command_failed`를 남긴다. 모델의 원판단이 `supports`여도 이 정책 판정은 유지된다.

실행 완료 주장은 입력 `claims[].test_command`에 정확한 명령을 구조화해 적어야 한다. 이 필드가 있으면 같은 `evidence_ids` 안에 `kind: "test_log"`인 검증된 로그가 적어도 하나 필요하다. 파일 증거를 함께 연결해도 된다. `test_log`는 파일 안의 단일 `command=<문자열>`·`exit_code=<정수>`를 코드가 읽고 기록한다. `supports`에는 선택 범위가 전체 로그이고 명령이 `test_command`와 일치하며 종료코드가 0인 로그가 필요하다. 로그의 `kind`를 생략하면 기본값 `file`로 처리한다. 자유 텍스트의 모든 실행 주장을 자동으로 찾아내지는 않으므로 입력 작성자가 실행 주장을 이 계약에 맞게 구조화해야 한다. 텍스트 로그의 진위와 실제 테스트 실행 여부는 별도 검증이 필요하다.

## dispatch 문맥 분류

`jev_context.py`는 지시서를 쓸 때 후보 문서의 입력을 자동으로 만든다. 인박스 지시서 본문을 task로, 후보 경로마다 SHA-256·HEAD 일치 여부·첫 34줄(최대 3,500자) 구간을 source로 넣는다. 공통 필수 문서와 인박스는 항상 유지된다. `observe()`는 후보 하나의 원문이 민감 패턴이나 크기로 거부되면 호출 전체를 건너뛰므로, 그런 파일과 64KB 초과·비 UTF-8 파일은 source 없이 넣어 keep으로 남긴다(`unsent_sources`). 민감 경로는 후보에서 빼고 `refused_paths`에 기록한다. 지시서 본문에 민감 문자열이 있거나 키가 없거나 API가 실패하면 전부 keep이다. 결과는 `.fullops-squad/docs/evaluations/jev/<과제 키>-context.json`에 남고 덮어쓰지 않는다. worker 완료 보고의 "제외 추천 문서가 필요했는지" 기록이 이 분류의 사람 라벨이 된다. 이 라벨이 쌓이기 전에는 제외 추천을 게이트로 쓰지 않는다.

평가 사례는 `tests/fixtures/jev-observe-0.3.1.md`에 원문을 보존한다. 출처는 커밋 `2be2a31b0d4dad6794ef374d701dc7357d8214b9`의 `docs/releases/0.3.1.md`이며, 사례 JSON에 원문 SHA-256을 기록했다. 기본 검사는 이 자체 완결 fixture만 읽으므로 Git 과거 객체가 필요 없다.

오프라인 검사는 필수 문맥, 반대 근거, 비밀 차단, 변조·인용 불일치, 부분 로그, 오류 응답을 다룬다. `tests/fixtures/jev-observe-cases.json`에는 이 저장소의 실제 0.3.1 완료 커밋에서 가져온 소수의 안전한 주장·근거와 사람이 붙인 라벨이 있다. 합성 stub 응답과 사례 라벨은 Jev 정확도 측정이 아니다. 실제 과제 비교에서는 자동판단률/보류율, 필수 문맥 누락, 근거 없는 `supports`, 후속 탐색·재작업, 토큰·비용·지연을 같은 SHA와 질문/입력 해시로 기록해야 한다. 현재 이러한 품질·총비용 지표는 미측정이다. 이전 합성 CLI 연결 실측은 `typesafe/jev-1.13-20260917`, 1,615 입력 토큰, 354 출력 토큰, $0.00006783, 0.481초였으며 현재 질문 버전의 품질 근거로 쓰지 않는다.
