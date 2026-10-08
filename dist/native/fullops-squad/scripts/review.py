#!/usr/bin/env python3
"""OCR delegate 준비와 리뷰 기록 검증. LLM 호출·병합은 실행하지 않는다."""
import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
import subprocess
import uuid

import jev_find
from lint import load_config
from jev_route import product_roles
from work import active_repo, safe_file, KEY
from storage import write_json, atomic_write


def ocr_command():
    return shutil.which('ocr') or 'ocr'  # Windows의 ocr.cmd


def sha(repo, ref):
    if ref.startswith('-'):
        raise ValueError('Git 옵션을 ref로 사용할 수 없습니다')
    return subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--verify', ref + '^{commit}'], text=True).strip()


def rule_hash(rule):
    return hashlib.sha256(rule.read_bytes()).hexdigest()


EVIDENCE = '.fullops-squad/docs/evaluations/qa-reports/'
EVIDENCE_REASON = ('검증 증거(rule.json exclude). 파일마다 열람하지 않고 같은 폴더의 manifest·result.json·report.md로 '
                   '존재와 무결성을 확인한다.')


def evidence(path):
    """OCR이 제외한 파일 중 검증 증거. 리뷰어가 수백 개에 같은 사유를 적지 않게 prepare가 미리 채운다."""
    return path.startswith(EVIDENCE) or path.endswith('.bak')


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
        return json.loads(subprocess.check_output([ocr_command(), 'delegate', *args, *options], text=True, env=env))
    preview = ocr('preview')
    if preview.get('schema_version') != '1':
        raise ValueError('지원하지 않는 OCR preview 스키마')
    paths = [item['path'] for item in preview['reviewable_files']]
    if any(p.startswith('-') for p in paths):
        raise ValueError('옵션과 혼동되는 파일명은 직접 검토하세요')
    rules = ocr('rule', *paths) if paths else {'schema_version': '1', 'groups': []}
    if rules.get('schema_version') != '1' or digest != rule_hash(rule):
        raise ValueError('규칙 스키마 또는 실행 중 규칙 변경을 확인하세요')
    version = subprocess.check_output([ocr_command(), '--version'], text=True, env=env).strip()
    result = {'base': base, 'head': head, 'rule_sha256': digest, 'ocr_version': version,
              'reviewer': '', 'conclusion': '',
              'files': [{**item, 'review_status': 'pending', 'reason': ''} for item in preview['reviewable_files']] +
                       [{**item, 'review_status': 'skipped', 'reason': EVIDENCE_REASON} if evidence(item['path']) else
                        {**item, 'review_status': 'pending', 'reason': ''} for item in preview['excluded_files']],
              'findings': []}
    managed = snapshot_record(repo, key)
    if product_roles(repo) or managed.is_file():
        preview['fullops_review_schema_version'] = 2
        result.update(review_schema_version=2, independence={'implementer_session': '', 'reviewer_session': '',
                      'snapshot_path': '', 'snapshot_head': head, 'read_only': True})
        if managed.is_file():
            saved = json.loads(managed.read_text(encoding='utf-8'))
            if saved.get('managed') is not True or saved.get('key') != key or saved.get('head') != head or saved.get('state') != 'active':
                raise ValueError('관리 snapshot의 과제·SHA·활성 상태가 다릅니다')
            result['independence'].update(snapshot_path=saved['path'], implementer_session=saved['implementer_session'],
                                          reviewer_session=saved['reviewer_session'])
            check_independence(repo, result)
    destination.mkdir(parents=True)
    for name, data in [('preview', preview), ('rules', rules), ('result', result)]:
        (destination / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    template = Path(__file__).resolve().parents[1] / 'assets/repository/.fullops-squad/review/_REPORT.md'
    (destination / 'report.md').write_text(template.read_text().replace('<과제 키>', key, 1))
    print(destination.relative_to(repo))


def check_independence(repo, result):
    """새 책임 구조의 리뷰 기록: 독립 세션과 깨끗한 고정 SHA detached snapshot을 확인한다."""
    if result.get('review_schema_version') is None:
        return  # 전환 전 고정 리뷰 원본은 보존한다
    if result['review_schema_version'] != 2:
        raise ValueError('지원하지 않는 FullOps 리뷰 스키마')
    record = result.get('independence') or {}
    author, reviewer = record.get('implementer_session'), record.get('reviewer_session')
    if not isinstance(author, str) or not author.strip() or not isinstance(reviewer, str) or not reviewer.strip() or author.strip() == reviewer.strip():
        raise ValueError('구현자와 독립 검토자의 서로 다른 세션 ID를 기록하세요')
    if not record.get('snapshot_path') or record.get('read_only') is not True:
        raise ValueError('읽기 전용 snapshot 경로와 read_only를 기록하세요')
    snapshot = Path(record['snapshot_path']).resolve(strict=True)
    if snapshot == Path(repo).resolve() or record.get('snapshot_head') != result['head'] or sha(snapshot, 'HEAD') != result['head']:
        raise ValueError('별도 snapshot의 고정 head가 리뷰와 다릅니다')
    if Path(subprocess.check_output(['git', '-C', str(snapshot), 'rev-parse', '--show-toplevel'], text=True).strip()).resolve() != snapshot:
        raise ValueError('snapshot_path는 Git 체크아웃 루트여야 합니다')
    if subprocess.run(['git', '-C', str(snapshot), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode != 1:
        raise ValueError('snapshot은 detached HEAD여야 합니다')
    if subprocess.check_output(['git', '-C', str(snapshot), 'status', '--porcelain']).strip():
        raise ValueError('읽기 전용 snapshot에 변경이 있습니다')


def snapshot_record(repo, key):
    from integration import directory
    return directory(repo).parent / 'fullops-snapshots' / f'{key}.json'


def snapshot(repo, key, head, implementer, reviewer, owner):
    """FullOps가 만든 임시 Git worktree만 기록한다. 사용자 clone/상설 공간은 소유하지 않는다."""
    if not implementer or not reviewer or implementer == reviewer or not owner:
        raise ValueError('독립 세션 두 개와 정리 담당을 지정하세요')
    record = snapshot_record(repo, key)
    if record.exists():
        raise ValueError('기존 snapshot 기록을 보존합니다. 새 리뷰 키를 사용하세요')
    head = sha(repo, head)
    path = Path(repo).parent / f'.fullops-review-{uuid.uuid4().hex}'
    data = {'schema_version': 1, 'kind': 'git-worktree', 'managed': True, 'purpose': 'review',
            'key': key, 'repository': str(Path(repo).resolve()), 'path': str(path), 'head': head,
            'implementer_session': implementer, 'reviewer_session': reviewer, 'owner': owner,
            'evidence': f'.fullops-squad/docs/evaluations/qa-reports/{key}-review', 'state': 'creating'}
    write_json(record, data)  # 생성 성공 후 기록 쓰기 실패에도 소유권을 잃지 않는다.
    subprocess.check_call(['git', '-C', str(repo), 'worktree', 'add', '--detach', str(path), head],
                          stdout=subprocess.DEVNULL)
    write_json(record, {**data, 'state': 'active'})
    print(path)
    return path


def evidence_hashes(repo, key):
    folder = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-review')
    files = [safe_file(repo, p.relative_to(repo)) for p in sorted(folder.rglob('*'))]
    if not all((folder / name).is_file() for name in ('preview.json', 'rules.json', 'result.json', 'lint.json', 'report.md')):
        raise ValueError('snapshot 밖 정본 증거가 빠졌습니다')
    if not (folder / 'report.md').read_text(encoding='utf-8').strip():
        raise ValueError('빈 리뷰 보고서')
    return {p.relative_to(folder).as_posix(): rule_hash(p) for p in files
            if p.is_file() and p.name != 'snapshot-cleanup.json'}


def historical(repo, key):
    receipt = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-review/snapshot-cleanup.json')
    data = json.loads(receipt.read_text(encoding='utf-8'))
    if data.get('state') != 'removed' or data.get('live_check') != 'passed' or data.get('evidence_sha256') != evidence_hashes(repo, key):
        raise ValueError('완료 후 보존 증거의 정체성이 다릅니다. live snapshot에서 다시 검증하세요')
    result = json.loads(receipt.with_name('result.json').read_text(encoding='utf-8'))
    if (data['base'], data['head']) != (result['base'], result['head']) or data.get('independence') != result.get('independence'):
        raise ValueError('정리 기록과 독립 리뷰 정체성이 다릅니다')
    return data


def cleanup(repo, key, dispatch, finished=False):
    from integration import orca
    record = snapshot_record(repo, key)
    data = json.loads(record.read_text(encoding='utf-8'))
    if data.get('state') == 'removed':
        historical(repo, key)
        return  # 동일 정리 재시도는 멱등이다.
    path = Path(data['path'])
    try:
        if not finished or not dispatch:
            raise ValueError('리뷰·수락·재검증 완료(--finished)와 reviewer dispatch가 필요합니다')
        if data.get('managed') is not True or data.get('kind') != 'git-worktree' or data.get('purpose') != 'review' or data.get('key') != key:
            raise ValueError('FullOps 소유의 임시 Git worktree가 아닙니다')
        if Path(data['repository']).resolve() != Path(repo).resolve() or path.resolve().parent != Path(repo).resolve().parent or not path.name.startswith('.fullops-review-'):
            raise ValueError('관리 경로 정체성이 다릅니다')
        result_path = safe_file(repo, data['evidence'] + '/result.json')
        result = json.loads(result_path.read_text(encoding='utf-8'))
        independence = result.get('independence') or {}
        if independence.get('snapshot_path') != str(path) or result['head'] != data['head'] or any(
                independence.get(k) != data[k] for k in ('implementer_session', 'reviewer_session')):
            raise ValueError('생성 기록과 리뷰 정체성이 다릅니다')
        def inactive():
            status = orca('orchestration', 'worker-read', '--dispatch', dispatch, '--source', 'terminal', '--limit', '1', cwd=repo)
            if not status or status.get('archived') is not True or (status.get('status') or {}).get('worker') != 'released' or (status.get('status') or {}).get('liveness') not in ('dead', 'exited', 'closed'):
                raise ValueError('Orca에서 reviewer release와 terminal 종료를 확인하지 못했습니다')
            workspace = ((status.get('projection') or {}).get('workspace') or {}).get('id')
            workspace_path = str(workspace or '').split('::', 1)[-1]
            if not workspace_path or Path(workspace_path).resolve() != path.resolve() or (data.get('dispatch') and data['dispatch'] != dispatch):
                raise ValueError('release한 dispatch가 해당 snapshot의 reviewer인지 확인하지 못했습니다')
            return status
        released = inactive()
        data['dispatch'] = dispatch
        write_json(record, data)
        receipt = safe_file(repo, data['evidence'] + '/snapshot-cleanup.json')
        if receipt.is_file() and not path.exists():
            saved = json.loads(receipt.read_text(encoding='utf-8'))
            listed = subprocess.check_output(['git', '-C', str(repo), 'worktree', 'list', '--porcelain'], text=True)
            if saved.get('live_check') != 'passed' or saved.get('evidence_sha256') != evidence_hashes(repo, key) or saved.get('independence') != independence or f'worktree {path}\n' in listed:
                raise ValueError('중단된 정리의 증거/등록 경로를 확인하세요')
            write_json(receipt, {**saved, 'state': 'removed'})
            write_json(record, {**data, 'state': 'removed'})
            return
        check(repo, key, result['base'], result['head'])  # 신규 수락은 항상 live 검사한다.
        hashes = evidence_hashes(repo, key)
        receipt = safe_file(repo, data['evidence'] + '/snapshot-cleanup.json')
        saved = {'base': result['base'], 'head': result['head'], 'independence': independence,
                 'live_check': 'passed', 'evidence_sha256': hashes, 'released_dispatch': dispatch,
                 'release_observation': released, 'state': 'validated'}
        write_json(receipt, saved)
        check_independence(repo, result)
        inactive()
        if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--ignored', '--untracked-files=all']).strip():
            raise ValueError('snapshot의 미커밋·미추적·ignored 고유 파일을 보존하세요')
        subprocess.check_call(['git', '-C', str(repo), 'worktree', 'remove', str(path)])  # --force 사용 금지
        write_json(receipt, {**saved, 'state': 'removed'})
        write_json(record, {**data, 'state': 'removed'})
    except Exception as error:
        try:
            write_json(record, {**data, 'hold': {'reason': str(error), 'owner': data.get('owner'),
                       'resume': '증거·clean 상태·reviewer release를 확인하고 같은 cleanup 명령을 재시도'}})
        except OSError:
            pass  # 기록 저장 실패가 원래 거부 원인을 가리지 않는다.
        raise


def check(repo, key, base, head, task_key=None):
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
    if preview.get('fullops_review_schema_version') == 2 and result.get('review_schema_version') != 2:
        raise ValueError('독립 리뷰 스키마를 유지하세요')
    check_independence(repo, result)
    for finding in result['findings']:
        if finding.get('severity') not in ('critical', 'high', 'medium', 'low') or type(finding.get('resolved')) is not bool:
            raise ValueError('발견 사항에 severity와 resolved(boolean)를 기록하세요')
        if finding['severity'] in ('critical', 'high') and not finding['resolved']:
            raise ValueError('critical/high 미해결 사항이 있습니다')
    lint = read('lint')
    if (lint['base'], lint['head']) != (result['base'], result['head']):
        raise ValueError('lint 결과의 base/head가 리뷰와 다릅니다. worker 체크아웃에서 lint.py를 다시 실행하세요')
    merge_base = subprocess.check_output(['git', '-C', str(repo), 'merge-base', result['base'], result['head']],
                                         text=True).strip()
    config = subprocess.run(['git', '-C', str(repo), 'cat-file', 'blob', f'{merge_base}:.fullops-squad/lint/lint.json'],
                            capture_output=True)
    if lint.get('merge_base') != merge_base or lint['config_sha256'] != (
            hashlib.sha256(config.stdout).hexdigest() if config.returncode == 0 else None):
        raise ValueError('lint 설정이 merge-base와 다릅니다. worker 브랜치의 설정 변경은 병합 후 적용됩니다')
    settings, _ = load_config(repo, merge_base)
    for command in (c for c in settings['commands'] if c.get('kind') == 'test'):
        records = [c for c in lint['commands'] if c.get('kind') == 'test' and c['name'] == command['name']
                   and c.get('run') == command['run'] and c.get('cwd', '.') == command.get('cwd', '.')]
        if len(records) != 1:
            raise ValueError(f'등록된 테스트 실행 증거가 없거나 중복됐습니다: {command["name"]}')
        if records[0]['status'] == 'passed' and records[0].get('exit_code') != 0:
            raise ValueError(f'테스트 통과 종료코드가 없습니다: {command["name"]}')
        if records[0]['status'] not in ('passed', 'failed', 'timeout', 'unavailable'):
            raise ValueError(f'테스트가 실행되지 않았습니다: {command["name"]}')
    if any(c['status'] == 'unavailable' and not c.get('reason', '').strip() for c in lint['commands']):
        raise ValueError('실행 불가 lint 명령에 reason을 기록하세요')
    errors = (sum(v['severity'] == 'ERROR' for v in lint['violations'])
              + sum(c['status'] in ('failed', 'timeout') for c in lint['commands']))
    if errors:
        raise ValueError(f'lint ERROR {errors}건이 남아 있습니다. 수정 커밋 후 새 리뷰를 준비하세요')
    packet_key = task_key or key
    packet_path = jev_find.result_path(repo, packet_key, 'packet')
    committed = subprocess.run(['git', '-C', str(repo), 'show', f'{head}:{packet_path.relative_to(repo).as_posix()}'], capture_output=True, text=True)
    route_path = jev_find.result_path(repo, packet_key, 'route')
    if packet_path.is_file() or committed.returncode == 0 or (route_path.is_file() and json.loads(route_path.read_text()).get('requires_packet')):
        from jev_packet import check as check_packet
        if committed.returncode != 0:
            raise ValueError('리뷰할 SHA에 탐색 패킷이 없습니다')
        packet = json.loads(committed.stdout)
        role = packet['role']
        content = subprocess.check_output(['git', '-C', str(repo), 'show', f'{head}:.fullops-squad/handovers/to_{role}.md'], text=True)
        if not content.strip():
            token = f'<!-- fullops-attempt: {packet_key} {packet["attempt"]} -->'
            for path in subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-r', '--name-only', head, '--', '.fullops-squad/handovers/logs'], text=True).splitlines():
                log = subprocess.check_output(['git', '-C', str(repo), 'show', f'{head}:{path}'], text=True)
                if token in log:
                    content = re.split(r'\n## [A-Za-z0-9][A-Za-z0-9._-]* — \d{4}-\d{2}-\d{2}\n<!-- fullops-attempt:', log.split(token, 1)[1], maxsplit=1)[0].strip()
                    break
        check_packet(repo, role, packet_key, completion=True, required=True, head=head, text=content)
    record_find_score(repo, directory, packet_key, result['base'], result['head'])
    reviewed = sum(f['review_status'] == 'reviewed' for f in result['files'])
    print(f'기록 검사 통과: reviewed={reviewed}, skipped={len(actual)-reviewed}, total={len(actual)}, '
          f"lint WARNING={lint['summary']['warnings']}")


def record_find_score(repo, directory, task_key, base, head):
    """과제의 jev_find 결과가 있으면 실제 변경과 비교한 적중률을 남긴다. 수락 판단에는 쓰지 않는다."""
    labels_path = jev_find.result_path(repo, task_key, 'packet-labels')
    labels = json.loads(labels_path.read_text()) if labels_path.is_file() else None
    for scope, suffix in [('code', 'find'), ('documents', 'documents-find')]:
        if not jev_find.result_path(repo, task_key, suffix).is_file():
            continue
        try:
            scored = jev_find.score(repo, task_key, base, head, scope, labels)
        except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
            print(f'jev_find {scope} score 생략: {error}')
            continue
        destination = safe_file(repo, f'{directory}/jev-{suffix}-score.json')
        value = json.dumps(scored, ensure_ascii=False, indent=2) + '\n'
        if not destination.is_file() or destination.read_text() != value:
            atomic_write(destination, value)
        print(f"jev_find score ({scope} changed-file overlap): recall {scored['recall']} / precision {scored['precision']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'check', 'snapshot', 'cleanup'])
    for option in ['repo', 'key']:
        parser.add_argument('--' + option, required=True)
    for option in ['from', 'to', 'implementer-session', 'reviewer-session', 'owner', 'dispatch']:
        parser.add_argument('--' + option)
    parser.add_argument('--finished', action='store_true', help='cleanup: 리뷰·수락·필요 재검증 완료')
    parser.add_argument('--historical', action='store_true', help='check: 과거 완료 증거만 확인; 신규 수락에 사용 금지')
    parser.add_argument('--task-key', help='check: jev_find 결과의 과제 키 (기본: 리뷰 키)')
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        if args.mode == 'snapshot':
            if not args.to:
                raise ValueError('--to가 필요합니다')
            snapshot(repo, args.key, args.to, args.implementer_session, args.reviewer_session, args.owner)
        elif args.mode == 'cleanup':
            cleanup(repo, args.key, args.dispatch, args.finished)
        elif args.historical:
            data = historical(repo, args.key)
            if args.mode != 'check' or (args.to and sha(repo, args.to) != data['head']) or (getattr(args, 'from') and sha(repo, getattr(args, 'from')) != data['base']):
                raise ValueError('historical은 보존된 SHA의 check에만 사용하세요')
            print('과거 완료 증거 확인: 신규 수락 아님')
        elif not getattr(args, 'from') or not args.to:
            raise ValueError('--from과 --to가 필요합니다')
        elif args.mode == 'prepare':
            prepare(repo, args.key, getattr(args, 'from'), args.to)
        else:
            if args.task_key and not KEY.fullmatch(args.task_key):
                raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
            check(repo, args.key, getattr(args, 'from'), args.to, args.task_key)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'리뷰 처리 실패: {error}\n')


if __name__ == '__main__':
    main()
