---
title: FullOps 1.0.0 이슈 6 후속 검증
status: draft
updated: 2026-10-07
owner: maintainer
summary: 새 리뷰 R1–R7 보완과 실제 로컬 업데이트 및 i-Docs 두 CLI 세션의 증거를 기록한다
---

# #6 후속 검증

검토한 코멘트: https://github.com/tourbut/Fullops-Squad-plugin/issues/6#issuecomment-6033458842
기준 커밋: df981bc279c79d71a334290e15c5093a27d86c23. #8 소스는 별도 85edbd3 커밋에 보존한다.

## 보완과 회귀

| 항목 | 수정 | 확인 |
|---|---|---|
| R1 | 개발 설치의 명령별 대상 확인, FullOps 버전·내용 해시·출처 receipt와 최종 검사, Claude readFromFolder 실제 로딩 경로 검사 | 제거/부분 실패/다른 버전/동일 버전 변경 회귀, 실제 양쪽 개발 설치 |
| R2 | standalone Claude 의존 플러그인 install 명령 생성 | 누락 대상 명령 회귀와 실제 설치/호스트 검사. 실제 dependency 제거 후 복구는 미실행 |
| R3 | wrapper와 개발 설치 모두 hook과 같은 python3 3.10+ 검사 | python만 성공하는 경우 거부 회귀, Linux 실제 python3 3.12.3 |
| R4 | producer의 task/role/HEAD/attempt/지시 해시 엄격 대조 | 동일 HEAD 새 시도 결과 거부, route 명시 bind/API 없는 연결 회귀 |
| R5 | producer_status에 partial/error/미확인 ID/잔여/원문 거부 보존 | D05 양성·D10 미확인, 실패 context가 partial로 남는 회귀 |
| R6 | find Markdown은 read, 명시 edit seed/diff/update ID만 update 근거 | 참고 Markdown이 update로 승격되지 않는 회귀 |
| R7 | worker의 packet 전달/identity/HEAD/접근성, finish/review의 항목별 처리 결과 검사 | missing packet, stale identity/HEAD, worker 파일 부재, 누락/unknown 결과 차단과 실제 D05 수정 통합 회귀 |

`completed` 또는 `no_change`에는 구체적인 사유가 필요하다. 추천을 모두 수정할 의무로 만들지 않는다. 패킷의 비선택 경로/범주 쌍마다 읽기·영향·갱신 결과를 기록하고 미확인은 완료로 승격하지 않는다. 완료 보고/체크박스 진행 기록은 지시 해시에서 분리하며 실질 지시 변경은 새 입력이다.

context의 suggest_omit는 optional 목록으로 남긴다. 배치 간 확률을 전역 비교하지 않고 배치별 후보를 교대로 전달하며 batch_only/partial/잔여 후보를 기록한다. 불균형 255+1 회귀에서 확률 1인 tail을 전역 최상으로 표시하지 않는다. 정의 64개 제한도 미확인으로 표시한다. worker decisions는 의견이며 인계에 보여 주고 원본 추천은 보존한다.

## 실제 Jev 연결

`python3 tests/jev-live.py --env-file .env --output docs/evidence/jev-1.0.0-followup.json`: exit 0.
route가 선택한 architecture 역할과 D05/D10/D09를 저장·현재 지시서에 bind한 뒤 find/documents-find/context와 packet에서 실제 소비했다. 이 연결 fixture에는 explicit seed/update ID를 주지 않았다. 4개 producer가 소비됐으며 이 실행은 partial=false였다. 총 API 비용은 $0.001605114, 캐시 적중 검증은 통과했다.

기존 LIVE-1 비교는 동일 explicit seed/D05가 주어진 비교다. 새 LIVE-ROUTE 연결과 구분한다. 단일 합성 과제·제한된 문자열/정의/링크 탐색이며 구현 품질, 전체 과제 비용, 후속 모델 토큰, 재작업 절감은 미측정이다.

## 로컬 설치와 기존 세션

