---
name: fullops-motion
description: FullOps 활성 레포에서 코드 기반 모션그래픽 영상을 제작·수정·검수·인계할 때 사용한다. HyperFrames와 Remotion 공식 스킬을 선택하고 필요하면 렌더 클립으로 함께 사용한다.
---

# 모션그래픽 제작

사용자가 영상 산출물을 요청한 경우에만 진입한다. 일반 setup·개발·문서 작업에서는 영상 도구 설치·네트워크 조회·렌더를 실행하지 않는다.

## 1. 작업과 규격 확정

레포의 `.fullops-squad/fullops.json`, `FULLOPS.md`, 공통 규칙과 `project.md` 정본을 읽는다. 활성화가 없으면 `setup-fullops`를 안내한다. `fullops-work`의 현재 역할 인박스에 [작업 입력과 인계 항목](delivery.md)을 채우거나 원천 문서를 연결한다. 대화에서 이미 확정한 값과 승인 범위를 재사용하고, 합리적인 가정은 명시한다. 브랜드·권리·외부 전송·예산처럼 추정할 수 없는 항목만 질문한다.

기존 등록 역할과 모델 정책으로 제작·내용 검토·검수를 배정한다. art/tester가 없으면 등록 역할이 담당한다. upstream의 director·frame-worker 등은 제작 절차로 읽고 FullOps 역할 인박스·dispatch로 실행한다. 새 역할·상시 워크트리를 자동 생성하지 않는다. 동일 과제의 수정은 같은 키와 새 attempt/산출물 버전으로 이어가며 기존 보고·원본을 보존한다.

완료 조건: 구간별 텍스트·음성 정책, 파일 소유권, 비용/전송 허용 범위, 검사별 담당과 실제 산출물 경로가 기록됐다.

## 2. 엔진과 공식 스킬 선택

| 작업 | 사용할 공식 스킬 |
|---|---|
| 짧은 무내레이션 HTML 모션·타이포·도형 | HyperFrames `hyperframes` → `motion-graphics`, `hyperframes-core`, `hyperframes-animation`, `hyperframes-creative`, `hyperframes-cli` |
| 내레이션·긴 영상·여러 장면의 HyperFrames 구성 | `hyperframes` → `general-video` (제품 URL 기반 소개는 `product-launch-video`), core/creative/animation/cli와 오디오 규약 |
| React 소스·프레임 단위 애니메이션·클립 합성 | Remotion `remotion-best-practices` → `remotion-create`, `remotion-markup`, `remotion-studio`, `remotion-render`와 해당 참조 |
| 기존 Remotion 소스를 HTML로 옮기는 명시적 요청 | HyperFrames `remotion-to-hyperframes`; 번역 한계와 전후 프레임 검증을 기록 |

선택한 엔진만 준비한다. 두 도구가 필요하면 **HyperFrames 클립 렌더 → Remotion 미디어 클립 합성** 또는 역방향의 렌더 자산 전달로 연결한다. 각 소스와 입력→출력 대응을 보존하고 FPS·크기·길이·색 공간·알파·음성 소유권을 맞춘다. HTML에 React 컴포넌트를 붙이면 호환된다고 가정하지 않는다. 소스 번역은 자산 합성과 별도 작업이다.

선택 전에 [공식 스킬 참조와 로컬 실행](toolchain.md)을 읽는다. 설치된 공식 스킬의 출처/ref를 확인하고 해당 작업에 필요한 원문·참조를 읽는다. FullOps는 공식 스킬을 참고하는 연결만 제공한다. 제작·미리보기·렌더는 로컬 공식 도구를 직접 사용한다. upstream의 latest 갱신·자동 설치·외부 자산/TTS·usage/feedback/publish 지시는 실행하지 않는다.

완료 조건: 엔진·공식 스킬 ref·실제 설치 버전·라이선스 적합성·로컬 실행 가능 여부를 기록했다. 누락/불일치는 성공으로 처리하지 않았다.

## 3. 제작과 미리보기

프로젝트 자산 정책에 맞는 `videos/<작업>/` 등 영속 경로에서 공식 구성 규약으로 제작한다. 원천 HTML/React·음원·글꼴·이미지는 임시 캐시에만 남기지 않는다. 허가된 로컬 자산·사용자 음원/로컬 TTS·로컬 렌더를 사용한다. 클라우드 렌더·외부 생성 API·업로드/게시를 실행하지 않는다. 무료 전용에서 Remotion 라이선스 조건이 불명확하면 실행을 보류하고 가능한 로컬 대안을 제시한다.

HyperFrames는 framework 소유 미디어와 seek 가능한 타임라인을, Remotion은 `useCurrentFrame()` 기반 애니메이션과 명시적 clip timing을 따른다. 제작 초기에 공식 Studio/preview를 열고 출력 URL과 실제 프로젝트 로딩을 확인한다. 한글 글꼴은 실제 파일·glyph·로드 성공을 확인하며 누락 시 대체 승인을 받거나 실패로 기록한다.

완료 조건: 미리보기에서 각 장면·전환·문구·음성이 확인됐다. 사용자 표현 검토가 필요한 항목은 담당과 대기 상태를 기록했다.

## 4. 렌더와 검수

HyperFrames는 공식 `check --snapshots`의 `ok`, `browserSkipped`, runtime/layout/motion/contrast 결과와 스냅샷을 확인한다. Remotion은 공식 still/frames와 Studio에서 장면·전환을 검토한다. 기본값으로 빠진 검사는 미확인이다. 임의 Canvas/HTML에 CLI만 붙여 규약 검증으로 보고하지 않는다.

이미 승인된 MP4 제작·검증 렌더는 진행한다. 미리보기만 요청했거나 렌더 승인이 필요한 범위면 구체적인 미리보기 뒤 승인받는다. 실행마다 새 출력/증거 디렉터리를 사용하고 명령·종료코드·시간·실제 비용(모르면 unknown)을 보존한다. 중단·실패·수정 렌더는 이전 성공 파일을 덮어쓰지 않는다.

`fullops-test`의 `qa-reports/<과제 키>-test/`에 [검수와 인계](delivery.md)를 기록한다. 공식 CLI와 로컬 FFprobe/FFmpeg로 실제 출력 파일을 검사한다. 시각·내용·음질 수락은 별도다. 최종 프레임 추출·실제 음성 청취는 수행한 근거를 남기고 미실행은 `not_run`으로 기록한다.

완료 조건: 실제 결과 파일의 규격과 대표/경계/마지막 프레임, 구간 정책, 오디오/내용 검수의 근거·실패·미확인이 분리됐다.

## 5. 인계와 완료

최종 MP4·수정 가능한 코드·음원/자산·출처/라이선스·글꼴·대본/장면표·버전/lock·렌더 명령·미리보기·대표 프레임·검수 결과를 기존 산출물 문서에 연결한다. 필요한 파일은 프로젝트 보관 정책으로 전달하며 대형 바이너리 커밋을 강제하지 않는다.

다른 깨끗한 경로에서 전달한 소스와 자산으로 재렌더해 규격·프레임 시각/내용을 대조한다. MP4 바이트 동일성을 보장하지 않는다. 실행 불가와 미적/청취 검토 대기는 명시하고 전체 수락으로 올리지 않는다. `fullops-work`의 완료 보고·아카이브와 기존 리뷰/통합 절차를 따른다.

완료 조건: 대화·임시 캐시 없이 재렌더할 자료와 명령이 있으며 남은 검수·담당·재개 조건까지 인계됐다.
