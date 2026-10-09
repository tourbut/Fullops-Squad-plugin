"""동일한 합성 과제로 배치·재정렬·폴더 다중 경로 탐색을 실제 Jev에서 비교한다."""
import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import jev_find
import jev_observe as jev
import jev_packet
import search_index
import setup
import storage
import work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error('기존 평가를 보존합니다. 새 --output 경로를 사용하세요')
    key = jev.api_key(args.env_file)
    os.environ['FULLOPS_JEV_CACHE_BYPASS'] = '1'
    implementation = {p.name: jev.digest(p.read_bytes()) for p in (ROOT / 'plugins/fullops-squad/scripts').glob('*.py')
                      if p.name in ('search_index.py', 'jev_find.py', 'jev_observe.py', 'jev_packet.py', 'work.py')}
    tasks = [
        {'key': 'SEMANTIC', 'request': 'Deny access after membership termination; inspect the eligibility decision and its written agreement.',
         'labels': {'direct_edit': ['src/access/ledger.py'], 'impact_check': ['src/caller.py', 'tests/test_admission.py'],
                    'document_read': ['docs/contract.md'], 'document_update': []}, 'retrieval': ['src/access/ledger.py', 'docs/contract.md']},
        {'key': 'EXPLICIT', 'request': 'Change `src/access/ledger.py` can_enter, update its callers/tests and `docs/contract.md` account admission contract.',
         'seeds': ['src/access/ledger.py', 'docs/contract.md'],
         'labels': {'direct_edit': ['src/access/ledger.py'], 'impact_check': ['src/caller.py', 'tests/test_admission.py'],
                    'document_read': ['docs/contract.md'], 'document_update': ['docs/contract.md']}, 'retrieval': ['src/access/ledger.py', 'docs/contract.md']},
        {'key': 'MISSING', 'request': 'Locate the existing orbital collision prediction engine and spacecraft trajectory equations.',
         'labels': {c: [] for c in jev_packet.CATEGORIES}, 'retrieval': []},
    ]
    rows = []
    with tempfile.TemporaryDirectory(prefix='fullops-search-eval-') as temp:
        repo = Path(temp)
        def git(*args):
            return subprocess.check_output(['git', '-C', temp, *args], stderr=subprocess.DEVNULL, encoding='utf-8').strip()
        git('init', '-q', '-b', 'main')
        git('config', 'core.autocrlf', 'false')
        with redirect_stdout(io.StringIO()):
            setup.setup(repo, roles=['architecture', 'dev'], local_only=True)
        files = {'src/access/ledger.py': '# Account admission: closed accounts cannot enter the service.\ndef can_enter(account):\n    """Decide whether an account may enter; reject closed accounts."""\n    return account["status"] != "closed"\n',
                 'src/caller.py': '# Request admission.\nfrom src.access.ledger import can_enter\n',
                 'tests/test_admission.py': '# Verify admission for closed accounts.\nfrom src.access.ledger import can_enter\n',
                 'docs/contract.md': '---\ntitle: Account admission contract\nsummary: Closed accounts must be rejected before entering the service.\nstatus: approved\n---\n# Admission\n[Implementation](../src/access/ledger.py)\ncan_enter is the access decision.\n'}
        for n in range(260):
            files[f'src/util{n % 6}/sample{n:03}.py'] = f'# Sampling utility {n}; produces a numeric observation.\ndef sample_{n}():\n    return {n}\n'
        for name, value in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding='utf-8', newline='\n')
        git('add', '-A')
        git('-c', 'user.name=test', '-c', 'user.email=test@example.test', 'commit', '-qm', 'search comparison fixture')
        head = git('rev-parse', 'HEAD')
        cache_metrics = {}
        for label in ('cold', 'warm'):
            start = time.monotonic()
            search_index.metadata(repo, head)
            cache_metrics[label + '_seconds'] = round(time.monotonic() - start, 3)
        for task in tasks:
            with redirect_stdout(io.StringIO()):
                work.new(repo, 'dev', task['key'], task['request'], head)
            for strategy in ('batch', 'rerank', 'hierarchical'):
                start = time.monotonic()
                code = jev_find.find(repo, 'dev', task['key'], lambda p: jev.request(p, key), strategy=strategy)
                documents = jev_find.find(repo, 'dev', task['key'], lambda p: jev.request(p, key), scope='documents', strategy=strategy)
                for suffix, result in (('find', code), ('documents-find', documents)):
                    storage.write_json(jev_find.result_path(repo, task['key'], suffix), result)
                packet = jev_packet.packet(repo, 'dev', task['key'], seeds=task.get('seeds', []))
                selected = {c['path'] for result in (code, documents) for c in result['candidates']}
                expected = set(task['retrieval'])
                rows.append({'task_key': task['key'], 'strategy': strategy,
                    'retrieval_recall': len(selected & expected) / len(expected) if expected else None,
                    'required_document_missed': sorted(set(task['labels']['document_read']) - selected),
                    'false_absence': bool(expected) and any((r.get('existence') or {}).get('status') == 'not_confirmed' for r in (code, documents)),
                    'existence': {'code': code['existence'], 'documents': documents['existence']},
                    'code_candidates': sorted(c['path'] for c in code['candidates']), 'document_candidates': sorted(c['path'] for c in documents['candidates']),
                    'usage': {k: sum((r['usage'][k] or 0) for r in (code, documents)) for k in ('input_tokens', 'output_tokens', 'known_cost')},
                    'calls': sum(len(r['calls']) for r in (code, documents)), 'elapsed_seconds': round(time.monotonic() - start, 3),
                    'errors': [r['error'] for r in (code, documents) if r['error']],
                    'models': sorted({c['model'] for r in (code, documents) for c in r['calls']}),
                    'packet_evaluation': jev_packet.evaluate(packet, task['labels']),
                    'packet_context_chars': sum(len(files.get(p, '')) for p in packet['context_paths']),
                    'map_sha256': {'code': code['map_sha256'], 'documents': documents['map_sha256']}})
                print(json.dumps({k: rows[-1][k] for k in ('task_key', 'strategy', 'retrieval_recall', 'calls', 'usage', 'errors')}), flush=True)
            (repo / '.fullops-squad/handovers/to_dev.md').write_bytes(b'')
        result = {'version': 1, 'fixture_head': head, 'fixture_sha256': jev.digest(json.dumps(files, sort_keys=True).encode()),
            'implementation_sha256': implementation,
            'runner_sha256': jev.digest(Path(__file__).read_bytes()), 'policy': jev_find.POLICY,
            'cache_metrics': cache_metrics, 'tasks': tasks, 'results': rows,
            'limitations': ['synthetic corpus only; thresholds and limit are not calibrated',
                'hierarchical visits alternative folders exhaustively; no recall or cost reduction guarantee',
                'recommendations stay read/impact candidates; direct edit requires explicit seed/diff',
                'document update requires explicit update/route; evaluation does not feed labels to retrieval',
                'packet_context_chars is fixture text volume, not host agent token use or whole-task cost']}
        storage.write_json(output, result)
    print(output)
    return 1 if any(row['errors'] for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
