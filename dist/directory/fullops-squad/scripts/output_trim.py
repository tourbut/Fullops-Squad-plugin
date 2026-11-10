"""긴 Bash 출력을 모델에 보내기 전에 줄인다(#104 후보 A). 모델을 부르지 않는다.

PostToolUse는 성공한 호출에만 발동하므로 줄인 출력의 종료코드는 0이다. 실패한 호출의 출력은 그대로 간다.
Claude Code의 Bash 응답 형식일 때만 동작하고, 다른 CLI에서는 아무것도 하지 않는다.
"""
import json
import re
import time
from pathlib import Path

LIMIT, HEAD, TAIL, KEPT, SLOTS = 400, 80, 80, 80, 20
IMPORTANT = re.compile(r'\b(?:error|errors|fail|failed|failure|fatal|traceback|exception|panic)\b', re.I)


def shorten(text, notice):
    """줄 수가 LIMIT 이하면 None. 넘으면 앞뒤와 오류로 보이는 줄만 남긴 글"""
    lines = text.splitlines()
    if len(lines) <= LIMIT:
        return None
    important = [(i, line) for i, line in enumerate(lines[HEAD:-TAIL], HEAD + 1) if IMPORTANT.search(line)]
    omitted = len(lines) - HEAD - TAIL
    return '\n'.join([notice, *lines[:HEAD],
                      f'[중간 {omitted}줄 생략. 오류로 보이는 줄 {len(important)}개 중 처음 {min(len(important), KEPT)}개, 앞 숫자는 원문 줄 번호]',
                      *(f'{i}: {line}' for i, line in important[:KEPT]),
                      '[생략 끝]', *lines[-TAIL:]])


def slot(folder):
    """지우지 않고 용량을 묶기 위해 빈 슬롯이나 가장 오래된 슬롯을 덮어쓴다"""
    return min((folder / f'output-{i:02}.txt' for i in range(SLOTS)),
               key=lambda path: path.stat().st_mtime if path.exists() else 0)


def program(event):
    """명령의 실행 파일 이름. 실측에서 시험 로그와 파일 덤프(cat·sed)를 가른다. 값이 비밀일 수 있는 `K=V` 대입은 건너뛴다"""
    tool = event.get('tool_input')
    words = str(tool.get('command') or '').split() if isinstance(tool, dict) else []
    # shortcut: 공백이 있는 경로는 앞 조각만 남는다, 실측에 방해되면 shlex로 바꾼다
    return next((re.split(r'[\\/]', word.strip('\'"'))[-1][:40] for word in words if '=' not in word), '')


def replacement(root, event):
    """줄인 tool_response. 줄일 것이 없거나 다른 형식이면 None"""
    response = event.get('tool_response')
    if event.get('hook_event_name') != 'PostToolUse' or event.get('tool_name') != 'Bash' or not isinstance(response, dict):
        return None
    stdout, stderr = response.get('stdout'), response.get('stderr')
    # 형식이 다른 값은 Claude Code가 무시하므로 같은 필드를 유지한다
    if not isinstance(stdout, str) or not isinstance(stderr, str) or response.get('interrupted') or response.get('isImage'):
        return None
    if len(stdout.splitlines()) <= LIMIT and len(stderr.splitlines()) <= LIMIT:
        return None
    folder = Path(root) / '.fullops-squad/local/outputs'
    folder.mkdir(parents=True, exist_ok=True)
    path = slot(folder)
    path.write_text(f'{stdout}\n--- stderr ---\n{stderr}', encoding='utf-8', errors='replace', newline='')
    notice = f'[FullOps: 출력이 길어 줄였다. 종료코드 0. 원문은 Read 도구로 {path} 를 읽는다. 통과 근거는 원문으로 확인한다]'
    updated = {**response, 'stdout': shorten(stdout, notice) or stdout, 'stderr': shorten(stderr, notice) or stderr}
    with (folder / 'trim.jsonl').open('a', encoding='utf-8') as log:  # #104 2단계: 절감량 실측
        log.write(json.dumps({'time': int(time.time()), 'command': program(event), 'raw': len(stdout) + len(stderr),
                              'sent': len(updated['stdout']) + len(updated['stderr'])}) + '\n')
    return updated
