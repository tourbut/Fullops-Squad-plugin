"""파일 규약을 흉내 내는 가짜 게임으로 Unity 조작 루프(상태 대기·행동 파일·판정·정체)와 브리지 설치를 확인한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import jev_test_unity as unity  # noqa: E402
import unity_bridge as bridge  # noqa: E402


class FakeGame(threading.Thread):
    """브리지처럼 state-<n>.json을 쓰고 action-<n>.json을 기다린다. 적은 x=5, 사거리 1.2, 체력 2."""

    def __init__(self, play):
        super().__init__(daemon=True)
        self.play, self.x, self.hp, self.outcome, self.last = play, 0.0, 2, '', ''
        self.start()

    def state(self, step):
        actors = [{'name': 'Enemy1', 'group': 'enemy', 'distance': abs(5 - self.x), 'direction': 'east',
                   'withinReach': abs(5 - self.x) <= 1.2}] if self.hp > 0 else []
        actions = ([{'id': 'approach:enemy', 'description': 'Move toward the nearest enemy.'}] if self.hp > 0 else []) + [
            {'id': 'press:attack', 'description': 'Attack whatever is within reach.'}, {'id': 'wait', 'description': 'Wait.'}]
        return {'step': step, 'player': {'name': 'Player'}, 'actors': actors,
                'fields': [{'name': 'enemy_hp', 'value': str(self.hp)}], 'texts': ['VICTORY'] if self.hp <= 0 else [],
                'actions': actions, 'lastAction': self.last, 'lastOutcome': self.outcome}

    def run(self):
        for step in range(1, 30):
            (self.play / f'state-{step}.json').write_text(json.dumps(self.state(step)), encoding='utf-8')
            path = self.play / f'action-{step}.json'
            action = None
            while action is None:
                try:
                    action = json.loads(path.read_text(encoding='utf-8'))['action']
                except (OSError, ValueError):
                    pass
            if action == 'quit':
                return
            self.last = action
            if action == 'approach:enemy':
                self.x, self.outcome = 4.0, 'reached'
            elif action == 'press:attack':
                self.hp -= 1 if abs(5 - self.x) <= 1.2 else 0
                self.outcome = 'pressed'
            else:
                self.outcome = 'waited'

    def poll(self):
        return None if self.is_alive() else 0

    def wait(self, timeout=None):
        self.join(timeout)

    def kill(self):
        pass


def jev(plan):
    steps = iter(plan)

    def call(payload):
        labels = list(payload['questions']['action']['criteria'])
        pick = next(steps)
        return {'answers': {'action': {'type': 'choice', 'choice': pick, 'confidence': 0.9,
                                       'probabilities': {l: 0.9 if l == pick else 0.1 / (len(labels) - 1) for l in labels}}},
                'usage': {'cost': 0.0001}}, 0.2
    return call


def main():
    scenario = {'goal': 'Defeat the enemy.', 'max_steps': 10, 'covers': ['M3-전투 적 처치'],
                'checks': [{'actor': 'enemy', 'absent': True}, {'field': 'enemy_hp', 'op': '<=', 'value': 0}, {'text': 'VICTORY'}]}
    quiet = {'log': lambda _: None}
    assert unity.problems(scenario) == []
    shown = unity.model_state({'gamePaused': True, 'actors': [], 'fields': [], 'texts': []})
    assert shown['gamePaused'] is True  # 게임이 스스로 멈춘 상태를 Jev에게 알린다(레벨업 선택 등)
    bad = unity.problems({'goal': 'x', 'checks': [{'field': 'hp', 'op': '~', 'value': 1}], 'player_args': 'x'})
    assert len(bad) == 3, bad  # covers·op·player_args
    with tempfile.TemporaryDirectory(prefix='fullops-jev-unity-') as tmp:
        tmp = Path(tmp)
        play = tmp / 'ok/play'
        play.mkdir(parents=True)
        summary = unity.run(scenario, play, FakeGame, jev(['approach:enemy', 'press:attack', 'press:attack', 'done']),
                            tmp / 'ok', **quiet)
        assert summary['passed'] and summary['steps'] == 4, summary
        assert json.loads((play / 'action-4.json').read_text())['action'] == 'quit'  # 끝나면 게임에 quit를 보낸다
        events = [json.loads(l) for l in (tmp / 'ok/events.jsonl').read_text(encoding='utf-8').splitlines()]
        assert [e['lastOutcome'] for e in events] == ['', 'reached', 'pressed', 'pressed']

        play = tmp / 'early/play'
        play.mkdir(parents=True)
        early = unity.run(scenario, play, FakeGame, jev(['done']), tmp / 'early', **quiet)
        assert early['result'] == 'done but checks failed' and not early['passed']  # 검증 없는 done은 통과가 아니다

        play = tmp / 'stall/play'
        play.mkdir(parents=True)
        stalled = unity.run(scenario, play, FakeGame, jev(['wait'] * 10), tmp / 'stall', **quiet)
        assert stalled['result'] == 'stalled' and stalled['steps'] == 4, stalled  # 같은 상태·같은 행동 세 번

        class Dead:
            def poll(self): return 1
            def wait(self, timeout=None): pass
            def kill(self): pass
        play = tmp / 'dead/play'
        play.mkdir(parents=True)
        dead = unity.run(scenario, play, lambda _: Dead(), jev([]), tmp / 'dead', timeout=1, **quiet)
        assert dead['result'].startswith('no state') and not dead['passed']

        # 브리지 설치: Unity 프로젝트를 찾아 embedded package로 복사하고 설정 템플릿을 만든다. 남의 폴더는 덮지 않는다
        repo = tmp / 'game'
        (repo / '.fullops-squad').mkdir(parents=True)
        (repo / '.fullops-squad/fullops.json').write_text('{"schema_version": 1}', encoding='utf-8')
        (repo / 'unity/Game/ProjectSettings').mkdir(parents=True)
        (repo / 'unity/Game/ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.24f1\n', encoding='utf-8')
        (repo / 'unity/Game/Library/X/ProjectSettings').mkdir(parents=True)  # 생성 폴더는 건너뛴다
        (repo / 'unity/Game/Library/X/ProjectSettings/ProjectVersion.txt').write_text('x', encoding='utf-8')
        changes = bridge.install(repo)
        package = repo / 'unity/Game/Packages/com.fullops.jevplay'
        assert (package / 'Runtime/JevPlay.cs').is_file() and (package / 'Runtime/JevPlay.cs.meta').is_file(), changes
        assert (repo / bridge.CONFIG).is_file() and len(changes) == 2
        assert bridge.install(repo) == []  # 같은 버전이면 변경 없음
        check = subprocess.run([sys.executable, str(SCRIPTS / 'unity_bridge.py'), 'check', '--repo', str(repo)],
                               capture_output=True, text=True, encoding='utf-8')
        assert check.returncode == 0 and '최신' in check.stdout
        (package / 'package.json').write_text('{"name": "someone.else", "version": "9"}', encoding='utf-8')
        try:
            bridge.install(repo)
            raise AssertionError('다른 패키지를 덮어씀')
        except ValueError:
            pass
    print('PASS: jev unity loop pass/premature-done/stall/dead player, bridge install/check/refuse')


if __name__ == '__main__':
    main()
