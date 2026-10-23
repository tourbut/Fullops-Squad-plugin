"""흐름 그래프 명세의 게이트 이름이 실제 코드에 있고 비어 있음 엣지가 처음 수를 넘지 않는지 확인한다."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'docs/flow-graph.md'
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


def edges():
    section = SPEC.read_text(encoding='utf-8').split('## 엣지', 1)[1].split('\n## ', 1)[0]
    rows = [[cell.strip() for cell in line.strip('|').split('|')] for line in section.splitlines()
            if re.match(r'\| E\d+ \|', line)]
    return {row[0]: row for row in rows}


class FlowGraphTests(unittest.TestCase):
    def test_every_edge_names_a_gate_or_is_marked_empty(self):
        rows = edges()
        self.assertTrue(rows)
        for ident, row in rows.items():
            self.assertEqual(len(row), 6, ident)
            gate, strength = row[4], row[5]
            if gate.startswith('비어 있음'):
                self.assertEqual(strength, '', ident)
            else:
                self.assertIn(strength, ('차단', '알림'), ident)
                self.assertRegex(gate, r'`\w+\.py:\w+`', ident)

    def test_named_gates_exist_in_scripts(self):
        for ident, row in edges().items():
            for script, name in re.findall(r'`(\w+\.py):(\w+)`', row[4]):
                source = (SCRIPTS / script).read_text(encoding='utf-8')
                self.assertTrue(re.search(rf'(?m)^def {name}\(', source), f'{ident}: {script}:{name} 없음')

    def test_empty_edges_do_not_grow(self):
        baseline = int(re.search(r'처음 비어 있음 엣지: (\d+)개', SPEC.read_text(encoding='utf-8')).group(1))
        empty = sum(row[4].startswith('비어 있음') for row in edges().values())
        self.assertLessEqual(empty, baseline)


if __name__ == '__main__':
    unittest.main()
