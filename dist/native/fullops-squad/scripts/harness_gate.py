"""FullOps 검증 증거·보고 규칙(rules/common/testing.md `담당과 반복 범위`)을 행동 시점에 지킨다.

막는 것은 객관적으로 확인되는 두 가지뿐이다: 보고서가 링크하지 않은 qa-reports 캡처의 커밋, 같은 과제의 차수 폴더 생성.
나머지는 쓴 직후에 알린다(PostToolUse additionalContext). 어떤 오류도 작업을 막지 않는다.
"""
import json
from pathlib import Path
import re
import subprocess

from done_gate import git

REPORTS = '.fullops-squad/docs/evaluations/qa-reports/'
MEDIA = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm', '.mov')
ROUND = re.compile(r'-(?:FIX|RECHECK|RETEST|LOWS|R\d+)(?=-|$)', re.I)
WIDTHS = re.compile(r'(?<!\d)(1920|1440|1366|1280|1024|768|430|414|390|375|360|320)(?:\s*px)?(?!\d)')
THEMES = re.compile(r'라이트.{0,6}다크|light.{0,6}dark', re.I)
LIGHT_LEVELS = ('minimal', 'lite')
REPORT_LINES = 40


def _relative(root, name):
    path = Path(name)
    try:
        return (path if path.is_absolute() else root / path).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return name.replace('\\', '/')


def _folder(relative):
    """qa-reports 바로 아래 과제 폴더 이름. 그 밖이면 None"""
    return relative[len(REPORTS):].split('/', 1)[0] if relative.startswith(REPORTS) and '/' in relative[len(REPORTS):] else None


def _commit_roots(root, commands):
    """`git ... commit`을 실행할 체크아웃과, 같은 명령의 `git add`가 넓게 담는지"""
    roots, broad = [], []
    for words in commands:
        if Path(words[0].strip('\'"')).stem != 'git':
            continue
        args, where = [w.strip('\'"') for w in words[1:]], root
        while args and args[0] in ('-C', '-c'):
            if args[0] == '-C' and len(args) > 1:
                where = Path(args[1]) if Path(args[1]).is_absolute() else root / args[1]
            args = args[2:]
        if args[:1] == ['add']:
            broad += [where / a for a in args[1:] if not a.startswith('-')] + ([where] if {'-A', '--all'} & set(args) else [])
        elif args[:1] == ['commit']:
            roots.append(where)
    return roots, broad


def unlinked_media(root, commands):
    """커밋될 새 qa-reports 캡처 중 그 과제 폴더의 어느 .md도 링크하지 않는 것. raw/는 .gitignore가 뺀다"""
    roots, broad = _commit_roots(root, commands)
    found = []
    for where in roots:
        try:
            top = Path(git(where, 'rev-parse', '--show-toplevel'))
            staged = git(top, '-c', 'core.quotepath=false', 'diff', '--cached', '--name-only', '--diff-filter=A').splitlines()
            # 같은 명령의 `git add`는 hook 뒤에 실행된다. 넓게 담는 add면 아직 추적하지 않는 파일도 커밋 후보다.
            untracked = git(top, '-c', 'core.quotepath=false', 'ls-files', '--others', '--exclude-standard', '--', REPORTS).splitlines()
        except (OSError, subprocess.CalledProcessError):
            continue
        scope = [p.resolve() for p in broad]
        candidates = staged + [u for u in untracked if any(s == (top / u).resolve() or s in (top / u).resolve().parents for s in scope)]
        texts = {}
        for name in candidates:
            folder = _folder(name)
            if not folder or not name.lower().endswith(MEDIA) or '/raw/' in name:
                continue
            if folder not in texts:
                texts[folder] = '\n'.join(p.read_text(encoding='utf-8', errors='replace')
                                          for p in (top / REPORTS / folder).rglob('*.md') if '/raw/' not in p.as_posix())
            if Path(name).name not in texts[folder]:
                found.append(name)
    return found


def round_folder(root, files):
    """새로 만드는 `<과제 키>-FIX…/report.md`처럼 기존 과제 폴더의 차수 폴더면 (새 폴더, 기존 폴더)"""
    for name, _ in files:
        relative = _relative(root, name)
        folder = _folder(relative)
        if not folder or relative != f'{REPORTS}{folder}/report.md' or (root / REPORTS / folder).exists():
            continue
        match = ROUND.search(folder)
        if not match or match.start() == 0:
            continue
        base = folder[:match.start()]
        existing = sorted((bool(ROUND.search(p.name[len(base):])), p.name) for p in (root / REPORTS).iterdir()
                          if p.is_dir() and p.name != folder and (p.name == base or p.name.startswith(base + '-')))
        if existing:  # 차수 접미사가 없는 원래 과제 폴더를 먼저 가리킨다
            return folder, existing[0][1]
    return None


