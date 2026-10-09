---
title: Git 메타데이터 탐색과 Jev 평가
status: draft
updated: 2026-10-09
owner: maintainer
summary: 이슈 18의 로컬 캐시, 탐색 범위, offline 정책과 비교 검증을 기록한다.
tasks: [ISSUE-18]
---

# Git 메타데이터 탐색

Git 커밋을 원본으로 사용한다. `search_index.py`는 원문에서 추출한 메타데이터를 재사용한다. SQLite와 본문 복제 저장소는 추가하지 않는다. 보드의 현재 작업 폴더 렌더링은 기존 `board_documents.documents()`를 사용한다.

## 캐시와 재생성

캐시는 `git rev-parse --absolute-git-dir`의 `fullops-search/code.json`과 `documents.json`이다. 연결 워크트리는 자기 Git 디렉터리를 사용한다. 캐시에는 커밋, 경로, blob OID, 파서 버전, 범위 설정 해시와 메타데이터 무결성 해시를 저장한다. 질의별 모델 점수와 파일 본문은 저장하지 않는다.

같은 경로·blob·설정은 다시 파싱하지 않는다. 변경·추가 파일만 파싱한다. 삭제 경로는 제거한다. 이동은 삭제와 추가로 처리한다. 같은 blob의 복수 경로도 각각 기록한다. 파서·스키마·exclude 변경은 재생성을 유발한다. 과거 커밋 score는 해당 커밋의 객체를 읽는다.

writer는 배타적 `writer.lock`을 획득한다. 캐시는 같은 디렉터리의 임시 파일을 fsync한 뒤 교체한다. Windows 공유 위반은 세 번까지 교체를 시도한다. 잠금·쓰기·교체 실패는 캐시를 최신으로 신뢰하지 않고 Git 직접 읽기로 돌아간다. 중단으로 잠금 파일이 남으면 직접 읽기를 계속한다. 실행 중인 writer가 없음을 확인한 뒤 해당 잠금 파일을 지우면 캐시 쓰기를 재개한다. JSON을 지우면 다음 실행에서 재생성한다.

검색은 시작 시 확정한 커밋만 읽는다. 실행 중 HEAD가 바뀌면 find/packet은 결과를 현재 HEAD와 혼합하지 않고 재실행을 요구한다. 색인 자체는 처음 확정한 커밋의 결과를 유지한다.

## 추출과 안전 범위

문서는 기존 front matter 파서로 title·summary·승인 status·다중 D번호 statuses를 보존한다. 소제목과 로컬 링크도 제한된 개수만 추출한다. Python은 AST의 함수·클래스 이름, 정의 줄, 시그니처와 docstring을 사용한다. 다른 언어와 파싱 실패는 헤더 기반으로 표시한다. 전체 호출 그래프와 LSP 참조 분석은 수행하지 않는다.

원문 읽기는 기존 65,536바이트 한도를 유지한다. 잘린 원문은 partial이다. 정의·소제목·링크는 최대 24개다. 모델 설명은 최대 800자이며 정의는 앞의 8개만 포함한다. 이 상한은 관련성 재현율의 보장이 아니다. 원문 키워드·심볼 검색과 packet의 정의·참조 후보로 보완한다.

민감 경로·심볼릭 링크·서브모듈·바이너리·exclude 경계를 유지한다. 원문 prefix의 명백한 비밀값 패턴은 해당 파일의 메타데이터 생성을 막는다. 원문과 payload 검사는 임의 형식의 비밀을 완벽하게 탐지하지 못한다. 전송자는 전송 가능한 파일만 사용한다.

## 의미 탐색과 패킷

