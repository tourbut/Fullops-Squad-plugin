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
import time
import uuid
from datetime import date, datetime, timezone
from fnmatch import fnmatch

import jev_find
import deliverables
from lint import code_changes, load_config, skips_tests, NO_CODE
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
# 하네스가 자동 생성·보관하는 기록. 요구사항 원천으로 읽을 수는 있지만 리뷰 대상 변경이 아니다.
GENERATED = (EVIDENCE, '.fullops-squad/docs/evaluations/jev/', '.fullops-squad/handovers/logs/')
EVIDENCE_REASON = ('검증 증거·하네스 자동 생성 기록. 파일마다 열람하지 않고 같은 폴더의 manifest·result.json·report.md로 '
                   '존재와 무결성을 확인한다.')


SUMMARY = ('manifest.json', 'result.json')


def evidence(path, reviewable=False):
    """리뷰어가 수백 개에 같은 사유를 적지 않게 prepare가 미리 채운다.
    OCR 대상 QA 증거 중 요약(manifest·result·.md)과 검증 스크립트는 직접 검토하고, 이전 리뷰 기록과 원시 JSON은 생략한다."""
    if path.startswith(GENERATED[1:]) or path.endswith('.bak'):
        return True
    if not path.startswith(EVIDENCE):
        return False
    name = path.rsplit('/', 1)[-1]
    return (not reviewable or path[len(EVIDENCE):].split('/', 1)[0].endswith('-review')
            or (name.endswith('.json') and name not in SUMMARY))


def file_entry(item, reviewable):
    return ({**item, 'review_status': 'skipped', 'reason': EVIDENCE_REASON} if evidence(item['path'], reviewable) else
            {**item, 'review_status': 'pending', 'reason': ''})


def need(repo, base, head):
    """기준 설정(merge-base)의 review_policy로 독립 리뷰 필요 여부를 정한다. 작업 브랜치가 기준을 낮추지 못한다."""
    import policy
    base, head = sha(repo, base), sha(repo, head)
    merge_base = subprocess.check_output(['git', '-C', str(repo), 'merge-base', base, head], text=True).strip()
    rules = policy.config_at_ref(repo, merge_base)[0]['review_policy']
    code = code_changes(repo, merge_base, head, load_config(repo, merge_base)[0])
    lines = sum(n for _, n in code)
    changed = subprocess.check_output(['git', '-C', str(repo), 'diff', '--name-only', '-z', '--no-renames', merge_base, head],
                                      text=True).split('\0')
    forced = [p for p in changed if p and any(fnmatch(p, g) or (g.startswith('**/') and fnmatch(p, g[3:])) for g in rules['always'])]
    required = bool(forced) or lines >= rules['min_code_lines'] or len(code) >= rules['min_code_files']
    if forced:
        reason = f'review_policy.always 경로 변경: {", ".join(forced[:5])}'
    elif required:
        reason = f'대규모 코드 변경: {len(code)}개 파일 {lines}줄 (기준 {rules["min_code_files"]}개 또는 {rules["min_code_lines"]}줄)'
    else:
        reason = (f'소규모 변경: 코드 {len(code)}개 파일 {lines}줄 (기준 {rules["min_code_files"]}개 또는 {rules["min_code_lines"]}줄 미만). '
                  '독립 리뷰 없이 병합 책임자가 diff·lint 결과를 확인한다')
    # ask: 사용자에게 진행/생략(waive)을 묻는다. 사용자가 자동 진행을 지시했거나 auto=true일 때만 review로 바로 간다.
    action = 'review' if required and rules['auto'] else 'ask' if required else 'skip'
    return {'required': required, 'action': action, 'reason': reason, 'base': base, 'head': head, 'merge_base': merge_base,
            'code_files': len(code), 'code_lines': lines, 'always': forced, 'policy': rules}


