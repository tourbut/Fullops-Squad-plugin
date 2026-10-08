"""설치된 로컬 GSAP·허가된 한글 글꼴·로컬 TTS로 선택형 예제 자산을 준비한다."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--font', type=Path, required=True, help='licensed NanumBarunGothic.ttf')
voice_source = parser.add_mutually_exclusive_group(required=True)
voice_source.add_argument('--voice-executable', help='existing espeak-ng executable')
voice_source.add_argument('--voice-file', type=Path, help='approved local WAV narration')
args = parser.parse_args()
root = Path(__file__).resolve().parent
public = root / 'public'
public.mkdir(exist_ok=True)
assets = ((args.font, 'NanumBarunGothic.ttf'),
          (root / 'node_modules/gsap/dist/gsap.min.js', 'gsap.min.js'))
for source, name in assets:
    target = public / name
    if target.exists():
        raise SystemExit(f'preserve existing asset: {target}')
    if not source.is_file():
        raise SystemExit(f'missing asset: {source}')
voice = public / 'narration.wav'
if voice.exists():
    raise SystemExit('preserve existing narration')
with tempfile.TemporaryDirectory(prefix='fullops-motion-voice-') as temporary:
    source_voice = args.voice_file or Path(temporary) / 'narration.wav'
    if not args.voice_file:
        subprocess.run([args.voice_executable, '-v', 'en-us', '-s', '155', '-w', str(source_voice),
                        'Motion connects ideas. Build scenes, test timing, and share editable sources.'], check=True)
    with wave.open(str(source_voice)) as audio:
        duration = audio.getnframes() / audio.getframerate()
    if not 0 < duration <= 14.5:
        raise SystemExit('narration must fit the 0.5–15s audio interval (0 < duration <= 14.5s)')
    for source, name in assets:
        shutil.copyfile(source, public / name)
    shutil.copyfile(source_voice, voice)
common = {'width': 1280, 'height': 720, 'fps': 30, 'assets': ['public/gsap.min.js'],
          'color_range': 'tv', 'color_space': 'bt709', 'color_transfer': 'bt709', 'color_primaries': 'bt709'}
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
