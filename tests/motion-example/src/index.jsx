// Compose the rendered HyperFrames clip with local speech and a Korean closing title.
import React from 'react';
import {AbsoluteFill, Composition, Sequence, registerRoot, staticFile, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Audio, Video} from '@remotion/media';
import {loadFont} from '@remotion/fonts';

loadFont({family: 'MotionKorean', url: staticFile('NanumBarunGothic.ttf')});

const Intro = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return <AbsoluteFill style={{backgroundColor: '#142032', fontFamily: 'MotionKorean'}}>
    <Video name="Opening" src={staticFile('motion.mp4')} durationInFrames={6 * fps} premountFor={fps} />
    <Video name="Repeat" src={staticFile('motion.mp4')} from={6 * fps} durationInFrames={6 * fps} premountFor={fps} />
    <Video name="Bridge" src={staticFile('motion.mp4')} from={12 * fps} durationInFrames={fps} premountFor={fps} />
    <Audio src={staticFile('narration.wav')} from={Math.round(0.5 * fps)} premountFor={fps} />
    <Sequence name="Closing" from={13 * fps} durationInFrames={2 * fps} premountFor={fps}>
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', color: '#ffffff'}}>
        <h1 style={{fontSize: 64, margin: 0, translate: `0px ${interpolate(frame, [13 * fps, 13.4 * fps], [32, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}px`}}>
          함께 만드는 모션
        </h1>
      </AbsoluteFill>
    </Sequence>
  </AbsoluteFill>;
};

const Root = () => <Composition id="Intro" component={Intro} width={1280} height={720} fps={30} durationInFrames={450} />;
registerRoot(Root);
