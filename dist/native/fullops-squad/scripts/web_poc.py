#!/usr/bin/env python3
"""기본 OFF인 CUAWright host-skill PoC를 준비한다. 모델·생성 코드·desktop runtime을 자동 실행하지 않는다."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

import deps
from frontend import local_file
from jev_route import fixed_model
from jev_test_web import problems
from storage import write_json
from work import active_repo


def skill():
    return next(s for s in deps.manifest()['optional_skills'] if s['names'] == ['cuawright-web'])


def runtime(python):
    code = "import importlib.metadata,json;from pathlib import Path;from playwright.sync_api import sync_playwright;" \
           "p=sync_playwright().start();print(json.dumps({'playwright':importlib.metadata.version('playwright'),'firefox_installed':Path(p.firefox.executable_path).is_file()}));p.stop()"
    try:
        result = subprocess.run([python, '-c', code], capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout) if result.returncode == 0 else {'playwright': None, 'firefox_installed': False}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {'playwright': None, 'firefox_installed': False}


def prepare(repo, key, scenario, host, model, effort, python, max_tokens, dry_run=True):
    tuple_ = fixed_model(host, model, effort)
    if tuple_ is None or host not in deps.COMMON_HOSTS:
        raise ValueError('CUAWright PoC requires an explicit supported host/model/effort tuple')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', key):
        raise ValueError('invalid task key')
    found = problems(scenario)
    if found or not scenario.get('safety', {}).get('fixture'):
        raise ValueError('PoC requires a valid isolated-fixture scenario: ' + ', '.join(found))
    if type(max_tokens) is not int or not 1 <= max_tokens <= 1000000:
        raise ValueError('max_tokens must be 1..1000000')
    command = deps.skill_command(skill(), [host])
    if dry_run:
        return {'enabled': False, 'status': 'disabled', 'optional_install': command,
                'writes': ['new PoC brief/metadata only when --prepare is supplied'], 'generation': 'not_run'}
    paths, absent = deps.skill_files(host, [skill()])
    checked = runtime(python)
    ready = not absent and checked['playwright'] and checked['firefox_installed']
    out = local_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-test/cuawright-poc-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}')
    out.mkdir(parents=True, exist_ok=False)
    result = {'version': 'cuawright-poc-v1', 'enabled': True, 'status': 'UNVERIFIED' if ready else 'BLOCKED',
              'host_tuple': tuple_, 'skill': {'source': skill()['source'], 'files': paths, 'problems': absent},
              'runtime': checked, 'python': python, 'max_seconds': scenario.get('max_seconds', 120), 'max_tokens': max_tokens,
              'budget_enforcement': 'host session and isolated runtime must enforce; this preparer launches neither',
              'generation': 'not_run', 'code_review': 'not_run', 'independent_assertions': 'not_run', 'visual_review': 'not_run',
              'optional_install': command, 'workspace': out.relative_to(repo).as_posix()}
    write_json(out / 'poc.json', result)
    write_json(out / 'scenario.json', scenario)
    (out / 'plan.md').write_text(
        '# CUAWright 선택형 웹 PoC\n\n'
        f'호스트/모델/effort: {host} / {model} / {effort}\n\n'
        '1. 연결된 최신 cuawright-web 스킬을 읽고 host-native 방식으로 수행한다. 별도 모델 API 키를 추가하지 않는다.\n'
        '2. scenario.json의 목표·fixture·origin·허용 동작·금지 효과·독립 checks가 정본이다. 이 폴더 안에서만 생성한다.\n'
        '3. 시간/토큰 예산을 호스트에서 먼저 설정·확인한다. 설정할 수 없으면 BLOCKED로 남긴다.\n'
        '4. plan.md의 수락 조건을 구체화하고 final_runs/run_<id>/final_script.py와 로그·캡처를 남긴다.\n'
        '5. 생성 코드는 실행 전 고정 SHA 독립 리뷰를 받는다. 격리 tenant와 네트워크 제한을 확인한 런타임에서만 실행한다.\n'
        '6. 별도 선택된 시각 검수 경로로 캡처를 확인한다. Jev에 이미지 판정을 요청하지 않는다.\n'
        '7. 사전에 정한 checks를 독립 실행하고 PASS/FAIL/BLOCKED/UNVERIFIED와 근거를 poc.json에 기록한다. 자체 성공 주장은 PASS가 아니다.\n'
        '8. 유용한 경로는 web_analysis.py --promote 또는 프로젝트 Playwright E2E로 승격·재생한다. 모델이 회귀 필수 의존성이 되지 않는다.\n\n'
        '기존 확정 회귀·보안·lint·done/review 게이트는 계속 실행한다. desktop·VM·자율 외부 업로드는 이 PoC 범위 밖이다.\n', encoding='utf-8', newline='\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--host', choices=deps.COMMON_HOSTS, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--effort', required=True)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--max-tokens', type=int, default=20000)
    parser.add_argument('--prepare', action='store_true', help='별도 PoC 지시서/메타데이터 생성; 기본은 계획만 출력')
    parser.add_argument('--install-skill', action='store_true', help='현재 선택 호스트에만 선택 스킬 설치; 브라우저/Python 설치는 별도')
    args = parser.parse_args()
    repo = active_repo(args.repo)
    scenario = json.loads(args.scenario.read_text(encoding='utf-8'))
    # 입력을 전부 검증한 뒤에만 선택 설치를 실행한다.
    result = prepare(repo, args.key, scenario, args.host, args.model, args.effort, args.python, args.max_tokens)
    if args.install_skill:
        command = result['optional_install']
        deps.backup_skills(args.host, command)
        deps.run([command], False)
    if args.prepare:
        result = prepare(repo, args.key, scenario, args.host, args.model, args.effort, args.python, args.max_tokens, dry_run=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    sys.exit(main())
