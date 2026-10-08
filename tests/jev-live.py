"""실제 Jev로 합성 과제의 route/find/context/조작 응답과 캐시·목적별 기대 목록을 확인한다. API 키는 저장하지 않는다."""
import argparse
from contextlib import redirect_stdout
import hashlib
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
import jev_context
import jev_find
import jev_observe as jev
import jev_packet
import jev_route
import jev_test_unity as unity
import jev_test_web as web
import setup
import storage
import work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    key = jev.key_from_file(args.env_file)
    output = Path(args.output)
    if output.exists():
        parser.error('기존 검증 증거를 보존합니다. 새 --output 경로를 사용하세요')
    os.environ['FULLOPS_JEV_CACHE_BYPASS'] = '1'
    calls, errors, last_payload = [], [], []
    started = time.monotonic()
    def call(payload):
        response = jev.request(payload, key)
        _, usage, elapsed, model = jev.validated(response, payload['questions'], partial=True)
        calls.append({'input_sha256': jev.digest(json.dumps(payload['state'], sort_keys=True).encode()),
            'question_sha256': jev.digest(json.dumps(payload['questions'], sort_keys=True).encode()),
            'requested_model': payload['model'], 'response_model': model, 'usage': usage,
            'elapsed_seconds': elapsed, 'cached': response[0].get('cached', False)})
        last_payload[:] = [payload]
        return response
    with tempfile.TemporaryDirectory(prefix='fullops-jev-live-') as temp:
        repo = Path(temp)
        def git(*argv):
            return subprocess.check_output(['git', '-C', temp, *argv], text=True).strip()
        git('init', '-q', '-b', 'main')
        with redirect_stdout(io.StringIO()):
            setup.setup(repo, roles=['architecture', 'dev'], local_only=True)
        fixtures = {'api.py': '# User lookup API.\ndef fetch_user(user_id):\n    return {"name": "test"}\n',
            'caller.py': '# Calls user lookup.\nfrom api import fetch_user\nprint(fetch_user(1))\n',
            'test_api.py': '# Tests the user lookup response.\nfrom api import fetch_user\nassert fetch_user(1)["name"] == "test"\n',
            'notes.md': '# Unrelated gardening notes\nWater plants weekly.\n',
            '.fullops-squad/docs/design-docs/interface-design.md': '# User lookup response contract D05\n[Implementation](../../../api.py)\nREQ-USER: fetch_user returns name.\n'}
        for name, content in fixtures.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        git('add', '-A')
        git('-c', 'user.name=test', '-c', 'user.email=test@example.test', 'commit', '-qm', 'synthetic fixture')
        with redirect_stdout(io.StringIO()):
            work.new(repo, 'dev', 'LIVE-1', 'Rename fetch_user to lookup_user and add user_id to its API response; update callers, tests and D05 contract.', 'HEAD')
        labels = {'direct_edit': ['api.py'], 'impact_check': ['caller.py', 'test_api.py'],
                  'document_read': ['.fullops-squad/docs/design-docs/interface-design.md'],
                  'document_update': ['.fullops-squad/docs/design-docs/interface-design.md']}
        baseline_started = time.monotonic()
        baseline = jev_packet.packet(repo, 'dev', 'LIVE-1', ['api.py'], updates=['D05'])
        baseline_seconds = time.monotonic() - baseline_started
        assisted_started = time.monotonic()
        route = jev_route.route(repo, 'LIVE-1', 'Rename fetch_user to lookup_user, add user_id to its response, update callers/tests and D05 API contract. Product requirements are fixed.', call)
        if route.get('error') or route.get('docs_status') != 'complete':
            errors.append('route response incomplete')
        code = jev_find.find(repo, 'dev', 'LIVE-1', call)
        documents = jev_find.find(repo, 'dev', 'LIVE-1', call, scope='documents')
        for name, result in [('find', code), ('documents-find', documents)]:
            if result['error'] or result['partial']:
                errors.append(name + ' response incomplete')
            storage.write_json(jev_find.result_path(repo, 'LIVE-1', name), result)
        context = jev_context.context(repo, 'dev', 'LIVE-1', list(fixtures), call)
        if context.get('error') or (context.get('context') or {}).get('fallback'):
            errors.append('context response incomplete')
        storage.write_json(jev_find.result_path(repo, 'LIVE-1', 'context'), context)
        packet = jev_packet.packet(repo, 'dev', 'LIVE-1', ['api.py'], updates=['D05'])
        assisted_seconds = time.monotonic() - assisted_started
        search_usage = {name: sum(c['usage'][name] for c in calls) for name in ('input_tokens', 'output_tokens', 'cost')}
        evaluation = jev_packet.evaluate(packet, labels)
        comparison = {'task_key': 'LIVE-1', 'head': packet['head'], 'labels': labels,
            'baseline': {'method': 'local definition/string/link/source-mapping search; same explicit seed and D05',
                         'evaluation': jev_packet.evaluate(baseline, labels), 'elapsed_seconds': baseline_seconds,
                         'jev_usage': {'input_tokens': 0, 'output_tokens': 0, 'cost': 0}},
            'assisted': {'method': 'same local search plus Jev code/document recommendations and context signals',
                         'evaluation': evaluation, 'elapsed_seconds': assisted_seconds, 'jev_usage': search_usage},
            'additional_search': {'status': 'not_run', 'reason': 'candidate generation only; no human or coding agent follow-through'},
            'rework': {'status': 'not_run'}, 'whole_task_tokens_cost': {'status': 'not_run',
                'reason': 'host agent reading/implementation/review tokens are not measured; no savings claim'}}
        # 분류 결과의 실제 역할/문서 ID를 저장·연결·소비한다. 이 연결 시험은 비용 절감 비교가 아니다.
        pipeline_request = 'Rename fetch_user to lookup_user, update callers/tests and the API contract. Product requirements are fixed.'
        pipeline_route = jev_route.route(repo, 'LIVE-ROUTE', pipeline_request, call)
        owner = pipeline_route.get('role')
        if not owner:
            raise ValueError('live pipeline route owner unresolved')
        storage.write_json(jev_find.result_path(repo, 'LIVE-ROUTE', 'route'), pipeline_route)
        with redirect_stdout(io.StringIO()):
            work.new(repo, owner, 'LIVE-ROUTE', pipeline_request, 'HEAD')
        subprocess.run([sys.executable, str(ROOT / 'plugins/fullops-squad/scripts/jev_route.py'), '--repo', temp,
                        '--key', 'LIVE-ROUTE', '--role', owner, '--bind-inbox'], check=True, capture_output=True)
        pipeline_route = json.loads(jev_find.result_path(repo, 'LIVE-ROUTE', 'route').read_text())
        for scope, name in [('code', 'find'), ('documents', 'documents-find')]:
            selected = jev_find.find(repo, owner, 'LIVE-ROUTE', call, scope=scope)
            storage.write_json(jev_find.result_path(repo, 'LIVE-ROUTE', name), selected)
        selected_context = jev_context.context(repo, owner, 'LIVE-ROUTE', list(fixtures), call)
        storage.write_json(jev_find.result_path(repo, 'LIVE-ROUTE', 'context'), selected_context)
        pipeline_packet = jev_packet.packet(repo, owner, 'LIVE-ROUTE')  # seed/update ID를 강제로 주지 않는다.
        pipeline = {'task_key': 'LIVE-ROUTE', 'role': owner, 'route_deliverables': pipeline_route['deliverables'],
                    'route_additional_deliverables': pipeline_route.get('additional_deliverables', []),
                    'producer_status': pipeline_packet['producer_status'], 'partial': pipeline_packet['partial'],
                    'unknown': pipeline_packet['unknown'], 'categories': pipeline_packet['categories'],
                    'input_sha256': pipeline_packet['input_sha256'], 'explicit_seeds': [], 'explicit_updates': [],
                    'status': 'passed' if 'route' in pipeline_packet['producer_status'] else 'failed',
                    'limitation': 'single synthetic connection fixture; no implementation, whole-task cost or quality gain claim'}
        if pipeline['status'] != 'passed':
            errors.append('persisted route not consumed by packet')
        page = {'url': 'https://example.test', 'elements': [{'ref': 'e1', 'role': 'textbox', 'name': 'New todo'}]}
        web_decision = web.ask(call, {'goal': 'Add milk to the todo list', 'values': {'milk': 'milk'}}, page, [], 1)
        unity_decision = unity.ask(call, {'goal': 'All enemies are defeated; finish the check.'},
                                  {'step': 1, 'actors': [], 'actorCounts': [{'group': 'enemy', 'count': 0}], 'actions': []}, [])
        payload = last_payload[0]
        fresh = call(payload)
        os.environ.pop('FULLOPS_JEV_CACHE_BYPASS')
        cached = call(payload)
        cache_proven = cached[0].get('cached') is True and cached[0]['usage']['cost'] == 0
        if not cache_proven:
            errors.append('cache hit not proven')
        result = {'plugin_version': json.loads((ROOT / 'plugins/fullops-squad/plugin.json').read_text())['version'],
            'fixture_head': git('rev-parse', 'HEAD'), 'fixture_sha256': jev.digest(json.dumps(fixtures, sort_keys=True).encode()),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'policy': 'uncached synthetic calls plus exact-payload cache control; scores are recommendations',
            'status': 'failed' if errors else 'passed', 'errors': errors, 'calls': calls,
            'known_cost': sum(c['usage']['cost'] for c in calls), 'elapsed_seconds': time.monotonic() - started,
            'route': {'route': route['route'], 'role': route['role'], 'deliverables': route['deliverables']},
            'code_candidates': code['candidates'], 'document_candidates': documents['candidates'],
            'context': context.get('context'), 'packet_evaluation': evaluation,
            'search_comparison': comparison, 'persisted_route_pipeline': pipeline,
            'web_operation': web_decision['operation']['choice'], 'web_risk': web_decision['risk'],
            'unity_action': unity_decision['action']['choice'], 'cache_hit_proven': cache_proven,
            'cache_answers_equal': fresh[0]['answers'] == cached[0]['answers'],
            'limitations': ['synthetic task only', 'no real browser or Unity Player', 'no whole-repo relevance guarantee']}
        storage.write_json(output, result)
        print(json.dumps({k: result[k] for k in ('status', 'known_cost', 'elapsed_seconds', 'cache_hit_proven', 'errors')}))
        print(output)
        return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