def advice(root, files, level, handover_pattern):
    """방금 쓴 지시서·보고서가 테스트 레벨 예산을 넘는 것 같으면 알릴 문장들"""
    notes = []
    if level not in LIGHT_LEVELS:
        return notes
    for name, _ in files:
        relative = _relative(root, name)
        path = root / relative
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        if handover_pattern.search(relative):
            widths = sorted(set(WIDTHS.findall(text)), key=int, reverse=True)
            asks = ([f"{'·'.join(widths)} 폭"] if len(widths) > 1 else []) + (['라이트·다크 테마'] if THEMES.search(text) else [])
            if asks:
                notes.append(f"지시서 {relative}가 {', '.join(asks)} 캡처를 요구합니다. 테스트 레벨 {level}의 개발 과제는 lint와 변경 동작 테스트로 "
                             '검증하고 보고용 캡처를 만들지 않습니다. 화면 품질은 통합 후보의 큰 틀 검수에서 봅니다. 반응형·테마가 이번 변경 대상이 아니면 '
                             '그 요구를 빼고, 꼭 필요하면 레벨을 올리거나 사용자에게 물으세요(rules/common/testing.md).')
        elif _folder(relative) and relative.endswith('/report.md'):
            lines = len(text.splitlines())
            if lines > REPORT_LINES:
                notes.append(f'보고서 {relative}가 {lines}줄입니다. 테스트 레벨 {level}의 보고서는 판정 항목과 결과 표, 실패·미실행·한계만 적고 '
                             '30줄 안팎으로 둡니다. 통과한 검사는 명령·SHA·종료코드 한 줄이면 됩니다.')
    return notes


BUDGET = 2  # intents/FLOW-GRAPH-001 Q3: 수정 1회와 재검증 1회까지는 정상 흐름이다
REPORTED = re.compile(r'<!-- fullops-attempt: (\S+) (\S+) -->')
# 차수 표기. `-FIX-DEV`·`-FIX-TESTER`처럼 역할로 나눈 키는 같은 차수 FIX다
ROUND_ID = re.compile(r'-((?:FIX|RECHECK|RETEST|LOWS|R\d+)(?:-\d+)?)(?=-|$)', re.I)


def _repeat_key(words):
    """`work.py reopen --key K`나 차수 키 `jev_route.py --key K-FIX`면 K"""
    names = [Path(w.strip('\'"')).name for w in words]
    reopen = 'work.py' in names and 'reopen' in words
    if not (reopen or 'jev_route.py' in names) or '--key' not in words[:-1]:
        return None
    key = words[words.index('--key') + 1].strip('\'"')
    return key if reopen or ROUND.search(key) else None


def base_key(key):
    """차수 키 `K-FIX-DEV`의 원래 과제 키 K"""
    match = ROUND.search(key)
    return key[:match.start()] if match and match.start() else key


def rework(root, base):
    """(반복 횟수, 예산, 재오픈 수, 차수 표기, 차수 키). 재오픈은 로그·인박스의 서로 다른 attempt − 1이다"""
    handovers = root / '.fullops-squad/handovers'
    attempts, budget = set(), BUDGET
    for path in [*handovers.glob('logs/*.md'), *handovers.glob('to_*.md')]:
        text = path.read_text(encoding='utf-8', errors='replace')
        attempts |= {a for k, a in REPORTED.findall(text) if k == base}
        if path.parent == handovers and re.search(rf'^# {re.escape(base)} — ', text, re.M):
            current = re.search(r'^attempt:\s*(\S+)', text, re.M)
            attempts |= {current.group(1)} if current else set()
            own = re.search(r'반복 예산\s*[:：]\s*(\d+)', text)
            budget = int(own.group(1)) if own else budget
    jev = root / '.fullops-squad/docs/evaluations/jev'
    rounds = sorted(p.name[:-len('-route.json')] for p in jev.glob(f'{base}-*-route.json')
                    if (m := ROUND.search(p.name[:-len('-route.json')])) and m.start() == len(base))
    ids = sorted({'-'.join(m.upper() for m in ROUND_ID.findall(r[len(base):])) for r in rounds})
    reopens = max(0, len(attempts) - 1)
    return reopens + len(ids), budget, reopens, ids, rounds


def repeat_budget(root, commands):
    """같은 과제의 수정·재검증이 예산을 넘으면 사람에게 올리라는 문장(docs/flow-graph.md E15)"""
    for words in commands:
        key = _repeat_key(words)
        if not key:
            continue
        base = base_key(key)
        count, budget, reopens, ids, rounds = rework(root, base)
        if count <= budget:
            continue
        flagged = {}
        for review in [base, *rounds]:
            try:
                findings = json.loads((root / REPORTS / f'{review}-review/result.json').read_text(encoding='utf-8'))['findings']
            except (OSError, ValueError, KeyError, TypeError):
                continue
            for path in {f.get('path') for f in findings if isinstance(f, dict) and f.get('path')}:
                flagged[path] = flagged.get(path, 0) + 1
        repeated = [f'{p}({n}회)' for p, n in sorted(flagged.items(), key=lambda i: -i[1]) if n > 1][:3]
        return (f"{base}의 수정·재검증이 {count}회째로 예산 {budget}회를 넘었습니다(재오픈 {reopens}회"
                + (f", 차수 {', '.join(ids)}" if ids else '') + '). '
                + (f"리뷰에서 반복 지적된 파일: {', '.join(repeated)}. " if repeated else '')
                + '같은 방식으로 더 고치기 전에 사용자에게 올리세요. 범위·설계를 다시 정할지, 마지막으로 나아진 SHA를 남기고 '
                '이후 시도는 버린 뒤 남은 문제를 PLANS.md에 넘길지 정합니다. 지시서에 `반복 예산: N`을 적으면 그 값을 씁니다.')
    return None
