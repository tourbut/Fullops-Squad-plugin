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
        finally:
            jev.subprocess.run = original

        # 키 찾는 순서: --env-file → 환경 변수 → 레포 루트 .env
        repo = Path(tmp) / 'repo'
        repo.mkdir()
        saved = os.environ.pop('OPENROUTER_API_KEY', None)
        try:
            assert jev.api_key(None, repo) == ''
            (repo / '.env').write_text('OTHER=1\nOPENROUTER_API_KEY="sk-or-from_dotenv"\n', encoding='utf-8')
            assert jev.api_key(None, repo) == 'sk-or-from_dotenv'
            os.environ['OPENROUTER_API_KEY'] = 'sk-or-from_env'
            assert jev.api_key(None, repo) == 'sk-or-from_env'
            other = Path(tmp) / 'keys.env'
            other.write_text('OPENROUTER_API_KEY=sk-or-from_file\n', encoding='utf-8')
            assert jev.api_key(str(other), repo) == 'sk-or-from_file'
            (repo / '.env').write_text('OTHER=1\n', encoding='utf-8')
            del os.environ['OPENROUTER_API_KEY']
            assert jev.api_key(None, repo) == ''  # 키 줄이 없으면 Jev 없이 진행
        finally:
            os.environ.pop('OPENROUTER_API_KEY', None)
            if saved is not None:
                os.environ['OPENROUTER_API_KEY'] = saved
    print('PASS: jev request closes and removes body file, key via stdin, cache hit, key lookup order')


if __name__ == '__main__':
    main()
