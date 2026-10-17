#!/usr/bin/env python3
"""Check the warm-cache retain judgement for Claude worker transcripts."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import session_cache

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def row(minutes_ago, read, ttl='1h'):
    created = {'ephemeral_1h_input_tokens': 500 if ttl == '1h' else 0,
               'ephemeral_5m_input_tokens': 500 if ttl == '5m' else 0}
    stamp = (NOW - timedelta(minutes=minutes_ago)).isoformat().replace('+00:00', 'Z')
    usage = {'input_tokens': 2, 'cache_read_input_tokens': read, 'cache_creation_input_tokens': 500,
             'output_tokens': 300, 'cache_creation': created}
    return json.dumps({'type': 'assistant', 'timestamp': stamp, 'message': {'usage': usage}})


with tempfile.TemporaryDirectory() as directory:
    config = Path(directory) / 'claude'
    worktree = Path(directory) / 'repo-worker'
    worktree.mkdir()
    sessions = config / 'projects' / session_cache.project_key(worktree)

    def judge(*rows):
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / 's.jsonl').write_text('not json\n' + '\n'.join(rows) + '\n', encoding='utf-8')
        return session_cache.inspect(worktree, [str(config)], NOW, session_cache.MAX_CONTEXT)

    assert session_cache.inspect(worktree, [str(config)], NOW, 80_000) == {
        'found': False, 'retain': False, 'reason': 'no Claude transcript for this worktree'}
    result = judge(row(60, 20_000), row(40, 40_000))
    assert result['retain'] and result['ttl'] == '1h' and result['context_tokens'] == 40_802
    assert judge(row(55, 40_000))['reason'] == 'cache likely expired'
    assert judge(row(10, 120_000))['reason'] == 'context too large'
    # The 5-minute cache leaves only a short window.
    result = judge(row(3, 40_000, '5m'))
    assert result['retain'] and result['ttl'] == '5m'
    assert not judge(row(6, 40_000, '5m'))['warm']

print('PASS: session cache judges warm, expired, large and 5m transcripts')
