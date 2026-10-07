"""선택형 영상 검사의 실패·미확인·구간 정책과 기존 증거 보존을 확인한다."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import deps
sys.path.insert(0, str(ROOT / 'tests'))
import motion_check as motion


def rejected(spec, root):
    try:
        motion.validate(spec, root)
    except (ValueError, KeyError, TypeError):
        return
    raise AssertionError('invalid spec accepted')


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'voice.wav').write_bytes(b'local asset')
    spec = {'width': 1280, 'height': 720, 'fps': 30, 'duration': 15, 'audio': 'required',
            'assets': ['voice.wav'], 'audio_clips': [{'path': 'voice.wav', 'start': 0.5, 'duration': 4}],
            'texts': [{'start': 13, 'end': 15, 'text': '함께 만드는 모션'}],
            'text_policy': [{'start': 0, 'end': 13, 'allow': []},
                            {'start': 13, 'end': 15, 'allow': ['함께 만드는 모션']}]}
    motion.validate(spec, root)
    for change in ({'fps': float('nan')}, {'duration': 14.99}, {'audio_clips': []},
                   {'assets': ['missing-font.ttf']}, {'assets': ['../escape.ttf']},
                   {'assets': [str(root / 'voice.wav')]}, {'allow_audio_overlap': 'false'},
                   {'texts': [{'start': 12.9, 'end': 15, 'text': '함께 만드는 모션'}]},
                   {'text_policy': [{'start': 1, 'end': 15, 'allow': []}]},
                   {'audio_clips': [{'path': 'voice.wav', 'start': 14, 'duration': 2}]},
                   {'audio_clips': [{'path': 'voice.wav', 'start': 0, 'duration': 4},
                                    {'path': 'voice.wav', 'start': 2, 'duration': 4}]}):
        rejected({**spec, **change}, root)
    metadata = {'format': {'duration': '15'}, 'streams': [
        {'codec_type': 'video', 'width': 1280, 'height': 720, 'avg_frame_rate': '30/1',
         'nb_read_frames': '450', 'duration': '15'},
        {'codec_type': 'audio', 'duration': '15'}]}
    source = {'format': {'duration': '4'}, 'streams': [{'codec_type': 'audio', 'duration': '4'}]}
    assert motion.inspect(spec, metadata, [source]) == []
    for key, value in (('width', 640), ('avg_frame_rate', '24/1'), ('nb_read_frames', '449'), ('duration', '14')):
        bad = deepcopy(metadata)
        bad['streams'][0][key] = value
        assert motion.inspect(spec, bad, [source])
    bad = deepcopy(metadata)
    bad['streams'].pop()
    assert 'audio stream requirement mismatch' in motion.inspect(spec, bad, [source])
    bad = deepcopy(source)
    bad['streams'][0]['duration'] = '3'
    assert any('too short' in f for f in motion.inspect(spec, metadata, [bad]))

    spec_path = root / 'spec.json'
    spec_path.write_text(json.dumps(spec))
    media = root / 'video.mp4'
    media.write_bytes(b'prior successful render')
    output = root / 'qa/v01/result.json'
    cmd = [sys.executable, str(ROOT / 'tests/motion_check.py'), '--spec', str(spec_path),
           '--media', str(media), '--ffprobe', str(root / 'missing-ffprobe'), '--out', str(output)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    assert done.returncode == 2, done.stderr
    report = json.loads(output.read_text())
    assert report['status'] == 'unavailable' and report['listening'] == 'not_run'
    previous = output.read_bytes()
    assert subprocess.run(cmd, capture_output=True).returncode == 2
    assert output.read_bytes() == previous and media.read_bytes() == b'prior successful render'

# Common install plans must remain independent of video tools on every host.
for host in ('codex', 'claude-code', 'grok', 'agy', 'all'):
    plan = list(deps.commands(host))
    assert not any('hyperframes' in ' '.join(c) or 'remotion' in ' '.join(c) for c in plan)
print('PASS: motion policy/assets/audio/spec/stream failures, unavailable tools, prior evidence, optional dependencies')