- 실제 이전 설치: Codex/Claude FullOps 0.9.14. CLI: Codex 0.160.1, Claude Code 2.1.292, Orca 1.4.222, Linux aarch64.
- marketplace 출처를 GitHub에서 이 개발 체크아웃으로 전환하고 `python3 scripts/install.py --host both`를 실행했다. 양쪽 1.0.0과 `deps.py --check --host codex|claude-code` exit 0을 확인했다. 서비스 setup을 다시 실행하지 않았다.
- 전환 중 Codex marketplace 제거가 기존 cache를 지웠다. 실행 중 부모 세션은 여전히 0.9.14 경로를 호출해 도구 실행이 차단됐다. 정확한 오류: `python3: can't open file '/home/shin/.codex/plugins/cache/fullops-squad/fullops-squad/0.9.14/scripts/flow_gate.py': [Errno 2] No such file or directory`.
- 새 복구 세션이 df981bc의 native 124개 파일을 기존 hook 경로에 보존 사본으로 복원했다. 이는 0.9.14 패키지 재설치가 아니라 1.0.0 기준 커밋의 호환 사본이다. hook 비활성화/래퍼 변경 없이 실행을 복구했다. 부모가 살아 있는 동안 이 사본은 유지한다.
- 기존 H1의 오류 원문과 동일한 재현이라고 확정하지 않는다. H1 원인은 여전히 미확정이다.
- Codex 신규 시작은 새 FullOps PostToolUse hook의 신뢰 확인 때문에 첫 dispatch가 readiness 단계에서 실패했다. 새 명령/플러그인 출처를 화면에서 검토한 뒤 해당 hook만 trust했다. 실패한 생성 세션은 Orca release로 정리하고 같은 task의 새 attempt로 재시도했다.

## i-Docs 실제 세션

Run: run_6d5f8427a99f. 기존 dev/ops 인박스·제품 코드·사용자 세션을 보존하고 비어 있는 arch/tester 인박스에 승인된 테스트 지시서를 작성했다. 각 worker는 자기 QA 증거·컨텍스트·완료 로그만 작성하고 로컬 역할 브랜치에 커밋했다. i-Docs push/merge는 수행하지 않는다.

Claude: arch, Opus 5.5 medium. 최초 보고 SHA 5bc574a. SessionStart 3종·PreToolUse(Bash/Write)·PostToolUse(Bash)의 자동 성공을 확인했다. UserPromptSubmit은 보고서의 로그 snapshot에서는 미확인이며, 부모가 같은 session/task/dispatch의 prompt 상태 파일로 후속 확인했다. directory 출처의 실제 hook 루트는 개발 dist이며 캐시와의 내용 일치도 검사했다. 최초 검증 당시 dist는 미커밋 후보였으므로 설치 metadata의 Git SHA로 실제 파일 내용을 대신하지 않는다.

실제 Stop에서 `O=<Orca 경로>; $O orchestration send ...` 완료 전송을 local parser가 인식하지 못해 이미 도착한 worker_done을 미완료로 경고했다. worker는 중복 회신까지 했다. 해당 세션 로그에 block 후 다음 Stop 정상 완료가 남았다. 이 결함은 현재 task/dispatch의 Orca 정본 완료를 조회하는 보완과 stale/진행 중/조회 실패 회귀로 수정했다. Run 집계에서도 in_progress를 active로 처리했다.

Codex는 SessionStart·UserPromptSubmit의 context/dispatch state와 실제 PreToolUse 거부를 관측했다. 보고서 작성용 Python here-doc 안의 `orca orchestration worker-start` 예시를 실제 실행으로 오인해 차단하는 결함도 재현했다. 공통 셸 분석에서 here-doc 본문·echo·인용된 spec은 실행 명령에서 제외하고 실제 최상위 Orca 명령만 선택하도록 수정했다. 진행 Run/route 추적과 inject 검사도 같은 분석을 사용한다. 실제 최상위 명령은 그대로 검사하는 회귀를 추가했다. Codex 최종 보고 커밋은 44747d4cd5556e6d844f22353e4ed0d2f7f66b93다. 실제 worker_done msg_4a5a1ec965d4의 현재 task/dispatch 정본 완료와 자동 PostToolUse settled=true 전환을 확인했다. 같은 세션은 task_complete 후 idle이었고 Stop 차단 메시지는 없었으나 Stop 개별 process 종료코드는 로그에 노출되지 않았다. 소유한 Codex terminal을 worker-release로 archive/종료한 뒤 delivery를 ack했다. Claude terminal은 사용자가 후속 입력을 했으므로 보존했다.

