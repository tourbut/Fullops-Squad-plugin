"""제품/기술 역할 분리의 라우팅·배정 훅·브랜치 보존을 임시 레포에서 검증한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import jev_route
import setup


with tempfile.TemporaryDirectory(prefix='fullops-product-') as tmp:
    repo = Path(tmp)
    subprocess.run(['git', 'init', '-q', '-b', 'main', tmp], check=True)
    setup.setup(tmp, roles=['designer', 'dev', 'art', 'coor'], local_only=True)
    agents = repo / '.fullops-squad/orca-agents.md'
    original = agents.read_text(encoding='utf-8')
    markers = ('- 설계 역할: `designer`\n- 제품 기획 역할: `designer`\n'
               '- 기술 계획 역할: `dev`\n- coordinator 역할: `coor`')
    split = original.replace('- 설계 역할: `architecture`', markers)
    # setup의 기본 설계 역할은 첫 등록 역할이다.
    if split == original:
        split = original.replace('- 설계 역할: `designer`', markers)
    agents.write_text(split, encoding='utf-8')
    assert jev_route.product_roles(repo) == ('designer', 'dev')

    def response(scope, probability=0.95, owner='dev', owner_probability=0.9):
        def call(payload):
            questions = payload['questions']
            assert set(questions['scope']['criteria']) == {'implementation', 'product'}
            roles = list(questions['role']['criteria'])
            assert set(roles) == {'dev', 'art'}
            return {'model': 'typesafe/jev-test', 'usage': {'input_tokens': 1, 'output_tokens': 1, 'cost': 0.001}, 'answers': {
                'scope': {'type': 'choice', 'choice': scope, 'confidence': probability,
                          'probabilities': {s: probability if s == scope else 1 - probability
                                            for s in questions['scope']['criteria']}},
                'role': {'type': 'choice', 'choice': owner, 'confidence': owner_probability,
                         'probabilities': {r: owner_probability if r == owner else 1 - owner_probability
                                           for r in roles}}}}, 0.1
        return call

    implementation = jev_route.route(repo, 'IMPLEMENT', '확정된 요구의 여러 모듈 API 구조와 버그를 수정한다',
                                     response('implementation'))
    assert (implementation['route'], implementation['role']) == ('implementation', 'dev')
    product = jev_route.route(repo, 'PRODUCT', '새 게임 규칙을 정한다', response('product'))
    assert (product['route'], product['role']) == ('product', 'designer')
    art = jev_route.route(repo, 'ART', '확정된 규격의 에셋을 제작한다', response('implementation', owner='art'))
    assert (art['route'], art['role']) == ('implementation', 'art')
    for call in (response('implementation', 0.6), response('implementation', owner_probability=0.55)):
        result = jev_route.route(repo, 'UNCERTAIN', '책임 확인 필요', call)
        assert (result['route'], result['role'], result['model']) == ('unresolved', None, None)

    def failed(payload):
        raise RuntimeError('test failure')

    result = jev_route.route(repo, 'FAILED', '버그 수정', failed)
    assert result['route'] == 'unresolved' and result['role'] is None and result['error']
    resolved = jev_route.route(repo, 'RESOLVED', '버그 수정', failed,
                              override_role='dev', reason='확정 요구 안의 구현 과제')
    assert (resolved['route'], resolved['role'], resolved['original_route']) == ('implementation', 'dev', 'unresolved')
    for owner, reason in [('dev', ''), ('coor', '배정'), ('missing', '배정')]:
        try:
            jev_route.route(repo, 'INVALID', '작업', failed, override_role=owner, reason=reason)
        except ValueError:
            pass
        else:
            raise AssertionError((owner, reason))

    def hook(command=None, content=None):
        tool = ({'command': command} if command is not None else
                {'file_path': '.fullops-squad/handovers/to_dev.md', 'content': content})
        done = subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), 'tool'],
                              input=json.dumps({'cwd': tmp, 'session_id': 'product', 'tool_input': tool}),
                              capture_output=True, text=True, encoding='utf-8', check=True)
        return json.loads(done.stdout).get('hookSpecificOutput', {}).get('permissionDecisionReason', '')

    records = repo / '.fullops-squad/docs/evaluations/jev'
    records.mkdir(parents=True, exist_ok=True)
    for result in (implementation, product, art):
        (records / f"{result['task_key']}-route.json").write_text(json.dumps(result), encoding='utf-8')
    (records / 'BLOCKED-route.json').write_text(json.dumps({'version':'jev-route-v4', 'task_key':'BLOCKED', 'route': 'unresolved', 'role': None}), encoding='utf-8')
    assert not hook(content='---\ntitle: 구현 지시\n---\n# IMPLEMENT — 구현\n')
    assert hook(content='# PRODUCT — 제품 결정\n')
    assert hook(content='# ART — 다른 역할\n')
    assert '미확정' in hook('orca orchestration worker-start --run r1 --spec "BLOCKED 작업"')
    assert 'implementation' in hook(f'orca orchestration worker-start --run r1 --worktree "{tmp}" --spec "IMPLEMENT 작업"')
    subprocess.run(['git', '-C', tmp, 'add', '-A'], check=True)
    subprocess.run(['git', '-C', tmp, '-c', 'user.name=t', '-c', 'user.email=t@example.test', 'commit', '-qm', 'setup'], check=True)
    worker = repo / '.git/dev'
    subprocess.run(['git', '-C', tmp, 'worktree', 'add', '-q', '-b', 'fullops/dev', str(worker)], check=True)
    assert not hook(f'orca orchestration worker-start --run r1 --worktree "{worker}" --spec "IMPLEMENT 작업"')
    patch = ('*** Begin Patch\n*** Update File: .fullops-squad/handovers/to_dev.md\n@@\n'
             '+# IMPLEMENT — 구현\n+orca orchestration worker-start --spec "본문 예시"\n*** End Patch\n')
    assert not hook(patch)  # 지시서 안의 실행 예시는 실제 배정 명령이 아니다.
    assert hook(patch.replace('IMPLEMENT', 'PRODUCT'))

    agents.write_text(split.replace('- 기술 계획 역할: `dev`\n', ''), encoding='utf-8')
    result = jev_route.classify(repo, 'PARTIAL', '불완전한 설정', failed)
    assert result['route'] == 'unresolved' and result['role'] is None
    agents.write_text(split, encoding='utf-8')

    marker = repo / '.fullops-squad/fullops.json'
    config = json.loads(marker.read_text(encoding='utf-8'))
    config['roles']['designer'] = 'fullops/architecture'
    marker.write_text(json.dumps(config), encoding='utf-8')
    before = agents.read_bytes()
    setup.setup(tmp, roles=['designer'], local_only=True)
    assert json.loads(marker.read_text(encoding='utf-8'))['roles']['designer'] == 'fullops/architecture'
    assert agents.read_bytes() == before
    config['roles']['designer'] = config['roles']['dev']
    marker.write_text(json.dumps(config), encoding='utf-8')
    try:
        setup.setup(tmp, local_only=True)
    except ValueError as error:
        assert '중복' in str(error)
    else:
        raise AssertionError('duplicate role branches accepted')

print('PASS: product/implementation/unresolved routing, audited override, dispatch gates, patch bodies, branch aliases')
