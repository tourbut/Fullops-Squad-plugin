# 두 엔진 모션그래픽 예제

일반 setup에서 실행하지 않는 선택형 검증 자료다. HyperFrames의 6초 무내레이션 모션을 Remotion의 15초 소개 영상에 합성한다. 처음 13초는 화면 텍스트 없이, 마지막 2초만 `함께 만드는 모션`이다. 음성은 직접 작성한 영문 대본의 로컬 eSpeak NG 합성으로 자연스러운 한국어 음성 예제가 아니다.

플러그인에 배포하지 않는 개발 검증 자료다. `fullops-motion`의 고정 도구/라이선스·설치 권한을 확인한 뒤 이 폴더를 프로젝트의 영속 영상 폴더로 복사한다. Node >=22, 지원 브라우저, FFmpeg/FFprobe, 허가된 `NanumBarunGothic.ttf`, 기존 `espeak-ng`가 필요하다. 선택한 작업에서는 실제 음원으로 교체해도 된다. 엔진과 외부 자산을 자동 설치하는 스크립트는 없다.

```bash
npm install
python3 prepare.py --font <NanumBarunGothic.ttf> --voice-executable <espeak-ng>
HYPERFRAMES_SKIP_SKILLS=1 DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes preview --background
DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes check --snapshots --json
DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes render --strict --fps 30 --workers 1 --output renders/v01/motion.mp4
cp renders/v01/motion.mp4 public/motion.mp4
DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes check general --snapshots --json
DO_NOT_TRACK=1 ./node_modules/.bin/hyperframes render general --strict --fps 30 --workers 1 --output renders/v01/general-intro.mp4
./node_modules/.bin/remotion studio src/index.jsx
./node_modules/.bin/remotion render src/index.jsx Intro renders/v01/intro.mp4
python3 <개발 저장소>/tests/motion_check.py --spec silent-spec.json --media renders/v01/motion.mp4 --out qa/v01/silent.json
python3 <개발 저장소>/tests/motion_check.py --spec intro-spec.json --media renders/v01/intro.mp4 --out qa/v01/intro.json
```

PATH에 없는 실행 파일은 `fullops-motion/toolchain.md`의 프로세스별 옵션을 명시한다. 렌더마다 새 `vNN`을 쓴다. source·package-lock·public 자산·spec·QA를 함께 전달하고 필요한 바이너리는 프로젝트의 보관 정책을 따른다. 다른 경로에서 `npm ci` 후 재렌더해 규격과 대표 프레임을 비교한다.

spec은 `color_range=tv`, `color_space/color_transfer/color_primaries=bt709`를 요구한다. 엔진별 실제 출력 속성을 확인하고 필요한 색 변환은 별도 버전으로 렌더한다. 태그만 바꿔 색 변환으로 보고하지 않는다. 기존 2026-10-07 Remotion 출력은 이 조건과 달라 새 검사에서 실패한다.

검사기는 FFprobe의 실제 프레임 시각을 확인하고, 음성이 있으면 FFmpeg로 원본과 출력을 8kHz mono PCM으로 디코드해 계획된 시작·길이의 unity-gain 합성과 0.25초 구간별로 비교한다. `--ffmpeg <실행 파일>`로 디코더를 지정할 수 있다. 가공 음성·fade·공간 음향은 이 비교의 범위 밖이며 별도 QA가 필요하다. 청취·시각 수락은 계속 별도다.

자산 기록:

- 도형·대본·한국어 문구·HTML/React/Python은 이 저장소의 예제 소스.
- GSAP 3.15.0은 공식 npm `gsap` 배포의 코드, [표준 라이선스](https://gsap.com/standard-license/).
- NanumGothic은 [공식 Nanum Fonts](https://github.com/naver/nanumfont), SIL Open Font License 1.1. 전달하는 파일의 출처·hash·라이선스 원문을 남긴다.
- eSpeak NG는 [공식 저장소](https://github.com/espeak-ng/espeak-ng), GPL-3.0-or-later 도구. 설치된 버전과 자체 대본의 합성 조건을 기록한다. 실제 청취가 없으면 음질 수락은 not_run.
- HyperFrames Apache-2.0, Remotion은 사용 주체별 라이선스. 예제 검증은 상업 사용 전 적합성 평가이며 일반 상업 프로젝트의 무료 자격을 보증하지 않는다.
