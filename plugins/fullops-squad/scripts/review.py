#!/usr/bin/env python3
"""OCR delegate 준비와 리뷰 기록 검증. LLM 호출·병합은 실행하지 않는다."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from work import active_repo, safe_file, KEY


def sha(repo, ref):
    if ref.startswith('-'):
        raise ValueError('Git 옵션을 ref로 사용할 수 없습니다')
    return subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--verify', ref + '^{commit}'], text=True).strip()


def rule_hash(rule):
    return hashlib.sha256(rule.read_bytes()).hexdigest()


def prepare(repo, key, base, head):
    rule = safe_file(repo, '.fullops-squad/review/rule.json')
    destination = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-review')
    if destination.exists():
        raise ValueError('기존 리뷰는 보존합니다. 새로운 리뷰 키를 사용하세요')
    base, head = sha(repo, base), sha(repo, head)
    digest = rule_hash(rule)
    env = dict(os.environ, OCR_NO_UPDATE='1')
    options = ['--repo', str(repo), '--from', base, '--to', head, '--rule', str(rule), '--format', 'json']
    def ocr(*args):
        return json.loads(subprocess.check_output(['ocr', 'delegate', *args, *options], text=True, env=env))
    preview = ocr('preview')
    if preview.get('schema_version') != '1':
        raise ValueError('지원하지 않는 OCR preview 스키마')
    paths = [item['path'] for item in preview['reviewable_files']]
    if any(p.startswith('-') for p in paths):
        raise ValueError('옵션과 혼동되는 파일명은 직접 검토하세요')
    rules = ocr('rule', *paths) if paths else {'schema_version': '1', 'groups': []}
    if rules.get('schema_version') != '1' or digest != rule_hash(rule):
        raise ValueError('규칙 스키마 또는 실행 중 규칙 변경을 확인하세요')
    version = subprocess.check_output(['ocr', '--version'], text=True, env=env).strip()
    result = {'base': base, 'head': head, 'rule_sha256': digest, 'ocr_version': version,
              'reviewer': '', 'conclusion': '',
              'files': [{**item, 'review_status': 'pending', 'reason': ''}
                        for item in preview['reviewable_files'] + preview['excluded_files']],
              'findings': []}
    destination.mkdir(parents=True)
    for name, data in [('preview', preview), ('rules', rules), ('result', result)]:
        (destination / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    template = Path(__file__).resolve().parents[1] / 'assets/repository/.fullops-squad/review/_REPORT.md'
    (destination / 'report.md').write_text(template.read_text().replace('<과제 키>', key, 1))
    print(destination.relative_to(repo))


def check(repo, key, base, head):
    directory = f'.fullops-squad/docs/evaluations/qa-reports/{key}-review'
    def read(name):
        return json.loads(safe_file(repo, f'{directory}/{name}.json').read_text())
    preview, result = read('preview'), read('result')
    if (result['base'], result['head']) != (sha(repo, base), sha(repo, head)):
        raise ValueError('base/head가 변경됐습니다. 새 리뷰를 준비하세요')
    if (preview['from'], preview['to']) != (result['base'], result['head']):
        raise ValueError('preview와 리뷰 SHA가 다릅니다')
    if result['rule_sha256'] != rule_hash(safe_file(repo, '.fullops-squad/review/rule.json')):
        raise ValueError('리뷰 규칙이 변경됐습니다')
    expected = [(f['path'], f['status']) for f in preview['reviewable_files'] + preview['excluded_files']]
    actual = [(f['path'], f['status']) for f in result['files']]
    if sorted(expected) != sorted(actual):
        raise ValueError('검토 파일 누락·중복·추가를 확인하세요')
    for item in result['files']:
        if item['review_status'] not in ('reviewed', 'skipped') or not item['reason'].strip():
            raise ValueError('모든 파일에 검토 상태와 근거/생략 사유를 기록하세요')
    if not result['reviewer'].strip() or not result['conclusion'].strip():
        raise ValueError('검토자와 결론을 기록하세요')
    for finding in result['findings']:
        if finding.get('severity') not in ('critical', 'high', 'medium', 'low') or type(finding.get('resolved')) is not bool:
            raise ValueError('발견 사항에 severity와 resolved(boolean)를 기록하세요')
        if finding['severity'] in ('critical', 'high') and not finding['resolved']:
            raise ValueError('critical/high 미해결 사항이 있습니다')
    lint = read('lint')
    if (lint['base'], lint['head']) != (result['base'], result['head']):
        raise ValueError('lint 결과의 base/head가 리뷰와 다릅니다. worker 체크아웃에서 lint.py를 다시 실행하세요')
    config = subprocess.run(['git', '-C', str(repo), 'cat-file', 'blob', f"{result['head']}:.fullops-squad/lint/lint.json"],
                            capture_output=True)
    if lint['config_sha256'] != (hashlib.sha256(config.stdout).hexdigest() if config.returncode == 0 else None):
        raise ValueError('lint 설정이 head와 다릅니다')
    if any(c['status'] == 'unavailable' and not c.get('reason', '').strip() for c in lint['commands']):
        raise ValueError('실행 불가 lint 명령에 reason을 기록하세요')
    errors = (sum(v['severity'] == 'ERROR' for v in lint['violations'])
              + sum(c['status'] in ('failed', 'timeout') for c in lint['commands']))
    if errors:
        raise ValueError(f'lint ERROR {errors}건이 남아 있습니다. 수정 커밋 후 새 리뷰를 준비하세요')
    reviewed = sum(f['review_status'] == 'reviewed' for f in result['files'])
    print(f'기록 검사 통과: reviewed={reviewed}, skipped={len(actual)-reviewed}, total={len(actual)}, '
          f"lint WARNING={lint['summary']['warnings']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'check'])
    for option in ['repo', 'key', 'from', 'to']:
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        (prepare if args.mode == 'prepare' else check)(repo, args.key, getattr(args, 'from'), args.to)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'리뷰 처리 실패: {error}\n')


if __name__ == '__main__':
    main()
