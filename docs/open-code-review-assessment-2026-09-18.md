# Open Code Review delegate 적용 검토

검토일: 2026-09-18. 결론은 **delegate 방식의 조건부 도입 권장**이다. 파일 선정·규칙 해석을 CLI에 맡기고 판단은 FullOps가 배정한 AI에 맡기는 구조가 모델 분업과 맞는다. 이번 작업은 검토이며 설치기·스킬·병합 동작은 변경하지 않았다.

## 확인한 동작

delegate는 OCR 측에서 LLM을 호출하지 않는다. `preview`로 파일과 비교 기준을 얻고 `rule`로 파일별 규칙을 묶어 받은 뒤, 호스트 AI가 Git diff와 필요한 문맥을 읽어 리뷰한다. 별도 OCR API 키나 provider 설정은 필요 없지만 호스트 모델의 토큰·구독 사용량은 발생한다. [공식 delegate 문서 원본](https://github.com/alibaba/open-code-review/blob/main/pages/src/content/docs/en/integrations/delegate.md).

공식 스킬은 `(path, status)` 단위로 모든 리뷰 대상의 reviewed/skipped 상태를 관리하고, skipped 사유와 커버리지를 보고하도록 안내한다. 이 과정은 스킬 지침이며 CLI가 리뷰 완료나 병합 허용을 검증해 주는 것은 아니다. JSON 출력은 1.9.0 이상이 필요하다. [공식 delegate 스킬](https://github.com/alibaba/open-code-review/blob/main/skills/open-code-review-delegate/SKILL.md).

README의 약 1/9 토큰 벤치마크는 delegate 자체의 비교 결과로 제시되지 않는다. 파일 필터링과 규칙 공유가 중복 입력을 줄일 가능성은 있지만 FullOps의 실제 토큰 절감률은 측정해야 한다. delegate는 파일별 diff 크기 상한을 적용하지 않아 큰 변경의 분할도 호스트 책임이다. [README](https://github.com/alibaba/open-code-review), [delegate 구현](https://github.com/alibaba/open-code-review/blob/main/cmd/opencodereview/delegate_cmd.go).

## 실제 실행 결과

기존 설치된 `ocr 1.12.5 darwin/arm64`로 실행했다. 새로운 전역 설치나 LLM 리뷰 실행은 하지 않았다.

| 실험 | 결과 |
|---|---|
| 이 레포 `4311456` → `8e7064e`, JSON preview | 22개 중 5개 대상, 17개 제외. Markdown 스킬·템플릿은 unsupported_ext |
| 위 대상의 JSON rule | 규칙 2개 그룹. 4개 파일이 공유하는 규칙 본문은 7,592자 |
| 임시 Git 레포의 7개 신규 파일 | `.cs`, `.ts`, `.yaml` 포함. `.md`, `.glsl`, `.tscn`, `requirements.txt` 제외 |
| 임시 `.fullops-squad/review/rule.json`의 include | Markdown·셰이더·씬·`.test.ts` 포함 성공 |

웹·모바일·게임 전체를 지원하려는 FullOps에서 OCR의 기본 리뷰 대상만 전체 변경으로 간주하면 문서와 게임 자산 검토가 누락된다. 기본 테스트 제외도 확인 대상이다. 코드 리뷰 커버리지와 전체 변경 검토 커버리지를 따로 기록해야 한다.

## 권장 적용 구조

1. `dependencies.json`에 CLI 의존성 `@alibaba-group/open-code-review`와 외부 스킬 `open-code-review-delegate`를 추가한다. CLI는 MCP 서버가 아니므로 현재 MCP 목록에 넣지 않고 설치기의 CLI 도구 목록으로 구분한다. 전체 OCR 플러그인과 일반 `ocr review` 스킬까지 중복 설치할 필요는 없다.
2. setup에서 제품·언어·테스트·문서·게임 자산에 맞는 `.fullops-squad/review/rule.json`을 구성한다. 전역 규칙을 바꾸지 않고 모든 delegate 명령에 `--rule`을 전달한다. 기존 `.opencodereview/rule.json`과 충돌하면 통합 기준을 먼저 정한다.
3. `worker 완료 보고 → delegate 리뷰 → 수정/재검증 → 병합`으로 연결한다. 기본 리뷰는 구현자가 아닌 coordinator 또는 레포에 배정된 검토자가 수행한다. 검토 역할을 고정 생성하지 않는다. 인증·결제·데이터 변경·복잡한 동시성 등은 고성능 모델로 배정한다.
4. branch 이름 대신 실제 base/head SHA를 고정해 preview·rule·diff에 같은 대상을 사용한다. 새 커밋이 생기면 리뷰 결과를 재사용 가능한 범위와 재검토할 범위로 구분한다. 범위 리뷰는 preview의 merge_base를 따른다.
5. 보고서는 `.fullops-squad/docs/evaluations/qa-reports/<과제키>-review.md`에 통일된 템플릿으로 남긴다. base/head SHA, OCR 버전, 적용 규칙, 전체 변경·OCR 대상·제외·검토/생략 파일, 사유, 심각도별 발견 사항, 검증 근거, 미해결 사항을 포함한다. preview의 제외 파일도 직접 검토 또는 명시적 제외 사유로 처리한다.
6. 스크립트화는 preview/rule 저장, 대상 체크리스트 생성, 보고서 누락·SHA 일치 검증에 한정한다. AI 판단을 스크립트로 흉내 내거나 새 리뷰 오케스트레이터를 만들 필요는 없다. critical/high 미해결 또는 대상 누락 시 병합 수락을 보류한다.

규칙은 첫 매칭이 선택되는 구조다. 사용자 규칙이 언어별 기본 규칙에 자동으로 덧붙는다고 가정하면 안 된다. `include`는 whitelist가 아니고 일부 기본 필터를 우회하는 설정이며, 명시적 exclude와 비밀 파일 보호는 우선한다. 문서·테스트·자산 패턴은 레포에 맞게 좁게 구성한다. [공식 규칙 문서](https://github.com/alibaba/open-code-review/blob/main/pages/src/content/docs/en/review-rules.md).

설치 버전 고정만으로 재현성이 끝나지 않는다. npm wrapper는 자동 업데이트 기능이 있어 실행에 `OCR_NO_UPDATE=1`을 전달하고 실제 버전도 기록하는 것이 좋다. Git 최소 요구사항도 기존 안내에 반영해야 한다. [공식 설치 문서](https://github.com/alibaba/open-code-review/blob/main/pages/src/content/docs/en/installation.md), [Git 요구사항](https://github.com/alibaba/open-code-review#prerequisites).

## 도입 전 남은 검증

- Codex·Claude Code·grok·agy 설치 계획에서 CLI와 delegate 스킬이 함께 설치되는지 확인.
- 규칙 중복 제거와 배치 분할이 실제 입력 토큰·시간을 줄이는지 대표 웹/모바일/게임 변경으로 측정.
- 삭제·이름 변경·staged 삭제 후 untracked 재생성, 기본 제외 테스트·문서·자산의 누락 방지 확인.
- head SHA 변경·미해결 high·파일 누락을 완료로 수락하지 않는지 검증.

delegate는 코드 품질 검토의 준비 단계를 개선한다. 요구사항 충족, 문서 톤·템플릿 준수, 테스트 실행, 모델 배정과 병합 승인은 계속 FullOps가 관리해야 한다. GitHub PR 댓글 게시도 별도의 작업이며 이번 검토 범위에는 포함하지 않는다.
