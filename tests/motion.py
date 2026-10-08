"""선택형 영상 검사의 실패·미확인·구간 정책과 기존 증거 보존을 확인한다."""
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from unittest.mock import patch
import wave

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
            'color_range': 'tv', 'color_space': 'bt709', 'color_transfer': 'bt709', 'color_primaries': 'bt709',
            'assets': ['voice.wav'], 'audio_clips': [{'path': 'voice.wav', 'start': 0.5, 'duration': 4}],
            'texts': [{'start': 13, 'end': 15, 'text': '함께 만드는 모션'}],
            'text_policy': [{'start': 0, 'end': 13, 'allow': []},
                            {'start': 13, 'end': 15, 'allow': ['함께 만드는 모션']}]}
    motion.validate(spec, root)
    for change in ({'fps': float('nan')}, {'duration': 14.99}, {'audio_clips': []}, {'color_space': 'unknown'},
                   {'assets': ['missing-font.ttf']}, {'assets': ['../escape.ttf']},
                   {'assets': [str(root / 'voice.wav')]}, {'allow_audio_overlap': 'false'},
                   {'texts': [{'start': 12.9, 'end': 15, 'text': '함께 만드는 모션'}]},
                   {'text_policy': [{'start': 1, 'end': 15, 'allow': []}]},
                   {'audio_clips': [{'path': 'voice.wav', 'start': 14, 'duration': 2}]},
                   {'audio_clips': [{'path': 'voice.wav', 'start': 0, 'duration': 4},
                                    {'path': 'voice.wav', 'start': 2, 'duration': 4}]}):
        rejected({**spec, **change}, root)
    metadata = {'format': {'duration': '15'}, 'frames': [
        {'media_type': 'video', 'best_effort_timestamp_time': str(index / 30)} for index in range(450)], 'streams': [
        {'codec_type': 'video', 'width': 1280, 'height': 720, 'avg_frame_rate': '30/1',
         'nb_read_frames': '450', 'duration': '15', 'time_base': '1/15360',
         **{key: spec[key] for key in motion.COLOR_KEYS}},
        {'codec_type': 'audio', 'duration': '15'}]}
    source = {'format': {'duration': '4'}, 'streams': [{'codec_type': 'audio', 'duration': '4'}]}
    assert motion.inspect(spec, metadata, [source]) == []
    for key in motion.COLOR_KEYS:
        bad = deepcopy(metadata)
        bad['streams'][0][key] = 'unknown'
        assert f'{key} mismatch' in motion.inspect(spec, bad, [source])
        del bad['streams'][0][key]
        assert f'{key} mismatch' in motion.inspect(spec, bad, [source])
    bad = deepcopy(metadata)
    bad['frames'][100]['best_effort_timestamp_time'] = str(100 / 30 + 0.01)
    assert any('cadence' in f for f in motion.inspect(spec, bad, [source]))
    bad['frames'][100]['best_effort_timestamp_time'] = 'nan'
    assert any('cadence' in f for f in motion.inspect(spec, bad, [source]))
    bad = deepcopy(metadata)
    bad['streams'][0]['time_base'] = '1/30'
    assert motion.inspect(spec, bad, [source]) == []
    bad['frames'][100]['best_effort_timestamp_time'] = str(101 / 30)
    assert any('cadence' in f for f in motion.inspect(spec, bad, [source]))
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

    signal = [0.25 * math.sin(index * 0.11) for index in range(4 * motion.SAMPLE_RATE)]
    rendered = [0.0] * (15 * motion.SAMPLE_RATE)
    offset = round(0.5 * motion.SAMPLE_RATE)
    rendered[offset:offset + len(signal)] = signal
    assert motion.inspect_audio(spec, rendered, [signal]) == []
    assert motion.inspect_audio(spec, rendered[:offset + len(signal)], [signal]) == []
    for bad in ([0.0] * len(rendered), [0.0] * 800 + rendered[:-800],
                rendered[:offset + 16000] + [0.0] * (len(rendered) - offset - 16000),
                [-value for value in rendered], rendered[:offset + 16000]):
        assert motion.inspect_audio(spec, bad, [signal])
    assert motion.inspect_audio(spec, rendered, [signal[:16000]])
    with patch.object(sys, 'argv', ['motion_check.py', '--spec', str(spec_path), '--media', str(media),
                                  '--out', str(root / 'decode-unavailable.json')]), \
         patch.object(motion, 'probe', side_effect=[metadata, source]), \
         patch.object(motion.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'tool version\n')), \
         patch.object(motion, 'decode_audio', side_effect=FileNotFoundError('missing decoder')):
        assert motion.main() == 2
    assert json.loads((root / 'decode-unavailable.json').read_text())['audio_content'] == 'not_run'

    # Optional real codec regression; the standard suite has no video-tool dependency.
    if shutil.which('ffmpeg') and shutil.which('ffprobe'):
        pcm = root / 'source.wav'
        samples = [int(8000 * math.sin(2 * math.pi * (300 * i / 8000 + 200 * (i / 8000) ** 2)))
                   for i in range(8000)]
        with wave.open(str(pcm), 'wb') as audio:
            audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            audio.writeframes(struct.pack(f'<{len(samples)}h', *samples))
        small = {**spec, 'width': 64, 'height': 64, 'fps': 10, 'duration': 2,
                 'assets': ['source.wav'], 'audio_clips': [{'path': 'source.wav', 'start': 0.5, 'duration': 1}],
                 'texts': [], 'text_policy': [{'start': 0, 'end': 2, 'allow': []}]}
        small_path = root / 'small.json'
        small_path.write_text(json.dumps(small))
        base = ['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:r=10:d=2',
                '-i', str(pcm), '-filter_complex', '[1:a]adelay=500:all=1,apad[a]', '-map', '0:v', '-map', '[a]',
                '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-color_range', 'tv', '-colorspace', 'bt709',
                '-color_trc', 'bt709', '-color_primaries', 'bt709',
                '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709:fullrange=off', '-c:a', 'aac']
        for label, audio_filter, change, expected_code in (
                ('valid', '', [], 0), ('tail-only', ',atrim=duration=1.5', [], 0), ('silent', ',volume=0', [], 1),
                ('shifted', ',adelay=200:all=1', [], 1),
                ('truncated', ",volume=0:enable='gte(t,1)'", [], 1),
                ('wrong-color', '', ['-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=smpte170m:fullrange=off'], 1),
                ('vfr', '', ['-vf', "settb=1/1000,setpts='PTS+if(mod(N,2),0.02,0)/TB'",
                         '-enc_time_base', '1:1000', '-fps_mode', 'passthrough'], 1)):
            video = root / f'{label}.mp4'
            command = base.copy()
            command[command.index('-filter_complex') + 1] = f'[1:a]adelay=500:all=1,apad{audio_filter}[a]'
            created = subprocess.run(command + change + [str(video)], capture_output=True, text=True)
            assert created.returncode == 0, created.stderr
            report_path = root / f'{label}-qa.json'
            checked = subprocess.run([sys.executable, str(ROOT / 'tests/motion_check.py'), '--spec', str(small_path),
                                      '--media', str(video), '--out', str(report_path)], capture_output=True, text=True)
            report = json.loads(report_path.read_text())
            assert checked.returncode == expected_code, (label, checked.stderr, report)
            if label == 'vfr':
                assert report['frame_cadence'] == 'failed', report
        print('PASS: real AAC/CFR, missing/shifted/truncated narration, color mismatch and VFR rejection')
    else:
        print('not_run: optional FFmpeg/FFprobe codec regression (tools unavailable)')

# Common install plans must remain independent of video tools on every host.
for host in ('codex', 'claude-code', 'grok', 'agy', 'all'):
    plan = list(deps.commands(host))
    assert not any('hyperframes' in ' '.join(c) or 'remotion' in ' '.join(c) for c in plan)
print('PASS: motion policy/assets/audio/spec/stream failures, unavailable tools, prior evidence, optional dependencies')
