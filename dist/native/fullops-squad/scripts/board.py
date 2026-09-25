#!/usr/bin/env python3
"""작업 현황판 데이터(board/board-data.js)를 만든다. 단계는 coordinator가 쓴 board.json에서, 나머지는 레포 기록에서 모은다.

HTML을 파일로 열면 fetch로 JSON을 읽을 수 없어서 `window.FULLOPS_BOARD = {...}` 형태의 JS로 쓴다.
모델을 쓰지 않는 결정론적 스크립트라 Stop hook에서 매번 실행해도 비용이 없다.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess

from deliverables import meta_for

BOARD = '.fullops-squad/board'
STATUSES = ('done', 'active', 'blocked', 'todo')
TITLE = re.compile(r'^#\s+([A-Za-z0-9][A-Za-z0-9._-]*)\s+—\s+(.+?)\s*$', re.M)
SEPARATOR = re.compile(r'\|?[\s:|-]+\|?')


def read(path):
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def load(path):
    try:
        return json.loads(read(path))
    except ValueError:
        return None


def git(repo, *args):
    done = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, encoding='utf-8')
    return done.stdout.strip() if done.returncode == 0 else ''


def cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def tables(text):
    """마크다운 표를 (바로 위 제목, 머리행, 데이터 행들)로 읽는다. 표마다 칸 수가 달라도 된다."""
    result, heading, lines, i = [], '', text.splitlines(), 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#'):
            heading = line.lstrip('#').strip()
        elif line.startswith('|') and i + 1 < len(lines) and SEPARATOR.fullmatch(lines[i + 1].strip()):
            header, rows, i = cells(line), [], i + 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append((cells(lines[i]) + [''] * len(header))[:len(header)])
                i += 1
            result.append((heading, header, rows))
            continue
        i += 1
    return result


def plain(text):
    """마크다운 링크·강조·코드 표시를 걷어 글만 남긴다."""
    return re.sub(r'[*`]', '', re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)).strip()


def phases(board):
    result = []
    for item in (board or {}).get('phases') or []:
        if isinstance(item, dict) and isinstance(item.get('name'), str) and item['name'].strip():
            status = item.get('status') if item.get('status') in STATUSES else 'todo'
            refs = [d for d in item.get('deliverables') or [] if isinstance(d, str)]
            result.append({'name': item['name'].strip(), 'status': status, 'deliverables': refs,
                           'note': item.get('note') if isinstance(item.get('note'), str) else ''})
    return result


def roles(root, config):
    result = []
    for role, branch in (config.get('roles') or {}).items():
        text = read(root / f'handovers/to_{role}.md')
        match = TITLE.search(text)
        state = re.search(r'^- 상태:\s*(ready|running|blocked)\s*$', text, re.M)
        task = {'key': match.group(1), 'goal': match.group(2), 'status': state.group(1) if state else 'ready'} if match else None
        result.append({'role': role, 'branch': branch, 'task': task})
    return result


def plans(root):
    """PLANS.md의 과제 표들을 열 이름으로 읽는다. 섹션 제목을 group으로 남기고 나중 섹션을 앞에 둔다."""
    def column(header, pattern):
        return next((n for n, h in enumerate(header) if re.search(pattern, h)), None)
    groups = []
    for heading, header, rows in tables(read(root / 'PLANS.md')):
        key, status = column(header, r'과제|키'), column(header, r'상태')
        if key is None or status is None:
            continue
        goal, owner = column(header, r'목표|결과|다음|내용'), column(header, r'담당|책임')
        groups.append([{'key': plain(r[key]), 'goal': plain(r[goal]) if goal is not None else '',
                        'owner': plain(r[owner]) if owner is not None else '', 'status': plain(r[status]),
                        'group': heading} for r in rows if r[key].strip()])
    return [item for items in reversed(groups) for item in items]


def notes(root, limit=5):
    """PLANS.md 첫 제목 아래, 첫 표나 소제목 전까지의 요약 문단. 최신 상황 요약으로 보여 준다."""
    template = set(read(Path(__file__).resolve().parents[1] / 'assets/repository/.fullops-squad/PLANS.md').splitlines())
    result = []
    for line in read(root / 'PLANS.md').splitlines()[1:]:
        if line.lstrip().startswith(('#', '|')):
            break
        if line.strip() and line not in template:  # 템플릿 안내 문장은 요약이 아니다
            result.append(plain(line)[:280])
    return result[:limit]


def history(root, limit=30):
    entries = []
    for log in sorted((root / 'handovers/logs').glob('*_to_*.md')):
        role = log.stem.split('_to_', 1)[-1]
        for block in re.split(r'^(?=## [A-Za-z0-9][A-Za-z0-9._-]* — \d{4}-\d{2}-\d{2}$)', read(log), flags=re.M):
            head = re.match(r'## (\S+) — (\d{4}-\d{2}-\d{2})$', block, re.M)
            if head:
                goal = TITLE.search(block)
                entries.append({'key': head.group(1), 'date': head.group(2), 'role': role,
                                'goal': goal.group(2) if goal else ''})
    entries.sort(key=lambda e: e['date'], reverse=True)
    return entries[:limit]


def routes(root):
    result = {}
    for path in sorted((root / 'docs/evaluations/jev').glob('*-route.json')):
        data = load(path) or {}
        if data.get('route') in ('simple', 'design'):
            result[path.name[:-len('-route.json')]] = {'route': data['route'], 'role': data.get('role'), 'model': model_of(data),
                                                        'deliverables': [d for d in data.get('deliverables') or [] if isinstance(d, str)]}
    return result


def model_of(data):
    model = data.get('model') if isinstance(data, dict) else None
    return {k: model.get(k) for k in ('agent', 'provider', 'model', 'effort', 'source')} if isinstance(model, dict) else None


def models(root):
    """설계 뒤 worker용 모델 선택 기록. {'<과제 키>|<역할>': 모델}"""
    result = {}
    for path in sorted((root / 'docs/evaluations/jev').glob('*-model-*.json')):
        data = load(path) or {}
        if data.get('task_key') and data.get('role') and model_of(data):
            result[f"{data['task_key']}|{data['role']}"] = model_of(data)
    return result


def review_times(repo):
    """리뷰 폴더별 가장 최근 커밋 시각. git log 한 번으로 모은다."""
    times, stamp = {}, 0
    for line in git(repo, 'log', '--format=@%ct', '--name-only', '--', '.fullops-squad/docs/evaluations/qa-reports').splitlines():
        if line.startswith('@'):
            stamp = int(line[1:])
        else:
            folder = next((part for part in line.split('/') if part.endswith('-review')), None)
            if folder:
                times.setdefault(folder, stamp)
    return times


def reviews(repo, root, limit=12):
    result, times = [], review_times(repo)
    for path in (root / 'docs/evaluations/qa-reports').glob('*-review/result.json'):
        data = load(path) or {}
        findings = [f for f in data.get('findings') or [] if isinstance(f, dict)]
        blocking = sum(1 for f in findings if f.get('severity') in ('critical', 'high') and not f.get('resolved'))
        summary = (load(path.with_name('lint.json')) or {}).get('summary') or {}
        stamp = times.get(path.parent.name) or int(path.stat().st_mtime)  # 커밋 전이면 파일 시각
        result.append({'key': path.parent.name[:-len('-review')], 'conclusion': data.get('conclusion') or '',
                       'reviewer': data.get('reviewer') or '', 'head': (data.get('head') or '')[:12],
                       'findings': len(findings), 'blocking': blocking,
                       'lint_errors': summary.get('errors') if isinstance(summary.get('errors'), int) else None,
                       'lint_warnings': summary.get('warnings') if isinstance(summary.get('warnings'), int) else None,
                       'date': datetime.fromtimestamp(stamp).strftime('%Y-%m-%d'), 'time': stamp})
    result.sort(key=lambda r: r['time'], reverse=True)
    return result[:limit]


def written(path):
    """파일이 있거나, 폴더에 .gitkeep 말고 실제 파일이 있으면 원천 문서가 있다고 본다."""
    if path.is_dir():
        return any(p.is_file() and p.name != '.gitkeep' for p in path.rglob('*'))
    return path.is_file()


def deliverables(root):
    result = []
    for _, header, rows in tables(read(root / 'docs/deliverables/README.md')):
        if len(header) != 5:
            continue
        for ident, stage, name, source, status in rows:
            if re.fullmatch(r'D\d{2}', ident):
                paths = re.findall(r'`([^`]+)`', source)
                _, meta = meta_for(root, ident, paths)
                meta = meta or {}  # 원천 문서의 front matter가 인덱스 표보다 우선한다
                result.append({'id': ident, 'stage': stage, 'name': meta.get('title') or name, 'source': paths,
                               'status': meta.get('status') or status, 'index_status': status,
                               'updated': meta.get('updated', ''), 'owner': meta.get('owner', ''),
                               'summary': meta.get('summary', ''), 'has_meta': bool(meta),
                               'source_exists': any(written(root / p.split(' ')[0]) for p in paths)})
    return result


def build(repo):
    root = Path(repo) / '.fullops-squad'
    config = load(root / 'fullops.json') or {}
    board = load(root / 'board/board.json')
    return {
        'version': 1,
        'updated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'repo': Path(repo).resolve().name,
        'branch': git(repo, 'rev-parse', '--abbrev-ref', 'HEAD'),
        'head': git(repo, 'rev-parse', '--short=12', 'HEAD'),
        'title': (board or {}).get('title') or Path(repo).resolve().name,
        'summary': (board or {}).get('summary') or '',
        'board_error': None if isinstance(board, dict) else 'board/board.json을 읽을 수 없습니다',
        'phases': phases(board if isinstance(board, dict) else None),
        'roles': roles(root, config),
        'notes': notes(root),
        'plans': plans(root),
        'history': history(root),
        'routes': routes(root),
        'models': models(root),
        'reviews': reviews(repo, root),
        'deliverables': deliverables(root),
    }


def write(repo):
    output = Path(repo) / BOARD / 'board-data.js'
    output.parent.mkdir(parents=True, exist_ok=True)
    text = 'window.FULLOPS_BOARD = ' + json.dumps(build(repo), ensure_ascii=False, indent=1) + ';\n'
    if read(output).split('\n', 3)[3:] != text.split('\n', 3)[3:]:  # 변경 시각만 다르면 다시 쓰지 않는다
        output.write_text(text, encoding='utf-8', newline='\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, help='FullOps가 활성화된 레포 루트')
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / '.fullops-squad/fullops.json').is_file():
        parser.exit(1, 'FullOps setup이 된 레포 루트를 지정하세요\n')
    print(write(repo).relative_to(repo).as_posix())


if __name__ == '__main__':
    main()
