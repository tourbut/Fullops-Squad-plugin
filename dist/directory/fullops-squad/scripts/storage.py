"""증거와 설정을 같은 디렉터리의 임시 파일로 쓰고 원자적으로 교체한다."""
import json
import os
from pathlib import Path
import tempfile


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode('utf-8') if isinstance(data, str) else data
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def write_many(changes):
    """다중 파일 쓰기 실패 시 원본을 복원한다. 프로세스 강제 종료 복구는 호출자의 journal이 맡는다."""
    originals = {Path(path): Path(path).read_bytes() if Path(path).exists() else None for path in changes}
    written = []
    try:
        for path, data in changes.items():
            atomic_write(path, data)
            written.append(Path(path))
    except Exception:
        for path in reversed(written):
            if originals[path] is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, originals[path])
        raise
