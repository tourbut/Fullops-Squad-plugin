---
name: fullops-review
description: FullOps 활성 레포에서 worker 구현 완료 후 병합 전 OCR delegate 리뷰를 준비하거나 리뷰 기록을 검증할 때 사용한다.
---

# 병합 전 delegate 리뷰

현재 Git 레포 루트의 `.fullops-squad/fullops.json`으로 활성화를 확인한다. 없으면 `setup-fullops`를 안내하고 멈춘다.
`.fullops-squad/rules/common/README.md` 및 연결된 세 규칙, `project.md`의 정본과 지시서의 `적용 기준과 예외`를 직접 읽는다. 이전 FULLOPS.md에 링크가 없어도 확인한다. 규칙이 없거나 worker가 사용한 버전과 다르면 setup 갱신 또는 준비 커밋·명시적인 스냅샷으로 일치시키고 재검토 범위를 정하기 전 수락하지 않는다.
공통 규칙은 OCR의 `review/rule.json`을 자동 대체하지 않는다. report.md에 규칙 식별자·문서 경로·기준 커밋 또는 스냅샷·예외·검증 근거를 남긴다. `review.py check`는 공통 Markdown의 내용·버전이나 테스트 성공을 자동 검증하지 않으며 미해결 critical/high 차단은 그대로 유지한다.

1. 레포의 `fullops.json`, 요구사항·설계·핸드오버 완료 기준을 읽고 병합 책임자 또는 배정된 검토자가 리뷰한다. 고정 리뷰 역할은 없다. 인증·결제·데이터 변경·동시성 등 위험한 변경은 고성능 모델에 배정한다. `open-code-review-delegate` 외부 스킬을 읽는다. OCR 측 LLM 설정과 일반 `ocr review`는 사용하지 않는다.
2. 레포의 `.fullops-squad/review/rule.json`을 확인한다. setup에서 제품별 테스트·문서·씬·셰이더 등의 include와 생성물 exclude를 구성한다. include는 whitelist가 아니며 사용자 규칙은 첫 매칭으로 기본 언어 규칙을 대체한다. 기존 `.opencodereview/rule.json`을 통합할 때 이 의미를 보존한다. 전역 규칙은 변경하지 않는다.
3. 이 스킬 기준 `../../scripts/review.py`를 사용해 `python3 <review.py> prepare --repo <루트> --key <리뷰 키> --from <기준 ref> --to <worker ref>`를 실행한다. SHA를 고정한 preview·rules·result와 report 템플릿이 `docs/evaluations/qa-reports/<키>-review/`에 생성된다. 기존 기록은 덮어쓰지 않으므로 재리뷰는 새 키를 사용한다. OCR CLI가 없거나 JSON 명령이 실패하면 실패를 보고하고 설치기를 안내한다.
4. preview의 merge_base와 head로 Git diff를 읽는다. rules는 그룹당 한 번 읽고 관련 파일을 적절한 배치로 검토한다. 내부 코드는 diff와 관련 파일을 직접 검색해 읽고, 외부 SDK 근거는 Context7을 사용한다. OCR 제외 파일도 직접 확인하거나 구체적인 생략 사유를 남긴다. 삭제·이름 변경 영향도 검토한다. 요구사항·문서 템플릿·테스트 실행은 FullOps 검토 범위에 포함한다.
5. result.json의 모든 `(path,status)`에 `review_status: reviewed/skipped`와 `reason`을 기록한다. reviewer와 conclusion을 채운다. findings에는 `path`, `content`, 필요 시 `start_line/end_line`, `severity: critical/high/medium/low`, `resolved: true/false`를 기록한다. report.md에 발견 사항·재현·검증·커버리지·생략 영향·수락 결론을 같은 톤으로 작성한다. AI가 판단한 결과이며 OCR의 자동 판정으로 보고하지 않는다.
6. lint 결과를 남긴다. 이 스킬 기준 `../../scripts/lint.py`로 `python3 <lint.py> --repo <worker 체크아웃 루트> --from <기준 ref> --out <리뷰 디렉터리>/lint.json`을 실행한다. worker 체크아웃은 보고된 SHA에 있고 작업 트리가 깨끗해야 한다. 실행 불가 명령은 사유를 `reason`에 적는다. ERROR가 있으면 수락하지 않고 수정을 요청한다. WARNING과 실행 불가의 영향은 report.md에 적는다.
7. `python3 <review.py> check --repo <루트> --key <키> --from <현재 기준 ref> --to <현재 worker ref>`를 실행한다. 실제 병합 ref를 전달해야 SHA 변경을 감지한다. 대상 누락, 규칙 변경, pending, 미해결 critical/high, lint 결과 누락·SHA 불일치·ERROR·사유 없는 실행 불가는 실패다. check 통과는 기록 검사이며 skipped의 수락 가능성과 테스트 결과는 검토자가 판단한다. 수정 커밋이 추가되면 새 SHA로 다시 리뷰한다.
8. 과제에 `docs/evaluations/jev/<과제 키>-find.json`이 있으면 check가 실제 변경과 비교한 적중률을 리뷰 디렉터리의 `jev-find-score.json`에 자동으로 남긴다. 리뷰 키가 과제 키와 다르면 check에 `--task-key <과제 키>`를 넘긴다. 수락 판단에는 쓰지 않는다.
9. 보고서·검증 근거를 완료 기록에 연결하고 미해결 사항은 PLANS.md에 남긴다. GitHub 댓글 게시·자동 병합은 실행하지 않는다. 병합 책임자는 최신 SHA에 대한 리뷰 수락과 허가된 병합 범위를 확인한다.
