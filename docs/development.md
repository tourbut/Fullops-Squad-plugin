# FullOps Squad 개발

플러그인 자체를 고치는 사람을 위한 문서다. 사용법은 [README](../README.md)를 본다.

## 구조

- `plugins/fullops-squad/`: Agent Plugins 1.0.0 표준 원본. `plugin.json`과 `mcp.json`이 공통 정본이다.
- `adapters/`: 호스트별 메타데이터.
- `dist/native/fullops-squad/`: `scripts/build.py`가 만드는 생성물. 직접 고치지 않는다. 루트 마켓플레이스 카탈로그가 이 경로를 가리키므로 호스트 검증 전에 빌드한다.
- `dependencies.json`: 외부 스킬·MCP·도구의 출처와 설치 대상. 외부 구현은 이 레포에 복사하지 않는다.
- `docs/releases/`: 버전별 변경 범위와 기존 레포 적용 방법.

## 검증

```bash
python3 scripts/build.py
npm ci
npm test
npm run test:review  # OCR CLI가 설치된 환경의 delegate 통합 검사
python3 scripts/install.py --host all --dry-run
claude plugin validate dist/native/fullops-squad
claude plugin validate .claude-plugin/marketplace.json
grok plugin validate dist/native/fullops-squad
agy plugin validate dist/native/fullops-squad
```

`npm test`는 Python 회귀 검사와 표준 스키마 검사를 실행한다. setup·hook·스크립트 검사는 임시 레포에서 돌고, 공식 스키마 사본과 개발용 Ajv로 표준 형식을 검사하며 실행 중 스키마를 다운로드하지 않는다. agy 검증에는 MCP 실행 파일이 PATH에 있어야 한다. GitHub Actions는 기본 검사와 OCR CLI의 실제 delegate 검사를 별도 job으로 실행한다. 전체 Orca worker 기동은 별도 통합 검증이 필요하다.

Windows에서 로컬로 돌리려면 실제 `python3` 실행 파일(Microsoft Store 스텁이 아닌 것), `PYTHONUTF8=1`, 심볼릭 링크용 개발자 모드가 필요하다.

선택형 Jev 관찰 실험의 입력 형식과 실행 방법은 [Jev 관찰 실험](jev-observe.md)에 있다.

## 참고

- [Agent Plugins 표준 적용](agent-plugins-spec-review.md): 공통 배포 형식과 호스트 호환 패키지.
- [mattpocock/skills](https://github.com/mattpocock/skills): 배포와 레포별 setup 분리 방식 참고.
- [Claude Code 플러그인 의존성](https://code.claude.com/docs/en/plugin-dependencies): 네이티브 dependencies 및 cross-marketplace 허용 목록.
- [OpenAI 플러그인 패키징](https://developers.openai.com/plugins/build/plugins): Codex 패키지 구조 참고.
- [Antigravity CLI 플러그인·스킬](https://antigravity.google/docs/cli/plugins/): agy 패키지 형식과 사용자 스킬 경로.
- [skills CLI 호스트 매핑](https://github.com/vercel-labs/skills/blob/main/src/agents.ts): `grok`·`antigravity-cli` 설치 대상.