def waive(repo, key, base, head, reason, decided_by):
    """사용자가 대규모 변경의 독립 리뷰를 생략하기로 한 결정을 고정 SHA와 함께 남긴다. 리뷰 수락이 아니다."""
    if decided_by != 'user' or not reason or not reason.strip():
        raise ValueError('waive는 사용자 결정(--decided-by user)과 사용자 지시를 옮긴 --reason이 필요합니다')
    decision = need(repo, base, head)
    folder = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-review')
    path = folder / 'waiver.json'
    if path.exists():
        raise ValueError('기존 면제 기록을 보존합니다. 새 리뷰 키를 사용하세요')
    record = snapshot_record(repo, key)
    if (folder / 'result.json').is_file() or (record.is_file() and
            str(json.loads(record.read_text(encoding='utf-8')).get('state', '')).startswith(('active', 'creating'))):
        abandon(repo, key, 'user waived: ' + reason.strip())  # 진행 중이던 리뷰의 snapshot과 미완 폴더를 닫는다.
    write_json(path, {'state': 'waived', 'base': decision['base'], 'head': decision['head'], 'reason': reason.strip(),
                      'decided_by': decided_by, 'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      'need': {k: decision[k] for k in ('required', 'reason', 'code_files', 'code_lines', 'always')}})
    print(path.relative_to(repo))


def waived(repo, base, head):
    for path in (Path(repo) / '.fullops-squad/docs/evaluations/qa-reports').glob('*-review/waiver.json'):
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict) and data.get('state') == 'waived' and data.get('decided_by') == 'user' and \
                (data.get('base'), data.get('head')) == (base, head):
            return True
    return False


def worker_lint(repo, result):
    """같은 base·head로 이미 통과한 체크아웃별 lint 결과를 찾는다. 테스트를 다시 실행하지 않는다."""
    listed = subprocess.check_output(['git', '-C', str(repo), 'worktree', 'list', '--porcelain'], text=True)
    for line in listed.splitlines():
        if not line.startswith('worktree '):
            continue
        done = subprocess.run(['git', '-C', line[9:], 'rev-parse', '--absolute-git-dir'], capture_output=True, text=True)
        source = Path(done.stdout.strip()) / 'fullops-gate/lint-result.json'
        try:
            raw = source.read_bytes()
            check_lint(repo, result, json.loads(raw))
        except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
            continue  # 다른 SHA·설정·실패 결과는 재사용하지 않는다.
        return source, raw
    return None, None


def prepare(repo, key, base, head, lint_source=None):
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
              'prepared_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'reviewer': '', 'conclusion': '',
              'files': [file_entry(item, True) for item in preview['reviewable_files']] +
                       [file_entry(item, False) for item in preview['excluded_files']],
              'findings': []}
    managed = snapshot_record(repo, key)
    import policy
    if product_roles(repo) or managed.is_file() or policy.load(repo)['mode'] == 'dev':
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
    lint_raw = Path(lint_source).read_bytes() if lint_source else None
    if lint_raw is not None:
        check_lint(repo, result, json.loads(lint_raw))
    else:
        lint_source, lint_raw = worker_lint(repo, result)
        if lint_raw is not None:
            print(f'lint 증거 재사용(재실행 금지): {lint_source}')
    destination.mkdir(parents=True)
    for name, data in [('preview', preview), ('rules', rules), ('result', result)]:
        (destination / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    template = Path(__file__).resolve().parents[1] / 'assets/repository/.fullops-squad/review/_REPORT.md'
    # 병합 후 lint의 DOC-003을 막는다. 리뷰어는 본문만 채운다.
    meta = deliverables.render({'title': f'{key} 리뷰', 'status': 'draft', 'updated': date.today().isoformat(),
                                'owner': 'reviewer', 'summary': f'{head[:12]} 병합 전 독립 리뷰 보고서'})
    (destination / 'report.md').write_text(meta + '\n' + template.read_text(encoding='utf-8').replace('<과제 키>', key, 1), encoding='utf-8')
    if lint_raw is not None:
        atomic_write(destination / 'lint.json', lint_raw)
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


def released(repo, path, dispatch):
    """snapshot에 살아 있는 Orca terminal이 없음을 확인한다. release 직후 반영 지연은 짧게 재확인한다."""
    from integration import orca
    for attempt in range(5):
        listed = orca('terminal', 'list', '--worktree', f'path:{path}', cwd=repo)
        if listed is not None and not listed.get('terminals'):
            break
        if attempt < 4:
            time.sleep(2)
    else:
        raise ValueError('Orca에서 snapshot terminal 종료를 확인하지 못했습니다. reviewer를 release(worker-release)한 뒤 재시도하세요')
    observation = {'terminals': 0}
    if dispatch:
        # release 뒤 terminal 출력은 지워지므로 auto source로 projection만 읽는다. worker 상태 이름은 판정에 쓰지 않는다.
        status = orca('orchestration', 'worker-read', '--dispatch', dispatch, '--source', 'auto', '--limit', '1', cwd=repo) or {}
        workspace = str(((status.get('projection') or {}).get('workspace') or {}).get('id') or '').split('::', 1)[-1]
        if workspace and Path(workspace).resolve() != Path(path).resolve():
            raise ValueError('release한 dispatch가 해당 snapshot의 reviewer가 아닙니다')
        observation.update(dispatch=dispatch, workspace=workspace or None,
                           resource=(status.get('projection') or {}).get('resource'))
    return observation


def owned(repo, key, data, path):
    if data.get('managed') is not True or data.get('kind') != 'git-worktree' or data.get('purpose') != 'review' or data.get('key') != key:
        raise ValueError('FullOps 소유의 임시 Git worktree가 아닙니다')
    if Path(data['repository']).resolve() != Path(repo).resolve() or path.resolve().parent != Path(repo).resolve().parent or not path.name.startswith('.fullops-review-'):
        raise ValueError('관리 경로 정체성이 다릅니다')


def remove_snapshot(repo, path):
    if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--ignored', '--untracked-files=all']).strip():
        raise ValueError('snapshot의 미커밋·미추적·ignored 고유 파일을 보존하세요')
    subprocess.check_call(['git', '-C', str(repo), 'worktree', 'remove', str(path)])  # --force 사용 금지


def abandon(repo, key, reason, dispatch=None):
    """중단·면제한 리뷰의 snapshot만 정리한다. 수락 증거가 아니며 미완 리뷰 폴더는 abandoned 기록으로 닫는다."""
    if not reason or not reason.strip():
        raise ValueError('--abandon에는 --reason이 필요합니다')
    record = snapshot_record(repo, key)
    data = json.loads(record.read_text(encoding='utf-8')) if record.is_file() else None
    folder = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-review')
    if data is None and not folder.is_dir():
        raise ValueError('해당 키의 snapshot 기록과 리뷰 폴더가 없습니다')
    if data and str(data.get('state', '')).startswith(('active', 'creating')):
        path = Path(data['path'])
        owned(repo, key, data, path)
        if path.exists():
            released(repo, path, dispatch)
            remove_snapshot(repo, path)
        write_json(record, {**data, 'state': 'abandoned', 'reason': reason.strip(), 'hold': None})
    if folder.is_dir():
        write_json(folder / 'abandoned.json', {'state': 'abandoned', 'reason': reason.strip(),
                   'result_sha256': rule_hash(folder / 'result.json') if (folder / 'result.json').is_file() else None,
                   'at': datetime.now(timezone.utc).isoformat(timespec='seconds')})


def abandoned(repo, key):
    """중단 기록 뒤 원본 결과가 바뀌지 않았는지 확인한다. 수락이 아니라 미완 리뷰 종료 표시다."""
    folder = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-review')
    path = folder / 'abandoned.json'
    if not path.is_file():
        return False
    data = json.loads(path.read_text(encoding='utf-8'))
    current = rule_hash(folder / 'result.json') if (folder / 'result.json').is_file() else None
    return data.get('state') == 'abandoned' and data.get('result_sha256') == current


def prune(repo):
    """이미 사라진 snapshot의 active 기록을 missing으로 닫고 남은 snapshot을 보고한다. 존재하는 worktree는 지우지 않는다."""
    listed = subprocess.check_output(['git', '-C', str(repo), 'worktree', 'list', '--porcelain'], text=True)
    registered = {Path(line[9:]).resolve() for line in listed.splitlines() if line.startswith('worktree ')}
    folder = snapshot_record(repo, 'x').parent
    report = {'missing': [], 'live': []}
    for record in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        data = json.loads(record.read_text(encoding='utf-8'))
        if data.get('managed') is not True or not str(data.get('state', '')).startswith(('active', 'creating')):
            continue
        path = Path(data['path'])
        live = {'key': data['key'], 'path': str(path), 'head': data['head'], 'hold': (data.get('hold') or {}).get('reason')}
        if path.exists():
            report['live'].append(live)
        elif path.resolve() in registered:
            report['live'].append({**live, 'hold': '경로 없음·Git 등록 남음: git worktree prune 확인'})
        else:
            write_json(record, {**data, 'state': 'missing', 'hold': None,
                                'reason': 'snapshot 경로와 Git worktree 등록이 이미 없음(prune 확인)'})
            report['missing'].append(data['key'])
    return report


def cleanup(repo, key, dispatch, finished=False):
    record = snapshot_record(repo, key)
    data = json.loads(record.read_text(encoding='utf-8'))
    if data.get('state') == 'removed':
        historical(repo, key)
        return  # 동일 정리 재시도는 멱등이다.
    path = Path(data['path'])
    try:
        if not finished:
            raise ValueError('리뷰·수락·재검증 완료(--finished)가 필요합니다. 중단한 리뷰는 --abandon --reason을 사용하세요')
        owned(repo, key, data, path)
        result_path = safe_file(repo, data['evidence'] + '/result.json')
        result = json.loads(result_path.read_text(encoding='utf-8'))
        independence = result.get('independence') or {}
        if independence.get('snapshot_path') != str(path) or result['head'] != data['head'] or any(
                independence.get(k) != data[k] for k in ('implementer_session', 'reviewer_session')):
            raise ValueError('생성 기록과 리뷰 정체성이 다릅니다')
        if dispatch and data.get('dispatch') and data['dispatch'] != dispatch:
            raise ValueError('기록된 reviewer dispatch와 다릅니다')
        observation = released(repo, path, dispatch)
        if dispatch:
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
                 'release_observation': observation, 'state': 'validated'}
        write_json(receipt, saved)
        check_independence(repo, result)
        released(repo, path, dispatch)
        remove_snapshot(repo, path)
        write_json(receipt, {**saved, 'state': 'removed'})
        write_json(record, {**data, 'state': 'removed'})
    except Exception as error:
        try:
            write_json(record, {**data, 'hold': {'reason': str(error), 'owner': data.get('owner'),
                       'resume': '증거·clean 상태·reviewer release를 확인하고 같은 cleanup 명령을 재시도'}})
        except OSError:
            pass  # 기록 저장 실패가 원래 거부 원인을 가리지 않는다.
        raise


