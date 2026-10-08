"""로컬 렌더 파일의 규격·필수 자산·계획된 텍스트/음성 구간을 검사한다. 설치/렌더는 하지 않는다."""
import argparse
from array import array
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

COLOR_KEYS = ('color_range', 'color_space', 'color_transfer', 'color_primaries')
SAMPLE_RATE = 8000


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name}: finite number required')
    if value < 0 or (positive and value == 0):
        raise ValueError(f'{name}: invalid range')
    return value


def interval(item, duration):
    start, end = number(item['start'], 'start'), number(item['end'], 'end', True)
    if start >= end or end > duration:
        raise ValueError('interval outside duration or empty')
    return start, end


def asset(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('asset path must be relative to spec')
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f'asset missing, empty or outside spec directory: {name}')
    return path


def validate(spec, root):
    for key in ('width', 'height'):
        value = number(spec[key], key, True)
        if not isinstance(value, int):
            raise ValueError(f'{key}: integer required')
    fps = number(spec['fps'], 'fps', True)
    duration = number(spec['duration'], 'duration', True)
    for key in COLOR_KEYS:
        if not isinstance(spec[key], str) or spec[key] in ('', 'unknown', 'unspecified'):
            raise ValueError(f'{key}: explicit color property required')
    if abs(duration * fps - round(duration * fps)) > 1e-6:
        raise ValueError('duration must contain a whole number of frames')
    if spec['audio'] not in ('none', 'required'):
        raise ValueError('audio must be none or required')
    if not isinstance(spec.get('allow_audio_overlap', False), bool):
        raise ValueError('allow_audio_overlap must be boolean')
    policies = spec['text_policy']
    if not isinstance(policies, list) or not policies:
        raise ValueError('text_policy required')
    cursor = 0
    for policy in policies:
        start, end = interval(policy, duration)
        if start != cursor or not isinstance(policy['allow'], list):
            raise ValueError('text_policy must cover duration without gaps/overlap')
        if not all(isinstance(text, str) for text in policy['allow']):
            raise ValueError('text_policy allow must contain strings')
        cursor = end
    if cursor != duration:
        raise ValueError('text_policy must cover duration')
    for text in spec['texts']:
        start, end = interval(text, duration)
        if not isinstance(text['text'], str):
            raise ValueError('text must be a string')
        for policy in policies:
            if start < policy['end'] and end > policy['start'] and text['text'] not in policy['allow']:
                raise ValueError('planned text violates interval policy')
    for path in spec['assets']:
        asset(root, path)
    clips = spec['audio_clips']
    if (spec['audio'] == 'none' and clips) or (spec['audio'] == 'required' and not clips):
        raise ValueError('audio clips contradict audio requirement')
    spans = []
    for clip in clips:
        asset(root, clip['path'])
        start = number(clip['start'], 'audio start')
        length = number(clip['duration'], 'audio duration', True)
        if start + length > duration:
            raise ValueError('audio tail exceeds video duration')
        spans.append((start, start + length))
    if not spec.get('allow_audio_overlap', False):
        spans.sort()
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            raise ValueError('unapproved audio overlap')


def probe(executable, path, frames=False):
    command = [executable, '-v', 'error', '-count_frames', '-show_streams', '-show_format']
    if frames:
        command += ['-show_frames', '-show_entries', 'frame=media_type,best_effort_timestamp_time']
    result = subprocess.run(command + ['-of', 'json', str(path)],
                            capture_output=True, text=True, timeout=180, check=True)
    return json.loads(result.stdout)


def inspect(spec, metadata, audio_metadata):
    failures = []
    video = [s for s in metadata['streams'] if s['codec_type'] == 'video']
    audio = [s for s in metadata['streams'] if s['codec_type'] == 'audio']
    if len(video) != 1:
        return ['expected exactly one video stream']
    stream = video[0]
    for key in ('width', 'height') + COLOR_KEYS:
        if stream.get(key) != spec[key]:
            failures.append(f'{key} mismatch')
    fps = float(Fraction(stream['avg_frame_rate']))
    if not math.isfinite(fps) or abs(fps - spec['fps']) > 1e-6:
        failures.append('fps mismatch')
    if int(stream['nb_read_frames']) != round(spec['duration'] * spec['fps']):
        failures.append('frame count mismatch')
    timestamps = [float(frame['best_effort_timestamp_time']) for frame in metadata['frames']
                  if frame['media_type'] == 'video']
    tolerance = max(1e-6, float(Fraction(stream['time_base'])) / 2 + 1e-6)
    if len(timestamps) != round(spec['duration'] * spec['fps']) or any(
            not math.isfinite(stamp) or abs(stamp - index / spec['fps']) > tolerance
            for index, stamp in enumerate(timestamps)):
        failures.append('nonconstant frame cadence or nonzero video start')
    actual_duration = float(stream.get('duration', metadata['format']['duration']))
    if not math.isfinite(actual_duration) or abs(actual_duration - spec['duration']) > 1 / spec['fps']:
        failures.append('video duration mismatch')
    if (spec['audio'] == 'required' and len(audio) != 1) or (spec['audio'] == 'none' and audio):
        failures.append('audio stream requirement mismatch')
    for clip, source in zip(spec['audio_clips'], audio_metadata):
        streams = [s for s in source['streams'] if s['codec_type'] == 'audio']
        if not streams:
            failures.append(f'no source audio stream: {clip["path"]}')
            continue
        source_duration = float(streams[0].get('duration', source['format']['duration']))
        if not math.isfinite(source_duration) or source_duration + 0.01 < clip['duration']:
            failures.append(f'source audio too short: {clip["path"]}')
    if audio and spec['audio_clips']:
        tail = max(c['start'] + c['duration'] for c in spec['audio_clips'])
        end = float(audio[0].get('start_time', 0)) + float(audio[0].get('duration', metadata['format']['duration']))
        if not math.isfinite(end) or end + 0.05 < tail:
            failures.append('output audio ends before planned tail')
    return failures


