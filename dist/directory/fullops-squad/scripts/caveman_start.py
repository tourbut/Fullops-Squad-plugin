#!/usr/bin/env python3
"""Load the installed Caveman skill for a new session without copying its rules."""
import json
import os
from pathlib import Path


def main():
    home = Path.home()
    roots = [home / '.agents', Path(os.environ.get('CODEX_HOME') or home / '.codex'),
             Path(os.environ.get('CLAUDE_CONFIG_DIR') or home / '.claude')]
    for root in roots:
        try:
            rules = (root / 'skills/caveman/SKILL.md').read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            continue
        if rules.startswith('---\n'):
            rules = rules.split('---', 2)[-1].strip()
        if not rules.strip():
            continue
        context = ('Apply the installed caveman skill at full intensity for this new session. '
                   'Honor later user requests to change intensity or turn it off. '
                   'Higher-priority safety and communication instructions still apply.\n\n' + rules)
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart',
                                                 'additionalContext': context}}))
        return
    print(json.dumps({'systemMessage': 'FullOps: caveman skill missing; install FullOps dependencies to enable session-start style.'}))


if __name__ == '__main__':
    main()