def check_lint(repo, result, lint):
    """기존 실행 증거의 범위·설정·명령·결과만 검사한다. 테스트는 실행하지 않는다."""
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
    code = code_changes(repo, merge_base, result['head'], settings)
    import policy
    level, policy_digest = policy.at_ref(repo, merge_base)
    if any(c.get('level') is not None for c in settings['commands']) and (
            lint.get('test_level') != level or lint.get('policy_sha256') != policy_digest):
        raise ValueError('테스트 레벨이 기준 설정과 다릅니다. lint.py를 다시 실행하세요')
    for command in settings['commands']:
        records = [c for c in lint['commands'] if c.get('kind', 'lint') == command.get('kind', 'lint') and c['name'] == command['name']
                   and c.get('run') == command['run'] and c.get('cwd', '.') == command.get('cwd', '.')]
        if len(records) != 1:
            raise ValueError(f'등록된 검사 실행 증거가 없거나 중복됐습니다: {command["name"]}')
        if not policy.command_selected(command, level):
            if records[0]['status'] != 'skipped' or not records[0].get('reason', '').strip():
                raise ValueError('레벨 범위 밖 테스트는 skipped와 사유를 기록하세요')
            continue
        if skips_tests(command, code) and records[0]['status'] == 'skipped' and records[0].get('reason') == NO_CODE:
            continue  # 문서·설정만 바뀐 변경은 test 명령을 실행하지 않는다.
        if records[0]['status'] == 'passed' and records[0].get('exit_code') != 0:
            raise ValueError(f'검사 통과 종료코드가 없습니다: {command["name"]}')
        if records[0]['status'] not in ('passed', 'failed', 'timeout', 'unavailable'):
            raise ValueError(f'검사가 실행되지 않았습니다: {command["name"]}')
    if any(c['status'] == 'unavailable' and not c.get('reason', '').strip() for c in lint['commands']):
        raise ValueError('실행 불가 lint 명령에 reason을 기록하세요')
    errors = (sum(v['severity'] == 'ERROR' for v in lint['violations'])
              + sum(c['status'] in ('failed', 'timeout') for c in lint['commands']))
    if errors:
        raise ValueError(f'lint ERROR {errors}건이 남아 있습니다. 수정 커밋 후 새 리뷰를 준비하세요')
    if len(lint['commands']) != len(settings['commands']):
        raise ValueError('등록되지 않은 검사 실행 증거가 있습니다')


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
    check_lint(repo, result, lint)
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


