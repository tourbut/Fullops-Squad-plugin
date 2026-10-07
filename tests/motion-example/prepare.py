"""설치된 로컬 GSAP·허가된 한글 글꼴·로컬 TTS로 선택형 예제 자산을 준비한다."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import wave

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--font', type=Path, required=True, help='licensed NanumBarunGothic.ttf')
parser.add_argument('--voice-executable', required=True, help='existing espeak-ng executable')
args = parser.parse_args()
root = Path(__file__).resolve().parent
public = root / 'public'
public.mkdir(exist_ok=True)
for source, name in ((args.font, 'NanumBarunGothic.ttf'),
                     (root / 'node_modules/gsap/dist/gsap.min.js', 'gsap.min.js')):
    target = public / name
    if target.exists():
        raise SystemExit(f'preserve existing asset: {target}')
    if not source.is_file():
        raise SystemExit(f'missing asset: {source}')
    shutil.copyfile(source, target)
voice = public / 'narration.wav'
if voice.exists():
    raise SystemExit('preserve existing narration')
subprocess.run([args.voice_executable, '-v', 'en-us', '-s', '155', '-w', str(voice),
                'Motion connects ideas. Build scenes, test timing, and share editable sources.'], check=True)
with wave.open(str(voice)) as audio:
    duration = audio.getnframes() / audio.getframerate()
common = {'width': 1280, 'height': 720, 'fps': 30, 'assets': ['public/gsap.min.js']}
silent = {**common, 'duration': 6, 'audio': 'none', 'audio_clips': [], 'texts': [],
          'text_policy': [{'start': 0, 'end': 6, 'allow': []}]}
intro = {**common, 'duration': 15, 'audio': 'required',
         'assets': ['public/NanumBarunGothic.ttf', 'public/gsap.min.js'],
         'audio_clips': [{'path': 'public/narration.wav', 'start': 0.5, 'duration': duration}],
         'texts': [{'start': 13, 'end': 15, 'text': '함께 만드는 모션'}],
         'text_policy': [{'start': 0, 'end': 13, 'allow': []},
                         {'start': 13, 'end': 15, 'allow': ['함께 만드는 모션']}]}
for name, spec in (('silent-spec.json', silent), ('intro-spec.json', intro)):
    with (root / name).open('x', encoding='utf-8') as output:
        json.dump(spec, output, ensure_ascii=False, indent=2)
        output.write('\n')
print(f'prepared local assets; narration {duration:.3f}s; listening not_run')
shutil.copytree(public, root / 'general/public')
