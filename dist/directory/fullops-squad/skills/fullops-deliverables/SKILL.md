---
name: fullops-deliverables
description: FullOps setup이 완료된 레포에서 기획·설계·구현·이행 산출물 13종을 작성하거나 개발 결과와 문서의 추적성을 검증할 때 사용한다.
---

# 개발 산출물

문서를 작성하거나 검토할 때 `.fullops-squad/docs/agents/document-writing.md`의 front matter와 한국어 STE 작성 원칙을 적용한다. 기존 레포에 이 파일이 없으면 `setup-fullops` 갱신으로 추가한다.

현재 Git 레포 루트의 `.fullops-squad/fullops.json`이 없으면 생성하지 않고 setup을 안내한다.
`.fullops-squad/FULLOPS.md`를 읽는다. 원천 매핑은 `.fullops-squad/docs/deliverables/README.md`가 정본이다. 이 스킬의 `../../scripts/deliverables.py`가 원천 파일과 조립 문서의 로컬 링크를 검사한다.

1. 요청한 단계나 D01–D13을 대상으로 정한다. 지정이 없으면 현재 작업에 영향을 받는 문서만 선택한다.
2. 기존 원천 문서·코드·검증 결과를 읽는다. 입력이 부족한 절은 미확정으로 표시하고 필요한 입력을 명시한다.
3. 원천을 갱신하고 개정 날짜·상위 요구사항·하위 영향 문서를 연결한다. 원천 문서의 front matter는 직접 쓰지 않고 이 스킬 기준 `../../scripts/deliverables.py`의 `--stamp`로 쓴다: `python3 <deliverables.py> --repo <레포 루트> --id DNN --stamp --task <과제 키> [--status ...]`. 처음 쓰면 `--owner`·`--summary`가 필요하고, 원천이 폴더이거나 여러 파일이면 `--path`로 문서를 고른다. 인덱스 표의 상태도 함께 맞춰진다. 기존 문서의 자유 형식 상태 줄은 `--stamp` 후 본문에서 지운다. 원천 경로가 기존 프로젝트에 있으면 매핑을 그 경로로 바꾸어 재사용한다.
4. `python3 <deliverables.py> --repo <레포 루트> --id DNN`으로 요청한 산출물의 경로·링크와 front matter를 검사한다. front matter 문제는 경고로 나오고 `--strict`면 오류다. 바뀐 원천 문서의 문제는 lint `DOC-002` ERROR로 병합이 막히므로 `--stamp`로 다시 쓴다. 전체 검토는 `--id` 없이 실행한다. 요구사항 ID와 화면/API/데이터/모듈/QA의 연결, 고아 테이블, 코드와 설계 차이는 직접 확인한다. 실행하지 못한 검증은 구분한다.
5. `deliverables/DNN_<slug>.md`에는 원천 절 링크·상태·조립 날짜만 쓴다. 원문을 이중 관리하지 않는다. 납품용 docx/pdf 요청이 있으면 이 원천으로 출력한다.
6. 인덱스의 상태·원천 링크를 갱신하고 결과를 해당 작업 로그에 남긴다. `approved`는 실제 승인 근거가 있을 때만 사용한다. 스키마 생성 명령이 없으면 D08을 자동 생성했다고 보고하지 않는다.

## 공유 원천과 상태

D06/D07/D09처럼 하나의 원천을 공유하면 stamp가 `id: [D06, D07, D09]`와 ID별 `statuses` 객체를 보존한다. 특정 ID의 상태 변경이 다른 ID를 자동 승인하지 않는다. 하나의 ID가 여러 원천을 갖고 있을 때 상태가 서로 다르면 일부 전환은 쓰기 전에 거부된다. 다른 원천의 검토가 끝나기 전 인덱스만 승격하지 않는다. 모든 원천을 실제 검토한 경우에만 `--all-sources --status <상태>`로 해당 ID의 전체 상태를 원자적으로 전환한다. 본문·owner·이전 과제와 다른 ID의 상태를 보존한다. draft/review/approved 폴더에는 실제 Markdown 원천이 있어야 한다. 미작성/범위 밖은 원천 생성 의무에서 제외한다.

대화 미참조 인계는 fullops-review의 점검을 수행하고 원천·절·미완료/미확인 사유를 기록한다. 형식 검사와 의미 점검을 별도 결과로 남긴다. 링크 검사는 로컬 파일 존재를 확인하며 fragment/원격 링크/내용 의미는 자동 검증 범위가 아니다.