def direct_check(repo, base, head, implementer):
    """직접 구현에는 부모 dispatch 대신 기존 고정 SHA 리뷰 계약을 적용한다. 사용자 면제 기록도 허용한다."""
    import contextlib
    import io
    if waived(repo, base, head):
        return
    for path in (repo / '.fullops-squad/docs/evaluations/qa-reports').glob('*-review/result.json'):
        result = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(result, dict) or not isinstance(result.get('independence', {}), dict):
            raise ValueError('독립 리뷰 result·independence는 객체여야 합니다')
        if (result.get('base'), result.get('head')) != (base, head):
            continue
        if result.get('review_schema_version') != 2 or result.get('independence', {}).get('implementer_session') != implementer:
            continue
        key = path.parent.name[:-7]
        if superseded_check(repo, key) or abandoned(repo, key):
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            if path.with_name('snapshot-cleanup.json').is_file():
                historical(repo, key)  # Already accepted and cleaned; this is completion, not a new acceptance.
            else:
                check(repo, key, base, head)
        return
    raise ValueError('직접 구현의 현재 SHA는 대규모 변경이지만 독립 리뷰·면제 기록이 없습니다. 사용자에게 리뷰 진행 여부를 묻고, '
                     '진행하면 fullops-review 절차를 완료하고, 생략하면 review.py waive --decided-by user로 기록하세요')


