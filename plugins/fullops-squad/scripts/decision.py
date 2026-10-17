#!/usr/bin/env python3
"""coordinator가 사용자에게 요청한 결정을 Git 공용 디렉터리에 기록한다. 세션·워크트리가 바뀌어도 열린 결정이 남는다."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from done_gate import git
from storage import write_json

STATES = ('open', 'answered', 'dropped')


def directory(root):
    common = Path(git(root, 'rev-parse', '--git-common-dir'))
    return (common if common.is_absolute() else Path(root) / common).resolve() / 'fullops-decisions'


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


def add(root, question, key=None, options=(), blocks=None):
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
    item = {'id': ident, 'status': 'open', 'key': key, 'question': question, 'options': list(options),
            'blocks': blocks, 'asked_at': now()}
    write_json(folder / f'{ident}.json', item)
    return item


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
    return (f' 사용자 결정 대기 {len(waiting)}건: {lines}. 이 결정에 걸린 작업은 진행하지 말고 사용자에게 먼저 다시 묻는다. '
            '답을 받으면 decision.py answer로 닫고, 필요 없어진 결정은 drop한다.')


def main(argv=None):
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
    args = parser.parse_args(argv)
    root = Path(git(args.repo, 'rev-parse', '--show-toplevel'))
    try:
        if args.action == 'add':
            if not (args.question and args.question.strip()):
                parser.error('add에는 --question이 필요합니다')
            result = add(root, args.question.strip(), args.key, args.option, args.blocks)
        elif args.action == 'answer':
            if not (args.id and args.answer and args.answer.strip()):
                parser.error('answer에는 --id와 --answer가 필요합니다')
            result = close(root, args.id, 'answered', answer=args.answer.strip(), decided_by=args.by)
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
