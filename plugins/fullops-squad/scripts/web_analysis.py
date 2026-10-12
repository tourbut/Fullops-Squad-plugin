#!/usr/bin/env python3
"""웹 결과의 선택형 shadow 분류와 모델 없는 고정 회귀 승격. 기존 결과·게이트를 바꾸지 않는다."""
import argparse
import json
from pathlib import Path

from jev_test_web import OPERATIONS
from storage import write_json
import web_contract as contract


def shadow(summary):
    result = summary['result']
    if summary['passed']:
        category, reason = 'no_failure', 'Only the recorded scope passed; no optional tests are skipped.'
    elif summary.get('error_type') or result in ('execution_failed', 'blocked_action'):
        category, reason = 'execution_environment', 'Inspect the executor/fixture before assigning a product defect.'
    elif summary.get('checks') and summary.get('assertions_passed') is False:
        category, reason = 'undetermined', 'Independent assertions failed; inspect the product and test/fixture before labeling exploration.'
    elif result in ('max_steps', 'time_budget', 'cost_budget', 'revisit_budget', 'stalled', 'uncertain', 'blocked', 'blocked_policy'):
        category, reason = 'exploration_failure', 'Exploration stopped; failed or unexamined assertions remain visible.'
    else:
        category, reason = 'undetermined', 'Independent failure may be a product or test/fixture defect; human labeling is required.'
    return {'version': 'web-shadow-v1', 'suggested_category': category, 'reason': reason,
            'advisory_only': True, 'gates_changed': False, 'human_label': None,
            'target_sha': summary.get('target_sha'), 'scenario_sha256': summary.get('scenario_sha256'),
            'original_result': result, 'original_passed': summary['passed']}


def promote(scenario, summary, events):
    if summary.get('passed') is not True or summary.get('result') != 'passed' or summary.get('scope') == 'assertions_only':
        raise ValueError('only a passed interaction trace can become a regression; assertions-only is insufficient')
    if summary.get('scenario_sha256') != contract.replay_plan(scenario, [])['scenario_sha256']:
        raise ValueError('scenario differs from the recorded trace')
    steps = []
    for event in events:
        if event['operation'] == 'done':
            continue
        expected = 'observed next candidate group' if event['operation'] == 'observe_more' else 'ok'
        if event['outcome'] != expected:
            raise ValueError('held, blocked or failed actions cannot be promoted')
        step = {'operation': event['operation']}
        if event.get('target'):
            step['target'] = {k: v for k, v in event['target_description'].items() if v and k in ('role', 'name', 'near')}
        if event.get('value'):
            step['value'] = event['value']
        steps.append(step)
    plan = contract.replay_plan(scenario, steps)
    contract.validate_replay(scenario, plan, OPERATIONS)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True, help='result.json/events.jsonl이 있는 실행 폴더')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--shadow', action='store_true')
    action.add_argument('--promote', action='store_true')
    parser.add_argument('--scenario', type=Path, help='승격할 원래 시나리오')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    summary = json.loads((args.record / 'result.json').read_text(encoding='utf-8'))
    if args.shadow:
        result, name = shadow(summary), 'shadow.json'
    else:
        if not args.scenario:
            parser.error('--promote에는 --scenario가 필요합니다')
        scenario = json.loads(args.scenario.read_text(encoding='utf-8'))
        events = [json.loads(line) for line in (args.record / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        result, name = promote(scenario, summary, events), 'regression.json'
    output = args.output or args.record / name
    if output.exists():
        parser.error('기존 분석/회귀 파일을 보존합니다. 새 --output 경로를 쓰세요')
    write_json(output, result)
    print(output)


if __name__ == '__main__':
    main()