def superseded_check(repo, key):
    folder = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-review')
    path = folder / 'superseded.json'
    if not path.is_file():
        return False
    receipt = json.loads(path.read_text(encoding='utf-8'))
    replacement = receipt['replacement']
    if not KEY.fullmatch(replacement) or replacement == key or receipt.get('state') != 'superseded':
        raise ValueError('리뷰 대체 기록의 키·상태가 다릅니다')
    if receipt.get('original_sha256') != rule_hash(folder / 'result.json') or receipt.get(
            'replacement_evidence_sha256') != evidence_hashes(repo, replacement):
        raise ValueError('리뷰 대체 후 원본·수락 증거가 바뀌었습니다')
    return True


def supersede(repo, key, replacement):
    """실패 원본은 그대로 두고 검증한 후속 수락에 연결한다."""
    if not replacement or not KEY.fullmatch(replacement) or replacement == key:
        raise ValueError('서로 다른 유효한 원본·후속 리뷰 키를 지정하세요')
    folder = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{key}-review')
    original = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    next_folder = safe_file(repo, f'.fullops-squad/docs/evaluations/qa-reports/{replacement}-review')
    result = json.loads((next_folder / 'result.json').read_text(encoding='utf-8'))
    subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', original['head'], result['head']], check=True)
    def merge_base(data):
        return subprocess.check_output(['git', '-C', str(repo), 'merge-base', sha(repo, data['base']),
                                        sha(repo, data['head'])], text=True).strip()
    coverage = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor',
                               merge_base(result), merge_base(original)], capture_output=True)
    if coverage.returncode != 0:
        raise ValueError('후속 리뷰의 범위가 원본 미검토 변경을 포함하지 않습니다. 원본 기준부터 리뷰하세요')
    if (next_folder / 'snapshot-cleanup.json').is_file():
        historical(repo, replacement)
    else:
        check(repo, replacement, result['base'], result['head'])
    write_json(folder / 'superseded.json', {'state': 'superseded', 'replacement': replacement,
               'original_sha256': rule_hash(folder / 'result.json'),
               'replacement_evidence_sha256': evidence_hashes(repo, replacement)})


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
    parser.add_argument('mode', choices=['need', 'waive', 'prepare', 'check', 'snapshot', 'cleanup', 'supersede', 'prune'])
    parser.add_argument('--replacement', help='supersede: 검증한 후속 리뷰 키')
    parser.add_argument('--repo', required=True)
    parser.add_argument('--key', help='need·prune 외 모드에서 필수')
    for option in ['from', 'to', 'implementer-session', 'reviewer-session', 'owner', 'dispatch', 'reason', 'decided-by']:
        parser.add_argument('--' + option)
    parser.add_argument('--finished', action='store_true', help='cleanup: 리뷰·수락·필요 재검증 완료')
    parser.add_argument('--abandon', action='store_true', help='cleanup: 중단·면제한 리뷰의 snapshot 정리(--reason 필수, 수락 아님)')
    parser.add_argument('--historical', action='store_true', help='check: 과거 완료 증거만 확인; 신규 수락에 사용 금지')
    parser.add_argument('--lint', help='prepare: 동일 코드·환경에서 이미 실행한 lint JSON을 재사용')
    parser.add_argument('--task-key', help='check: jev_find 결과의 과제 키 (기본: 리뷰 키)')
    args = parser.parse_args()
    try:
        if args.mode not in ('need', 'prune') and not KEY.fullmatch(args.key or ''):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        if args.mode == 'need':
            if not getattr(args, 'from') or not args.to:
                raise ValueError('--from과 --to가 필요합니다')
            print(json.dumps(need(repo, getattr(args, 'from'), args.to), ensure_ascii=False))
        elif args.mode == 'waive':
            if not getattr(args, 'from') or not args.to:
                raise ValueError('--from과 --to가 필요합니다')
            waive(repo, args.key, getattr(args, 'from'), args.to, args.reason, args.decided_by)
        elif args.mode == 'prune':
            print(json.dumps(prune(repo), ensure_ascii=False, indent=2))
        elif args.mode == 'cleanup' and args.abandon:
            abandon(repo, args.key, args.reason, args.dispatch)
        elif args.mode == 'supersede':
            supersede(repo, args.key, args.replacement)
        elif args.mode == 'snapshot':
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
            prepare(repo, args.key, getattr(args, 'from'), args.to, args.lint)
        else:
            if args.task_key and not KEY.fullmatch(args.task_key):
                raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
            check(repo, args.key, getattr(args, 'from'), args.to, args.task_key)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'리뷰 처리 실패: {error}\n')


if __name__ == '__main__':
    main()
