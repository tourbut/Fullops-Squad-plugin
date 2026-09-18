# OCR delegate 실제 리뷰 테스트

후속 조치: R1·R2를 0.3.0 개발 변경에서 수정했다. 저장된 remote/base를 CLI와 공유 setup 함수에서 재사용하고, 원격 연결된 레포의 로컬 전용 역할 추가를 변경 전에 거절한다. 아래 발견 사항과 재현 결과는 수정 전 상태의 기록이다. 임시 원격 회귀 검사에 사용자 지정 upstream/release 재사용, 명시적 override, dry-run 보존, 로컬 전용 추가 거절을 포함했다.

실행일: 2026-09-18. 대상은 최근 역할/원격 브랜치 변경이며 전체 레포 감사는 아니다.

## 대상과 실행

- base: `4311456359013379a6cc984d4baadf3e23d238cd`
- head: `8e7064efd0abe8f95911e8cbcb136793ad9c9017`
- CLI: `open-code-review 1.12.5 darwin/arm64`
- `OCR_NO_UPDATE=1 ocr delegate preview --format json --from 4311456 --to 8e7064e`
- `OCR_NO_UPDATE=1 ocr delegate rule --format json --from 4311456 --to 8e7064e <대상 5개>`
- OCR 시스템 규칙을 적용했다. Python 4개 파일은 7,592자 규칙을 공유하며 JSON 1개는 85자 규칙을 적용한다.
- preview의 merge_base로 Git diff를 읽고, 관련 setup/work 코드와 스킬의 실제 호출 흐름을 확인했다.
- OCR이 제공한 규칙에 따라 호스트 AI가 리뷰했다. 별도 LLM endpoint 호출·다른 리뷰 모델 실행은 하지 않았다.
- 작업 트리의 앞선 검토 보고서는 범위 밖이다. 테스트용 Git push는 임시 bare remote에만 실행했다.

## 재현된 발견 사항

### R1 — medium / bug: 저장된 remote와 기준 브랜치를 재실행 기본값으로 사용하지 않는다

- path: `plugins/fullops-squad/scripts/setup.py`
- start_line: 132
- end_line: 140
- content: 기존 설정에 `git.remote=upstream`, `git.base=release`를 저장했어도 CLI 기본값은 origin이며 base 생략 시 원격 HEAD로 다시 결정한다. 역할 추가를 위해 일반 setup 명령을 재실행하면 잘못된 기준에서 새 역할 브랜치가 만들어지거나 존재하지 않는 origin 때문에 실패한다.
- 재현: main과 다른 커밋의 release를 가진 임시 원격에서 engine을 release 기준으로 생성했다. 이후 `--roles gameplay`만 추가하자 설정의 base가 main으로 바뀌고 gameplay 브랜치도 main SHA를 가리켰다. remote를 upstream으로 바꿔 설정에 저장한 뒤 remote 옵션을 생략한 dry-run은 origin 부재로 실패했다.
- 권장 수정: 명시적 옵션 → 저장된 설정 → 최초 setup 기본값 순으로 선택한다. 기준 변경은 사용자가 지정한 경우에 적용한다.

### R2 — medium / bug: 로컬 전용 역할 추가가 원격 설정과 불일치한다

- path: `plugins/fullops-squad/scripts/setup.py`
- start_line: 108
- end_line: 111
- content: 원격 연결된 레포에서 `--roles localworker --local-only`를 실행하면 역할은 추가되지만 기존 `git.remote`는 유지되고 해당 역할 원격 브랜치는 생성되지 않는다. bootstrap 지침은 등록 역할을 해당 원격 브랜치에서 생성하도록 하므로 없는 브랜치를 찾게 된다.
- 재현: 원격 setup 완료 후 local-only로 역할을 추가했다. fullops.json에는 origin과 localworker가 함께 있었지만 `git ls-remote origin refs/heads/fullops/localworker`는 빈 결과였다. 이후 원격 setup을 다시 실행해야 브랜치가 생성됐다.
- 권장 수정: 원격 연결된 레포의 local-only 역할 추가를 명확히 처리한다. 가장 작은 변경은 이 조합을 거절하거나, 원격 생성이 미완료라는 상태를 기록하고 bootstrap이 이를 확인하도록 하는 것이다. 전체 레포의 원격 설정을 무조건 삭제하는 방식은 기존 worker에 영향을 준다.

critical/high 발견 사항은 없다. 위 두 항목은 재현된 동작 결함이며 이번 테스트에서 수정하지 않았다.

## 검증 결과

`npm test`는 통과했다. 기존 테스트는 origin/main의 반복 실행·역할 추가·push 거절을 검증하지만 저장된 사용자 지정 remote/base의 기본값 재사용과 원격/로컬 혼합 역할 상태는 검증하지 않는다. 따라서 green 결과만으로 두 문제를 배제할 수 없다.

대상 누락 없이 실제 diff를 확인했다. 삭제된 12개 역할 파일은 setup의 동적 생성 및 기존 기록 보존과 대조했다. 발견 사항을 재현하는 실행은 모두 임시 레포에서 완료했다.

## 커버리지

| 지표 | 결과 |
|---|---|
| total_files (전체 diff) | 22 |
| OCR reviewable_files | 5 |
| OCR excluded_files | 17 |
| reviewed_files (OCR 대상) | 5 |
| skipped_files (OCR 대상) | 0 |
| coverage_rate (OCR 대상) | 100% |
| 전체 변경 reviewed_files | 22 |
| 전체 변경 skipped_files | 0 |
| 전체 변경 coverage_rate | 100% |

파일 상태 M은 수정, D는 삭제다. OCR 제외는 최종 리뷰 생략으로 처리하지 않았다.

| path | status | 결과 | 방식 |
|---|---|---|---|
| `README.md` | M | reviewed | 직접 검토 (OCR 제외) |
| `docs/diagnostics/harness-probes.py` | M | reviewed | OCR 규칙 + 직접 검토 |
| `plugins/fullops-squad/assets/repository/.fullops-squad/contexts/architect.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/contexts/backend_dev.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/contexts/devops.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/contexts/docs.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/contexts/frontend_dev.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/contexts/qa_tester.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/handovers/to_architect.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/handovers/to_backend_dev.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/handovers/to_devops.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/handovers/to_docs.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/handovers/to_frontend_dev.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/handovers/to_qa_tester.md` | D | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/assets/repository/.fullops-squad/orca-agents.md` | M | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/plugin.json` | M | reviewed | OCR 규칙 + 직접 검토 |
| `plugins/fullops-squad/scripts/setup.py` | M | reviewed | OCR 규칙 + 직접 검토 |
| `plugins/fullops-squad/scripts/work.py` | M | reviewed | OCR 규칙 + 직접 검토 |
| `plugins/fullops-squad/skills/fullops-orca/SKILL.md` | M | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/skills/fullops-work/SKILL.md` | M | reviewed | 직접 검토 (OCR 제외) |
| `plugins/fullops-squad/skills/setup-fullops/SKILL.md` | M | reviewed | 직접 검토 (OCR 제외) |
| `tests/check.py` | M | reviewed | OCR 규칙 + 직접 검토 |

## 도입 판단

실제 delegate 명령과 규칙 공유는 정상 동작했고, 기존 테스트가 놓친 결함을 호스트 리뷰에서 찾을 수 있었다. 결함을 찾은 판단은 OCR의 자동 판정이 아니라 호스트 AI의 코드 검토와 재현 결과다. 기본 제외 파일을 보완하는 절차가 필요하다. 토큰 절감률·전용 OCR review 대비 품질·다른 모델 대비 성능은 이번 실행에서 측정하지 않았다.
