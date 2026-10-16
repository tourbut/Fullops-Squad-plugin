"""Install a persistent hook runtime; dispatch without the host's versioned cache."""
import hashlib
import json
from pathlib import Path
import re
import runpy
import sys
import tempfile
import uuid

HOOKS = {'caveman_start', 'done_gate', 'flow_gate', 'issue_mode'}


def runtime_root():
    return Path.home() / '.fullops-squad/runtime/fullops-squad'


def package_files(package):
    files = {p.relative_to(package).as_posix(): p.read_bytes() for p in package.rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    if 'dependencies.json' not in files:
        files['dependencies.json'] = (package.parents[1] / 'dependencies.json').read_bytes()
    return files


def content_key(files):
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        digest.update(name.encode() + b'\0' + hashlib.sha256(data).digest())
    return digest.hexdigest()


def in_place(package):
    """The directory edition runs hooks from its own folder through hooks/run.sh and needs no runtime."""
    return (Path(package) / 'hooks/run.sh').is_file()


def problems(package):
    if in_place(package):
        return []
    try:
        root = runtime_root()
        current = json.loads((root / 'current.json').read_text(encoding='utf-8'))
        expected = json.loads((Path(package) / 'plugin.json').read_text(encoding='utf-8'))
        key = current['package']
        if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
            raise ValueError('Invalid runtime package')
        if current['version'] != expected['version'] or not (root / 'scripts/hook_runtime.py').is_file():
            raise ValueError('Hook runtime differs from installed plugin')
        if any(not (root / 'packages' / key / 'scripts' / (name + '.py')).is_file() for name in HOOKS):
            raise ValueError('Incomplete runtime')
        expected_key = content_key(package_files(Path(package)))
        if (current.get('sha256') != expected_key or
                content_key(package_files(root / 'packages' / key)) != expected_key):
            raise ValueError('Hook runtime content differs from installed plugin')
        return []
    except (OSError, ValueError, KeyError, TypeError):
        return ['hook runtime missing or outdated; run installed scripts/deps.py --runtime-only']


def install(package):
    from storage import write_many

    package = Path(package).resolve()
    if in_place(package):
        return package  # Nothing is written outside the plugin folder.
    manifest = json.loads((package / 'plugin.json').read_text(encoding='utf-8'))
    if manifest.get('name') != 'fullops-squad':
        raise ValueError('FullOps package required for hook runtime')
    files = package_files(package)
    for name in HOOKS:
        if f'scripts/{name}.py' not in files:
            raise ValueError(f'Missing hook script: {name}')
    digest = content_key(files)
    key = digest
    root = runtime_root()
    packages = root / 'packages'
    packages.mkdir(parents=True, exist_ok=True)
    target = packages / key
    if target.exists():
        try:
            intact = content_key(package_files(target)) == digest
        except (OSError, ValueError):
            intact = False
        if not intact:
            # Publish a fresh location; never remove a snapshot a running hook may use.
            key = hashlib.sha256((digest + uuid.uuid4().hex).encode()).hexdigest()
            target = packages / key
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix='.stage-', dir=packages) as temp:
            stage = Path(temp) / 'package'
            for name, data in files.items():
                dest = stage / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            try:
                stage.rename(target)
            except OSError:
                if not target.is_dir():
                    raise
    # Running hooks retain their complete snapshot across cache removal or updates.
    write_many({root / 'scripts/hook_runtime.py': files['scripts/hook_runtime.py'],
                root / 'current.json': json.dumps({'package': key, 'sha256': digest,
                                                  'version': manifest['version']}) + '\n'})
    return root


def run():
    root = Path(__file__).resolve().parents[1]
    current = json.loads((root / 'current.json').read_text(encoding='utf-8'))
    key = current['package']
    if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
        raise ValueError('Invalid hook runtime package')
    name = sys.argv[1] if len(sys.argv) > 1 else ''
    if name not in HOOKS:
        raise ValueError('Unknown FullOps hook')
    script = root / 'packages' / key / 'scripts' / (name + '.py')
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script), *sys.argv[2:]]
    runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    run()