## 최종 재설치 검사

최종 재설치에서 Claude 2.1.292의 plugin list는 오래된 installPath와 최신 readFromFolder/folderVersion을 함께 반환했다. 실제 hook은 폴더에서 읽지만 최초 검사는 cache를 확인해 exit 2가 났다. readFromFolder가 있을 때 그 경로와 folderVersion을 검사하도록 수정하고 오래된 cache/변경된 실폴더/일반 cache 설치 회귀를 추가했다. 이후 `python3 scripts/install.py --host both` exit 0. Codex cache와 Claude 실제 로딩 폴더를 각각 개발 dist의 버전·내용 해시·marketplace 출처와 대조했다.

Codex add는 기존 0.9.14 호환 경로를 다시 정리했다. 부모 hook 경로가 사라진 상태로 방치하지 않고 동일 df981bc archive 124파일을 설치 후 복원·SHA 검증했다. 이는 실행 중 부모의 경로 보존이며 최신 설치 버전을 되돌리지 않는다.

## 수정본의 실제 hook 재검증

새 Claude Sonnet 5.5 medium 세션을 tester에서 실행했다. Task task_9d8267afa0ff, Dispatch ctx_e5c2d5d0978a, Session 9487f8b2-5ffc-4f53-9fe8-195688d69787, 보고 커밋 9693df72143e. 기존 사용자 arch 세션은 재사용하지 않았다.

- 자동 PreToolUse에서 worker-start 문자열을 담은 Python here-doc 쓰기가 exit 0으로 통과했다. 실제 최상위 worker-start의 --run 누락은 도구 실행 전에 계속 차단됐다.
- 마지막 worker_done을 Python subprocess로 보내 local command receipt 추적 없이 Orca msg_7f5f626fdd4d에 전달했다. 같은 세션의 자동 Stop 요약은 hookCount=3, hookErrors=[], preventedContinuation=false다. flow 상태에는 현재 task/dispatch, settled=true, settlement_source=Orca current dispatch outcome이 남았다. 정본 완료 조회 보완의 실제 실행을 확인했다.
- worker가 범위 밖의 전체 lint CLI도 실행해 설치되지 않은 frontend svelte-kit/prettier로 2건 실패했다. 이를 전체 제품 lint 통과로 표시하지 않는다. 부모는 이번 Markdown의 DOC-002/DOC-003을 별도 검사해 위반 0과 git diff --check exit 0을 확인했다.
- parent가 만든 새 테스트 terminal은 정상 완료·idle을 확인하고 release/close한 뒤 delivery를 ack했다. 사용자 arch terminal은 보존했다.

## Actions 실패와 경로 수정

77fcaaf의 Actions run 37595873280은 Linux core/OCR와 Windows portable이 통과했고 macOS portable의 Python 회귀 4건이 실패했다. macOS 임시 경로 /var가 /private/var로 resolve되면서 원래 repo 경로와 resolved 파일을 비교해 정상 파일을 외부로 거부한 것이 원인이다.

공유 local_file은 실제 containment를 resolved repo끼리 확인하고 검증한 입력 경로를 반환한다. 내부 symlink/민감 이름/외부 경로/상위 탈출 차단은 유지한다. Markdown 링크도 resolved repo를 기준으로 계산한다. 부모 경로 alias의 파일·링크·packet 접근과 차단 경계를 함께 확인하는 회귀를 추가했다. 기존 jev-observe 보안 검사는 통과했다. 수정본 Actions 재실행 결과는 아래에 기록한다.

## 검사

npm test: 전체 통과. tests/stabilization.py: 24개 통과. tests/review-check.py: pinned OCR 1.12.12 실제 delegate 검사 통과. 실제 Jev API/캐시/route 연결: 통과. build와 git diff --check: 통과.

Windows/macOS 실제 host·Unity Player·강제 종료/동시 빌드 회복·전체 제품 QA는 미실행이다. Windows/macOS portable은 CI의 launcher·실패 회복·합성 회귀·native build 검사이며 실제 CLI 설치·세션 테스트는 Linux에서만 실행했다. i-Docs main의 서비스 적용 버전 0.9.14는 테스트 설치와 구분하며 운영 정책 전체 반영/병합을 이번 점검으로 완료했다고 표시하지 않는다.