def decode_audio(executable, path, duration):
    result = subprocess.run([executable, '-v', 'error', '-nostdin', '-copyts', '-i', str(path),
        '-map', '0:a:0', '-t', str(duration), '-af', f'aresample={SAMPLE_RATE}:async=1:first_pts=0',
        '-ac', '1', '-ar', str(SAMPLE_RATE), '-f', 'f32le', '-'],
        capture_output=True, timeout=180, check=True)
    samples = array('f')
    samples.frombytes(result.stdout)
    if sys.byteorder != 'little':
        samples.byteswap()
    if not samples or any(not math.isfinite(value) for value in samples):
        raise ValueError('decoded audio missing or nonfinite')
    return samples


def inspect_audio(spec, rendered, sources):
    expected = [0.0] * round(spec['duration'] * SAMPLE_RATE)
    if len(sources) != len(spec['audio_clips']):
        raise ValueError('decoded source count mismatch')
    for clip, samples in zip(spec['audio_clips'], sources):
        start = round(clip['start'] * SAMPLE_RATE)
        count = round((clip['start'] + clip['duration']) * SAMPLE_RATE) - start
        if len(samples) < count - 1:
            return [f'decoded source audio too short: {clip["path"]}']
        for index, value in enumerate(samples[:count]):
            expected[start + index] += value
    # ponytail: unity-gain mono mixes only; use separate QA for fades, spatial audio or processed voices.
    for start in range(0, len(expected), SAMPLE_RATE // 4):
        reference = expected[start:start + SAMPLE_RATE // 4]
        actual = list(rendered[start:start + len(reference)])
        actual += [0.0] * (len(reference) - len(actual))
        power = sum(value * value for value in reference)
        error = sum((left - right) ** 2 for left, right in zip(reference, actual))
        if error > max(power * 0.04, len(reference) * 1e-6):
            return [f'rendered audio differs from planned mix at {start / SAMPLE_RATE:.2f}s']
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--ffprobe', default='ffprobe')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.out.is_symlink():
        parser.error('output already exists; choose a new attempt path')
    report = {'status': 'unavailable', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'media': str(args.media), 'spec': str(args.spec), 'failures': [],
              'visual': 'not_run', 'content': 'not_run', 'listening': 'not_run',
              'audio_content': 'not_run', 'frame_cadence': 'not_run', 'color_properties': 'not_run'}
    code = 2
    try:
        raw = args.spec.read_bytes()
        spec = json.loads(raw)
        validate(spec, args.spec.resolve().parent)
        if not args.media.is_file() or args.media.stat().st_size == 0:
            raise ValueError('media missing or empty')
        report['spec_sha256'] = hashlib.sha256(raw).hexdigest()
        report['ffprobe_version'] = subprocess.run([args.ffprobe, '-version'], capture_output=True,
            text=True, timeout=10, check=True).stdout.splitlines()[0]
        report['metadata'] = probe(args.ffprobe, args.media, frames=True)
        sources = [probe(args.ffprobe, asset(args.spec.resolve().parent, clip['path']))
                   for clip in spec['audio_clips']]
        report['audio_metadata'] = sources
        report['failures'] = inspect(spec, report['metadata'], sources)
        if len([s for s in report['metadata']['streams'] if s['codec_type'] == 'video']) == 1:
            report['frame_cadence'] = 'failed' if any('cadence' in f for f in report['failures']) else 'passed'
            report['color_properties'] = 'failed' if any(
                f'{key} mismatch' in report['failures'] for key in COLOR_KEYS) else 'passed'
        if spec['audio'] == 'required' and not report['failures']:
            report['ffmpeg_version'] = subprocess.run([args.ffmpeg, '-version'], capture_output=True,
                text=True, timeout=10, check=True).stdout.splitlines()[0]
            rendered = decode_audio(args.ffmpeg, args.media, spec['duration'])
            decoded = [decode_audio(args.ffmpeg, asset(args.spec.resolve().parent, clip['path']),
                                   clip['duration']) for clip in spec['audio_clips']]
            audio_failures = inspect_audio(spec, rendered, decoded)
            report['audio_content'] = 'failed' if audio_failures else 'passed'
            report['failures'].extend(audio_failures)
        elif spec['audio'] == 'none':
            report['audio_content'] = 'not_applicable'
        code = int(bool(report['failures']))
        report['status'] = 'failed' if code else 'passed'
    except (OSError, ValueError, KeyError, TypeError, IndexError, ZeroDivisionError, subprocess.SubprocessError) as error:
        report['reason'] = f'{type(error).__name__}: {error}'
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves prior attempts, including a concurrent writer.
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write('\n')
    print(f'{report["status"]}: {args.out}')
    return code


if __name__ == '__main__':
    sys.exit(main())
