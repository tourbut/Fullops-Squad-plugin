# 공식 스킬 참조와 로컬 실행

2026-10-07 검토 기준. 실행한 환경과 한계는 개발 저장소 `docs/motion-graphics.md`에 기록한다. 이것은 전 OS/CPU 지원 보증이 아니다.

| 구성 | 고정 기준 | 공식 원천 |
|---|---|---|
| HyperFrames CLI | `hyperframes@0.8.139`, Node >=22 | [공식 저장소](https://github.com/heygen-com/hyperframes/tree/e6daed3df04d9b9373601e4293018ffa09023144) |
| HyperFrames 스킬 | `e6daed3df04d9b9373601e4293018ffa09023144` (`v0.8.139`) | [진입 스킬](https://github.com/heygen-com/hyperframes/blob/e6daed3df04d9b9373601e4293018ffa09023144/skills/hyperframes/SKILL.md) |
| Remotion CLI/패키지 | `4.0.533`, 모든 `remotion`/`@remotion/*` 버전 일치 | [CLI](https://www.remotion.dev/docs/cli), [공식 스킬](https://www.remotion.dev/docs/ai/skills) |
| Remotion 스킬 | `473352613039e718e46655a26df224851e84c4aa` | [진입 스킬](https://github.com/remotion-dev/skills/blob/473352613039e718e46655a26df224851e84c4aa/skills/remotion-best-practices/SKILL.md) |

## 기존 로컬 환경 확인

1. 영상 폴더의 package/lock와 로컬 실행 파일을 먼저 확인한다. Node·브라우저·FFmpeg/FFprobe 버전·OS/CPU를 기록한다. HyperFrames는 `--version`, Remotion은 `versions`로 실제 설치를 확인한다. `npx`의 자동 다운로드로 존재 검사를 대신하지 않는다.
2. 같은 버전이면 재설치하지 않는다. 기존 작업의 다른 버전은 그대로 보존하고 별도 작업 폴더에서 호환 검증한다. 실행 중 프로젝트의 latest upgrade나 lock 교체를 하지 않는다.
3. 누락된 도구/스킬과 실행할 수 없는 검사를 보고한다. 도구·전역 스킬 설치나 갱신을 자동으로 실행하지 않는다. 환경 준비 요청이 있으면 설치 위치·고정 버전·구체적 명령과 기존 승인 범위를 확인해 별도로 수행한다.

설치된 공식 스킬에서 필요한 entry와 상대 참조를 읽는다. 출처/ref가 다르면 차이를 검토하고 기존 프로젝트를 보존한다. 원천 링크는 위 고정 commit을 기준으로 사용한다. 새 ref는 새 작업의 검토/검증 이후에만 적용한다. 전체 스킬 복사나 독자 포크 유지, 자동 skills update를 하지 않는다.

## 로컬 명령

공식 CLI의 해당 버전 `--help`와 스킬 참조를 읽고 실행한다. HyperFrames 0.8.139의 `--skip-skills`는 무시되므로 `HYPERFRAMES_SKIP_SKILLS=1`로 init의 자동 latest 스킬 조회를 막는다. 기본 blank의 외부 GSAP/font URL도 로컬 승인 자산으로 바꾼다. registry/add/capture는 별도의 네트워크 작업이다.

```bash
HYPERFRAMES_SKIP_SKILLS=1 DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes init clip --non-interactive --example blank --skill motion-graphics
# 내레이션은 --skill general-video
DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes preview clip --background
DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes check clip --snapshots --json
DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes render clip --strict --fps 30 --output renders/v01/clip.mp4
./node_modules/.bin/remotion studio src/index.jsx
./node_modules/.bin/remotion render src/index.jsx Intro renders/v01/intro.mp4
```

실제 브라우저와 ffmpeg가 PATH에 없다면 버전 CLI가 지원하는 실행 파일 옵션/환경 변수를 명시한다. HyperFrames: `HYPERFRAMES_BROWSER_PATH`, `HYPERFRAMES_FFMPEG_PATH`, `HYPERFRAMES_FFPROBE_PATH`. Remotion: `--browser-executable`. 실행 프로세스에만 적용하고 시스템 PATH는 바꾸지 않는다. 바이너리의 CPU/OS·codec 지원과 라이선스도 확인한다.

HyperFrames 0.8.139와 Remotion의 브라우저 실행에는 upstream 기본 `--no-sandbox` 동작이 있다. 로컬 신뢰 소스만 사용하고 해당 실행 경계를 기록한다. 프로젝트에서 sandbox 유지가 필수이면 실행을 보류하고 지원되는 격리 환경을 준비한다. FullOps가 추가 보안 해제 옵션이나 권한 상승을 자동 적용하지 않는다.

## 비용과 라이선스

HyperFrames는 [Apache-2.0](https://github.com/heygen-com/hyperframes/blob/e6daed3df04d9b9373601e4293018ffa09023144/LICENSE). 외부 스톡·글꼴·음성·클라우드의 권리는 별도다.

Remotion은 [4.0.533 라이선스](https://github.com/remotion-dev/remotion/blob/v4.0.533/LICENSE.md)의 사용 주체 조건을 확인한다. 개인, 직원 3명 이하 영리 조직, 비영리 조직 또는 아직 상업적으로 쓰지 않는 적합성 평가가 무료 대상이다. 그 밖의 조직은 Company License가 필요하다. 무료 전용인데 적합성이 불명확하면 Remotion 실행을 보류하며 자격이나 이미 보유한 라이선스를 확인한다. 로컬 렌더라는 이유로 무료라고 단정하지 않는다.

실행은 허가된 로컬 자산과 로컬 렌더로 제한한다. cloud/Lambda/Cloud Run, 외부 TTS/생성형 이미지, usage/feedback/publish 업로드를 실행하지 않는다. HyperFrames CLI는 프로세스에 `DO_NOT_TRACK=1`을 명시해 telemetry를 끈다. Remotion도 로컬 명령만 사용한다. 원문/오류/스크린샷에 키나 민감정보를 포함하지 않는다.
