#!/usr/bin/env python3
"""Report whether a Claude worker session in a worktree still has a warm prompt cache."""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Margin for dispatch time before the cache lapses.
WINDOW = {'1h': 50 * 60, '5m': 4 * 60}
MAX_CONTEXT = 80_000


def config_dirs(extra):
    if extra:
        return [Path(p) for p in extra]
    env = os.environ.get('CLAUDE_CONFIG_DIR')
    dirs = [Path(env)] if env else []
    dirs.append(Path.home() / '.claude')
    # Orca runs each Claude profile under claude-profiles/<id>/home; workers may use another profile.
    if env and Path(env).parent.parent.name == 'claude-profiles':
        dirs += sorted(Path(env).parent.parent.glob('*/home'))
    return list(dict.fromkeys(dirs))


def project_key(worktree):
    # shortcut: Claude Code truncates and hashes very long keys; such worktrees report not found.
    return re.sub(r'[^A-Za-z0-9]', '-', str(Path(worktree).resolve()))


def usages(transcript):
    rows = []
    with open(transcript, encoding='utf-8', errors='replace') as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            usage = (row.get('message') or {}).get('usage') if isinstance(row, dict) else None
            if isinstance(usage, dict) and row.get('timestamp'):
                rows.append((row['timestamp'], usage))
    return rows


def inspect(worktree, dirs, now, max_context):
    key = project_key(worktree)
    found = [p for d in config_dirs(dirs) for p in (d / 'projects' / key).glob('*.jsonl')]
    if not found:
        return {'found': False, 'retain': False, 'reason': 'no Claude transcript for this worktree'}
    transcript = max(found, key=lambda p: p.stat().st_mtime)
    rows = usages(transcript)
    if not rows:
        return {'found': False, 'retain': False, 'reason': 'transcript has no model usage', 'transcript': str(transcript)}
    stamp, last = rows[-1]
    ttl = '5m'  # unknown TTL counts as the shorter one
    for _, usage in reversed(rows):
        created = usage.get('cache_creation') or {}
        if created.get('ephemeral_1h_input_tokens'):
            ttl = '1h'
            break
        if created.get('ephemeral_5m_input_tokens'):
            break
    context = sum(int(last.get(k) or 0) for k in
                  ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens'))
    idle = int((now - datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds())
    warm, small = idle <= WINDOW[ttl], context <= max_context
    reason = 'warm and small' if warm and small else 'cache likely expired' if not warm else 'context too large'
    return {'found': True, 'transcript': str(transcript), 'last_at': stamp, 'idle_seconds': idle, 'ttl': ttl,
            'window_seconds': WINDOW[ttl], 'context_tokens': context, 'max_context': max_context,
            'warm': warm, 'small': small, 'retain': warm and small, 'reason': reason}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree', required=True)
    parser.add_argument('--config-dir', action='append', help='Claude config dir to search (repeatable)')
    parser.add_argument('--max-context', type=int, default=MAX_CONTEXT)
    args = parser.parse_args(argv)
    result = inspect(args.worktree, args.config_dir, datetime.now(timezone.utc), args.max_context)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