후보 ID와 설명은 shared state의 `entries`에 한 번만 넣는다. Choice criteria에는 ID만 둔다. Noul은 같은 entries를 바탕으로 관련 위치의 근거가 있는지 묻는다. [TypeSafe state](https://docs.typesafe.ai/concepts/state)와 [semantic_find](https://docs.typesafe.ai/cookbooks/semantic_find)의 계약을 따른다.

낮은 Noul의 `not_confirmed`는 지도에서 관련성을 확인하지 못했다는 뜻이다. 저장소에 코드가 없다는 판단이 아니다. 0.7/0.35와 누적 확률 0.99는 기존 예제 정책이며 운영 데이터로 교정된 값이 아니다. 게이트에 사용하지 않는다.

기본 전략은 전체 후보의 배치 탐색이다. 호출마다 선택지 255개와 문자 예산 24,000자를 각각 관리한다. 문자 예산은 토큰 상한이 아니다. 실제 입력/출력 토큰·알려진 비용·호출별 모델·지연을 별도 기록한다. 지시서 발췌와 미전송·읽기 실패·잔여 후보를 명시한다. 배치 확률은 서로 비교하지 않는다. 결과 수 제한을 입력 비용 절감이라고 표현하지 않는다.

평가용 `rerank`는 배치 후보 중 하나의 공통 예산 안에 든 shortlist만 재정렬한다. shortlist 밖 후보는 남겨 둔다. 평가용 `hierarchical`은 하위 파일 설명을 가진 폴더 구간을 먼저 정렬하고 여러 폴더를 탐색한다. 잘못 선택한 폴더에 고정되지 않도록 모든 대안 폴더로 확대한다. 두 전략은 기본 CLI 전략으로 채택하지 않는다. [계층 탐색](https://docs.typesafe.ai/cookbooks/hierarchical_classification)과 [재정렬](https://docs.typesafe.ai/cookbooks/rerank_typesafe)의 아이디어를 제한적으로 비교한다.

백틱으로 명시한 경로와 정확한 심볼·오류 문자열은 별도 Git grep seed로 보존한다. seed 검색은 안전한 지도 경로와 교집합만 사용한다. 필수 문서는 packet에서 유지한다. 키워드 무일치로 의미 탐색 후보를 제거하지 않는다. 잘못된 ID·응답·장애는 unknown과 로컬 문자 검색 후보로 돌아간다.

packet은 직접 수정·영향 확인·문서 읽기·문서 갱신 범주를 유지한다. find 추천은 읽기·영향 확인 후보이며 자동 수정 승인이 아니다. 명시 seed·tracked diff·update ID로 수정 범위를 정한다. 문자열 출현과 로컬 링크는 영향 확인 후보이지 실제 호출 관계의 확정 근거가 아니다.

find는 HEAD를 검색한다. packet은 tracked 작업 폴더 변경과 명시 seed·필수 문서의 로컬 원문을 함께 읽는다. 각 항목의 `source_basis`는 HEAD, tracked overlay 또는 명시/필수 untracked를 구분한다. 전체 untracked 파일을 자동 전송하지 않는다. worker 시작 전 `source_sha256`가 달라지면 packet을 다시 만든다. 인박스는 기존 instruction digest로 진행 상태·복귀 주소·완료 보고를 정규화한다. 완료 검사는 구현 중 원문 변경을 허용하며 항목별 처리 근거를 요구한다.

## 폐쇄망

실행 환경에 `FULLOPS_OFFLINE=1` 또는 `FULLOPS_JEV_ENABLED=0`을 설정한다. 공통 request 함수가 API와 응답 캐시를 읽기 전에 차단한다. find는 로컬 문자 검색 후보와 `semantic_search: false`를 반환한다. route는 기존 보수적 fallback, context/observe는 후보 유지로 처리한다. 조작 판단도 같은 공통 request 차단을 적용한다.

관련 Git 읽기는 `GIT_NO_LAZY_FETCH=1`을 사용한다. offline에서는 Git 프로토콜도 비활성화한다. 누락 객체는 수동 확보가 필요한 미확인 범위다. `--force`는 과제 결과 갱신이며 응답 캐시를 우회하지 않는다. 실제 재호출은 `FULLOPS_JEV_CACHE_BYPASS=1`로 구분한다. 결과 정체성에는 커밋·지시서·파서·정책·모델·offline 설정을 반영한다.

## 검사와 비교

```bash
python3 tests/search-index.py
python3 tests/search-eval.py --env-file .env --output docs/diagnostics/search-eval-issue-18.json
```

첫 명령은 외부 호출 없이 증분/전체 재생성, 과거 커밋, 브랜치·워크트리, 동시 writer, 손상·잠금·Windows 교체 실패, 민감 파일, shared state, ID 검증, offline 차단과 패킷 갱신을 검사한다. 기본 `npm test`와 Windows/macOS CI에도 포함한다.

둘째 명령은 실제 Jev로 같은 합성 과제와 260개 방해 파일을 비교한다. 코드 위치의 표현이 다른 과제, 명시 경로 과제, 관련 구현이 없는 과제를 포함한다. 직접 수정·영향·문서 read/update 라벨을 따로 평가한다. 라벨은 검색 입력에 주입하지 않는다. 모델 사용량과 최종 packet의 fixture 문맥 문자량을 구분한다. 실측 원본은 [비교 JSON](diagnostics/search-eval-issue-18.json)에 보존한다. 이 합성 평가로 실제 서비스 재현율·전체 작업 비용·비용 절감을 주장하지 않는다.

### 2026-10-09 최종 합성 비교

모델은 `typesafe/jev-1.13-20260917`이다. 세 과제 전체의 관측값을 합산했다. 캐시를 우회한 호출이며 실패는 없었다.

| 전략 | 호출 | 입력 토큰 | 출력 토큰 | 관측 비용(USD) | 경과 시간(초) |
|---|---:|---:|---:|---:|---:|
| batch | 9 | 60,795 | 8,973 | 0.002553390 | 90.055 |
| rerank | 12 | 68,516 | 9,313 | 0.002877672 | 88.054 |
| hierarchical | 36 | 125,307 | 10,221 | 0.005262894 | 99.514 |

관련 구현이 있는 두 과제는 세 전략 모두 라벨링한 코드·계약 문서를 찾았다. 필수 계약 문서 누락은 없었다. 표현이 다른 과제의 직접 수정 분류는 자동 승격하지 않아 recall 0이었다. 명시 seed 과제는 직접 수정·영향·문서 read/update를 각각 평가한다. 이 차이는 검색 실패와 수정 범위 확정을 구분한다.

폴더 전략은 대안 폴더를 모두 확대하므로 호출·입력량이 늘었다. 재정렬도 추가 호출에 비례한 품질 개선을 이 사례에서 확인하지 못했다. 기본 배치 전략을 유지한다. 부재 과제의 낮은 Noul과 unclear는 지도 수준의 판단으로 보존한다.

같은 Windows 합성 지도에서 최초 메타데이터 생성은 21.661초, 무변경 재사용은 0.507초였다. 단일 실행의 관측값이며 다른 저장소의 성능 보장이 아니다.

측정의 기준은 JSON에 기록한 runner·implementation·map 지문이다. 최종 코드의 손상 메타데이터 거부와 하네스 문서 seed 보존은 별도 회귀검사로 확인한다. 실제 서비스 과제, 호스트 전체 토큰, 전체 작업 비용과 임계값 교정은 미측정이다.

### 구현 검증

Windows에서 `npm ci`, `npm test`, `python3 tests/review-check.py`와 패키지 스키마 검사를 통과했다. 메타데이터 NaN·손상된 필드·명시 하네스 문서 seed와 패킷 갱신의 추가 회귀검사도 통과했다. `scripts/build.py`로 재생성한 배포물의 Python 파일은 portable source와 일치한다. Linux/macOS 원격 CI와 실제 서비스 과제 평가는 실행하지 않았다.
