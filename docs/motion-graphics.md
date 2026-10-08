---
title: 로컬 모션그래픽 연결과 검증
status: draft
updated: 2026-10-08
owner: maintainer
summary: HyperFrames와 Remotion 공식 스킬 참조, 로컬 클립 합성 및 재렌더 검증 기록
---

# 로컬 모션그래픽

이슈 [#8](https://github.com/tourbut/Fullops-Squad-plugin/issues/8)와 사용자 후속 지시를 적용했다.
FullOps에는 `fullops-motion` 연결 스킬만 배포한다. 공식 스킬을 참고하고 제작·미리보기·렌더는 로컬 도구로 직접 수행한다.
공통 의존성·setup·역할/워크트리 수를 늘리지 않는다. 외부 생성 API·클라우드 렌더·업로드/게시를 실행하지 않는다.
개발용 예제와 검사기는 `tests/motion-example/`, `tests/motion_check.py`이며 플러그인 패키지에 포함하지 않는다.

## 도구와 조합

| 항목 | 검토/실행 기준 |
|---|---|
| HyperFrames | CLI 0.8.139, 공식 스킬 commit `e6daed3df04d9b9373601e4293018ffa09023144` |
| Remotion | CLI 및 remotion/@remotion 패키지 4.0.533, 공식 스킬 commit `473352613039e718e46655a26df224851e84c4aa` |
| 런타임 | Linux aarch64, Node 26.5.0, 시스템 Google Chrome, NVIDIA GB10 |
| 인코더 | Remotion 내장 FFmpeg n7.1: 무음 HF·Remotion 렌더/검사. Ubuntu FFmpeg 6.1.1-3ubuntu5: HF 내레이션 믹스·RGB 비교 |
| 자산 | 로컬 GSAP 3.15.0, NanumBarunGothic, 자체 영문 대본의 eSpeak NG 1.51 음원 |

짧은 HTML 모션은 HyperFrames `hyperframes`/`motion-graphics`, 내레이션 소개는 `general-video` 규약을 참고했다.
React 구성은 Remotion `remotion-best-practices`/create/markup/render/studio의 composition·미디어 timing·local-fonts 규약을 참고했다.
두 도구의 병용은 **HyperFrames 6초 클립 → Remotion 15초 합성**으로 검증했다. React 소스를 HTML에 직접 실행하거나 번역 결과의 동등성을 보증하지 않는다.

공식 근거: [HyperFrames core](https://github.com/heygen-com/hyperframes/blob/e6daed3df04d9b9373601e4293018ffa09023144/skills/hyperframes-core/SKILL.md),
[HyperFrames CLI](https://github.com/heygen-com/hyperframes/blob/e6daed3df04d9b9373601e4293018ffa09023144/skills/hyperframes-cli/SKILL.md),
[Remotion 스킬](https://www.remotion.dev/docs/ai/skills), [Remotion 4.0.533 라이선스](https://github.com/remotion-dev/remotion/blob/v4.0.533/LICENSE.md).
Remotion 무료 자격은 사용 주체에 달려 있다. 이번 로컬 실행은 상업 사용 전 적합성 평가이며 다른 조직의 무료 자격을 보증하지 않는다.

## 실행 결과

모든 출력은 1280×720, 30fps, H.264 MP4다. API/클라우드/유료 생성 호출은 0회다. 로컬 계산 비용이나 전체 작업 비용을 0으로 단정하지 않는다.

| 사례 | 실제 결과 |
|---|---|
| HF 무음 도형 모션 | 6초·180프레임·영상 stream 1·음성 없음, 렌더 약 9.3초 |
| HF general-video 내레이션 | 15초·450프레임·영상/음성 stream 각 1, 렌더 약 21.2초 |
| HF 클립을 Remotion으로 합성 | 15초·450프레임·영상/음성 stream 각 1 |
| 구간 정책 | 최종 MP4의 389프레임(12.966…초)에 텍스트 없음, 390/449프레임에 `함께 만드는 모션` 확인 |
| 한글 글꼴 | 정상 NanumBarunGothic 로드·문구/경계/마지막 프레임 확인. glyph 깨짐/문구 잘림 없음 |
| 음성 기술 | 자체 영문 대본 6.376초, 시작 0.5초, 최종 PCM peak 약 0.7075, clipped sample 0, 신호 종료 약 6.51초 |
| 음성 청취 | **not_run**. 기계적 음성의 발음/억양·자연스러움을 수락하지 않음 |
| 재렌더 | 두 번째 경로에서 lock로 npm ci, HF 재렌더 후 Remotion 재합성. 규격 통과, 10개 선택 프레임의 RGB RMSE 0 |

프레임 비교는 같은 호스트의 두 디렉터리에서 수행했다. 다른 OS/GPU의 완전한 동등성, 모든 프레임이나 MP4 바이트 동일성을 보증하지 않는다.
첫 프레임과 6/12초 반복 경계의 빈 화면은 원본 clip의 entrance 재시작이다. 13초부터 closing 타이포가 표시된다.
시각 검수는 위 실제 프레임에서 수행했으며 음성 청취와 사용자 미적 수락은 별도다.

### PR 검토에서 보완한 검사 경계

위 렌더 기록과 JSON의 `status=passed`는 2026-10-07 당시 제한된 검사의 원문이다. 당시 검사는 색 속성, 프레임별 시각, 입력 음원과 실제 출력의 구간별 대응을 검증하지 않았다. 이를 새 기술 검사 전체 통과로 해석하지 않는다.

2026-10-08 검사기는 spec의 네 색 속성을 실제 stream과 대조하고, 모든 영상 프레임의 시각으로 고정 FPS를 확인한다. 음성이 있으면 로컬 FFmpeg로 원본과 출력을 8kHz mono PCM으로 디코드해 계획된 unity-gain 합성의 0.25초 구간별 대응을 검사한다. 가공 음성·fade·공간 음향과 실제 청취는 별도 검수가 필요하다. 도구나 프레임 시각 metadata가 없으면 unavailable이며, 색 속성 누락·불일치는 failed다.

기존 HF 출력은 BT.709/TV인 반면 Remotion 합성·재렌더는 BT.470BG/PC이고 transfer/primaries가 누락됐다. 새 예제의 BT.709/TV spec에서 기존 합성은 실패한다. 색 변환·원본 영상 재검사·전체 재렌더는 이번 PR 검토에서 실행하지 않았다. 과거 원문 증거를 보존하고 `review_assessment`에 새 검사 기준의 실패·미실행을 분리했다.

Windows의 로컬 FFmpeg/FFprobe 회귀 영상에서는 정상 AAC/CFR 합성 통과와 무음·시작 이동·중간 잘림, 색 속성 불일치·가변 FPS 실패를 확인했다. 이는 기존 소개 영상의 새 수락 검사를 대신하지 않는다. 검사 명령은 [FFprobe 공식 문서](https://ffmpeg.org/ffprobe.html)와 [FFmpeg 공식 문서](https://ffmpeg.org/ffmpeg.html)를 대조했다.

### 검사와 실패 보존

- HF check는 실제 브라우저에서 runtime/layout/contrast를 실행했다. 무음 예제에 motion sidecar를 추가해 121개 sample의 명시적 움직임 assertion을 통과했다. 텍스트 없는 clip의 contrast checked=0과 general의 motion sidecar 미적용은 별도로 기록한다.
- 한 장면 안의 도형 그룹에 `nested_structure_needs_subcomposition` 경고가 남는다. 작은 예제의 단일 편집 그룹을 유지했다. 오류가 없다는 결과를 모든 경고 없음으로 보고하지 않는다.
- 첫 HTML의 doctype 앞 주석 때문에 HF StaticGuard가 실패했다. doctype을 첫 줄로 수정한 뒤 재검사했다.
- 시스템 NanumGothic.ttf는 Chrome의 `OTS parsing error: TSI3: zero-length table`로 거부됐다. 실패 렌더/Studio 오류를 보존하고 정상 로드된 로컬 NanumBarunGothic으로 새 버전을 렌더했다.
- 없는 font URL은 실제 HF check에서 http_error/request_failed로 실패했다.
- 의도적으로 nowrap/좁은 폭의 긴 제목을 만든 별도 예제를 검수했다. 기술 결과와 실제 프레임을 구분하며 일반적인 모든 텍스트 잘림 검출을 보증하지 않는다.
- Remotion의 제한된 FFmpeg 빌드로 HF 음성 믹스를 시도하면 muxer 부재로 실패했다. `--strict`가 무음 결과의 성공 처리를 거부했다. 공식 Ubuntu FFmpeg를 관리자 설치 없이 임시 경로에 추출해 새 출력 경로에서 재시도했다.
- 개발 회귀는 시간별 문구 위반, 누락/경로 밖 자산, NaN/불완전 규격, 음원 없음/길이 부족/미승인 겹침, stream/FPS/프레임 수 위반, 도구 없음 및 기존 보고서/영상 보존을 확인한다.

`npm test`, `python3 tests/review-check.py`, native build와 `git diff --check`가 통과했다. 기존 공통 설치 계획에 영상 도구가 없음을 검사했다.
실제 렌더 강제 중단, 다른 OS/호스트, 소스 번역, alpha/HDR 합성, 사용자 청취/미적 수락은 not_run이다.

## 보관과 재현

현재 로컬 결과는 개발 레포의 `.local/motion-issue8/`에 보존한다. 임시 캐시만으로 전달하지 않는다.
코드/lock·public 음원/글꼴/GSAP·spec·원본 및 수정 영상·실패 로그·검사 JSON·대표 프레임·재렌더 결과가 있다.
이 경로는 테스트 바이너리 보관용으로 Git에서 제외한다. 공유가 필요하면 이 자료를 프로젝트 자산 정책에 따라 함께 전달한다.
커밋되는 예제 코드는 `tests/motion-example/`이며 새 환경에서는 README에 따라 허가된 실제 자산을 준비한다.

- 무음: `.local/motion-issue8/renders/v01/motion.mp4`
- HF 내레이션: `.local/motion-issue8/renders/v02/general-intro.mp4`
- 두 도구 합성: `.local/motion-issue8/renders/v03/intro.mp4`
- 재렌더: `.local/motion-issue8/rerender/renders/v01/intro.mp4`
- 최종 검사/음성/프레임: `.local/motion-issue8/qa/v03/`, 재렌더 비교 `qa/rerender-comparison.json`
- 미리보기: HF `http://localhost:3418/#project/motion-issue8`, Remotion `http://localhost:3419/Intro` (서버가 실행 중일 때)

재현 명령과 source→clip→합성 대응은 예제 README, 실제 세부 metadata는 `docs/evidence/motion-issue8.json`에 있다.
툴과 자산 라이선스는 연결 스킬의 toolchain과 예제 README를 읽는다. 원문 스킬은 복사해 배포하지 않는다.
