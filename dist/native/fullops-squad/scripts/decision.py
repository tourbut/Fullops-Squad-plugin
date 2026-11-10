#!/usr/bin/env python3
"""coordinator가 사용자에게 요청한 결정을 Git 공용 디렉터리에 기록한다. 세션·워크트리가 바뀌어도 열린 결정이 남는다.

SHA에 묶은 결정은 같은 SHA·유효 기간·허용 응답자의 답만 받는다. Orca와 봇 어느 쪽 답이든 같은 기록을 닫는다."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

from done_gate import git
from policy import common_dir
from storage import write_json

STATES = ('open', 'answered', 'dropped')


def directory(root):
    return common_dir(str(Path(root).resolve())) / 'fullops-decisions'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def items(root):
    found = []
    for path in sorted(directory(root).glob('D*.json')):
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(item, dict) and item.get('status') in STATES:
            found.append(item)
    return found


def open_items(root):
    return [item for item in items(root) if item['status'] == 'open']


def add(root, question, key=None, options=(), blocks=None, repository=None, sha=None, risks=(), expires_hours=None,
        origin='user', allow=()):
    if sha is not None and not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('--sha는 40자리 커밋 SHA여야 합니다')
    if expires_hours is not None and expires_hours < 1:
        raise ValueError('--expires-hours는 1 이상이어야 합니다')
    folder = directory(root)
    folder.mkdir(parents=True, exist_ok=True)
    taken = [int(m.group(1)) for p in folder.glob('D*.json') if (m := re.fullmatch(r'D(\d+)\.json', p.name))]
    number = max(taken, default=0) + 1
    while True:
        ident = f'D{number:03d}'
        try:  # 배타 생성으로 같은 번호를 두 번 쓰지 않는다
            os.close(os.open(folder / f'{ident}.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            number += 1
    item = {'version': 1, 'id': ident, 'status': 'open', 'key': key, 'question': question, 'options': list(options),
            'blocks': blocks, 'asked_at': now(), 'origin': origin}
    hours = expires_hours or (24 if sha else None)  # SHA 승인은 기본 하루 안에 받는다
    extra = {'repository': repository, 'sha': sha, 'risks': list(risks), 'allow': list(allow),
             'expires_at': hours and (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec='seconds')}
    item.update({k: v for k, v in extra.items() if v})
    write_json(folder / f'{ident}.json', item)
    return item


def answer(root, ident, text, by='user', sha=None, via='user'):
    """열린 결정을 닫는다. 이미 닫힌 결정은 덮어쓰지 않고 already로 알린다."""
    path = directory(root) / f'{ident}.json'
    if not re.fullmatch(r'D\d+', ident) or not path.is_file():
        raise ValueError(f'결정 {ident}이 없습니다')
    item = json.loads(path.read_text(encoding='utf-8'))
    if item.get('status') != 'open':
        return {**item, 'already': True}
    if item.get('sha') and sha != item['sha']:
        raise ValueError(f'결정 {ident}은 {item["sha"][:12]}에 묶여 있습니다. 커밋이 바뀌었으면 다시 물어야 합니다')
    if item.get('expires_at') and datetime.now(timezone.utc) >= datetime.fromisoformat(item['expires_at']):
        raise ValueError(f'결정 {ident}은 {item["expires_at"]}에 만료됐습니다. 다시 물어야 합니다')
    if item.get('allow') and by not in item['allow']:
        raise ValueError(f'{by}는 결정 {ident}에 답할 수 없습니다')
    # shortcut: 같은 순간 두 경로의 답이 겹치면 나중 답이 기록된다. 충돌이 보이면 배타 잠금을 둔다
    return close(root, ident, 'answered', answer=text, decided_by=by, via=via)


def close(root, ident, status, **fields):
    path = directory(root) / f'{ident}.json'
    if not re.fullmatch(r'D\d+', ident) or not path.is_file():
        raise ValueError(f'결정 {ident}이 없습니다')
    item = json.loads(path.read_text(encoding='utf-8'))
    if item.get('status') != 'open':
        raise ValueError(f'결정 {ident}은 이미 {item.get("status")}입니다')
    item.update(status=status, closed_at=now(), **fields)
    write_json(path, item)
    return item


def brief(root):
    """새 coordinator 세션 문맥에 넣을 열린 결정 요약. 없으면 빈 문자열."""
    waiting = open_items(root)
    if not waiting:
        return ''
    lines = '; '.join(f"{i['id']}{'(' + i['key'] + ')' if i.get('key') else ''}: {i['question']}"
                      + (f" [{' / '.join(i['options'])}]" if i.get('options') else '') for i in waiting)
    return (f' 사용자 결정 대기 {len(waiting)}건: {lines}. 이 결정이 막는 작업만 멈추고 그 작업 전에 사용자에게 다시 묻는다. 막히지 않은 작업은 계속한다. '
            '답을 받으면 decision.py answer로 닫고, 필요 없어진 결정은 drop한다.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['add', 'answer', 'drop', 'list'])
    parser.add_argument('--repo', default='.')
    parser.add_argument('--question')
    parser.add_argument('--key', help='과제 키')
    parser.add_argument('--option', action='append', default=[], help='선택지(반복)')
    parser.add_argument('--blocks', help='이 결정을 기다리는 worker·과제·질문 message id')
    parser.add_argument('--id')
    parser.add_argument('--answer')
    parser.add_argument('--by', default='user', help='결정한 사람')
    parser.add_argument('--reason')
    parser.add_argument('--all', action='store_true', help='닫힌 결정도 표시')
    parser.add_argument('--repository', help='add: owner/repo')
    parser.add_argument('--sha', help='add: 승인을 묶을 커밋 SHA. answer: 지금 병합할 SHA(묶인 SHA와 같아야 한다)')
    parser.add_argument('--risk', action='append', default=[], help='add: 사람 승인이 필요한 사유(반복)')
    parser.add_argument('--expires-hours', type=int, help='add: 유효 시간. --sha가 있으면 기본 24')
    parser.add_argument('--origin', choices=['user', 'bot'], default='user', help='add: 요청이 들어온 진입점')
    parser.add_argument('--allow', action='append', default=[], help='add: 답할 수 있는 사람(반복, 없으면 누구나)')
    parser.add_argument('--via', choices=['user', 'bot'], default='user', help='answer: 답이 들어온 경로')
    args = parser.parse_args()
    root = Path(git(args.repo, 'rev-parse', '--show-toplevel'))
    try:
        if args.action == 'add':
            if not (args.question and args.question.strip()):
                parser.error('add에는 --question이 필요합니다')
            result = add(root, args.question.strip(), args.key, args.option, args.blocks, args.repository, args.sha,
                         args.risk, args.expires_hours, args.origin, args.allow)
        elif args.action == 'answer':
            if not (args.id and args.answer and args.answer.strip()):
                parser.error('answer에는 --id와 --answer가 필요합니다')
            result = answer(root, args.id, args.answer.strip(), args.by, args.sha, args.via)
        elif args.action == 'drop':
            if not (args.id and args.reason and args.reason.strip()):
                parser.error('drop에는 --id와 --reason이 필요합니다')
            result = close(root, args.id, 'dropped', reason=args.reason.strip())
        else:
            result = {'decisions': items(root) if args.all else open_items(root)}
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
