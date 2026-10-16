"""가짜 curl로 Jev 요청의 본문 파일 전달(Windows 잠금 없음·삭제)·키 표준입력 전달·캐시와 키 찾는 순서를 확인한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import jev_observe as jev  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-jev-request-') as tmp:
        os.environ['FULLOPS_JEV_CACHE'] = str(Path(tmp) / 'cache')
        seen = {}

        def fake_run(argv, input=None, **kwargs):
            body = argv[argv.index('--data-binary') + 1][1:]
            with open(body, encoding='utf-8') as handle:  # Windows에서 잠겨 있으면 여기서 실패한다
                seen['payload'] = json.load(handle)
            seen['body'], seen['argv'], seen['stdin'] = body, argv, input
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({'model': 'jev-test', 'answers': {}}), stderr='')

        original = jev.subprocess.run
        jev.subprocess.run = fake_run
        try:
            response, _ = jev.request({'model': 'm', 'questions': {'q': 1}}, 'sk-or-test_KEY-1')
            assert response['model'] == 'jev-test' and seen['payload'] == {'model': 'm', 'questions': {'q': 1}}
            assert not Path(seen['body']).exists()  # 본문 파일은 지운다
            assert 'sk-or-test_KEY-1' in seen['stdin'] and not any('sk-or-test' in a for a in seen['argv'])  # 키는 명령줄에 없다
            seen.clear()
            cached, _ = jev.request({'model': 'm', 'questions': {'q': 1}}, 'sk-or-test_KEY-1')
            assert cached.get('cached') and not seen  # 같은 요청은 캐시에서
            path = jev.cache_path({'model': 'm', 'questions': {'q': 1}})
            path.write_text(json.dumps({'note': 'TOKEN=synthetic-sensitive-value'}), encoding='utf-8')
            safe, _ = jev.request({'model': 'm', 'questions': {'q': 1}}, 'sk-or-test_KEY-1')
            assert not safe.get('cached') and seen  # 민감 문자열이 든 캐시는 반환·재사용하지 않는다.
            assert 'synthetic-sensitive-value' not in path.read_text()
            # 공식 API 키는 공식 endpoint·모델 ID로 보내고, OpenRouter 키는 기존 형식 그대로 보낸다.
            os.environ['FULLOPS_JEV_CACHE_BYPASS'] = '1'
            request = {'model': jev.MODEL, 'state': 's', 'questions': {'q': 1}}
            jev.request(request, jev.Key.of('ts-test_KEY', 'typesafe'))
            assert seen['argv'][-1] == 'https://api.typesafe.ai/v1/systemone' and seen['payload']['model'] == 'jev-latest'
            assert 'ts-test_KEY' in seen['stdin'] and not any('ts-test' in a for a in seen['argv'])
            jev.request(request, 'sk-or-test_KEY-1')
            assert seen['argv'][-1] == jev.URL and seen['payload']['model'] == jev.MODEL
            jev.subprocess.run = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stderr='', stdout=json.dumps(
                {'model': 'jev-1.13.0', 'answers': {}, 'usage': {'input_tokens': 3, 'output_tokens': 1}}))
            filled, _ = jev.request(request, jev.Key.of('ts-test_KEY', 'typesafe'))
            assert filled['usage']['cost'] == 0  # 공식 API는 비용을 보고하지 않는다
            del os.environ['FULLOPS_JEV_CACHE_BYPASS']
        finally:
            jev.subprocess.run = original

        # 공식 API는 jev-<버전>, OpenRouter는 typesafe/jev-<버전>으로 답한다. 공식 API 응답에는 cost가 없다.
        for model in ('jev-1.13.0', 'typesafe/jev-1.13.0'):
            jev.validated(({'model': model, 'answers': {}, 'usage': {'input_tokens': 1, 'output_tokens': 1, 'cost': 0}}, 0.1), {})
        for model in ('gpt-4', 'jev', 'other/jev-1'):
            try:
                jev.validated(({'model': model, 'answers': {}, 'usage': {'input_tokens': 1, 'output_tokens': 1, 'cost': 0}}, 0.1), {})
            except ValueError:
                continue
            raise AssertionError(model)

        # 키 찾는 순서: --env-file → 환경 변수 → .fullops-squad/.env. 같은 출처에서는 공식 API 키가 우선한다.
        repo = Path(tmp) / 'repo'
        (repo / '.fullops-squad').mkdir(parents=True)
        saved = os.environ.pop('OPENROUTER_API_KEY', None)
        saved_typesafe = os.environ.pop('TYPESAFE_API_KEY', None)
        try:
            assert jev.api_key(None, repo) == ''
            (repo / '.env').write_text('OTHER=1\nOPENROUTER_API_KEY="sk-or-from_dotenv"\n', encoding='utf-8')
            assert jev.api_key(None, repo) == ''  # 옛 레포 루트 파일은 읽지 않는다
            local = repo / '.fullops-squad' / '.env'
            local.write_text('OTHER=1\nOPENROUTER_API_KEY="sk-or-from_dotenv"\n', encoding='utf-8')
            assert jev.api_key(None, repo) == 'sk-or-from_dotenv'
            os.environ['OPENROUTER_API_KEY'] = 'sk-or-from_env'
            assert jev.api_key(None, repo) == 'sk-or-from_env'
            other = Path(tmp) / 'keys.env'
            other.write_text('OPENROUTER_API_KEY=sk-or-from_file\n', encoding='utf-8')
            assert jev.api_key(str(other), repo) == 'sk-or-from_file'
            assert jev.api_key(str(other), repo).provider == 'openrouter'
            other.write_text('OPENROUTER_API_KEY=sk-or-from_file\nTYPESAFE_API_KEY=ts-from_file\n', encoding='utf-8')
            found = jev.api_key(str(other), repo)
            assert found == 'ts-from_file' and found.provider == 'typesafe'
            os.environ['TYPESAFE_API_KEY'] = 'ts-from_env'
            found = jev.api_key(None, repo)
            assert found == 'ts-from_env' and found.provider == 'typesafe'  # 둘 다 있으면 공식 API
            del os.environ['TYPESAFE_API_KEY']
            local.write_text('OTHER=1\n', encoding='utf-8')
            del os.environ['OPENROUTER_API_KEY']
            assert jev.api_key(None, repo) == ''  # 키 줄이 없으면 Jev 없이 진행
            local.write_text('TYPESAFE_API_KEY=ts-from_dotenv\n', encoding='utf-8')
            assert jev.api_key(None, repo).provider == 'typesafe'
        finally:
            os.environ.pop('OPENROUTER_API_KEY', None)
            os.environ.pop('TYPESAFE_API_KEY', None)
            if saved is not None:
                os.environ['OPENROUTER_API_KEY'] = saved
            if saved_typesafe is not None:
                os.environ['TYPESAFE_API_KEY'] = saved_typesafe
    print('PASS: jev request closes and removes body file, key via stdin, cache hit, key lookup order, TypeSafe/OpenRouter providers')


if __name__ == '__main__':
    main()
