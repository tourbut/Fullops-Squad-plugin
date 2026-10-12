"""웹 실행기 공통 입력·관측·권한 계약. 모델 점수와 별개로 적용한다."""
import hashlib
import ipaddress
import json
import math
import re
from urllib.parse import urlsplit, urlunsplit

from jev_observe import safe_text

NONE = '_NONE_'
STOP = '_STOP_'
BOUNDS = {'max_seconds': (120, 1, 1800), 'max_cost': (0.05, 0.000001, 100),
          'max_visits': (4, 1, 20), 'candidate_limit': (80, 1, 254), 'max_input_chars': (32000, 4000, 100000)}


class SafetyStop(RuntimeError):
    pass


def origin(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('http(s) origin without credentials required')
    host = parts.hostname.encode('idna').decode().lower()
    host = '[' + host + ']' if ':' in host else host
    port = parts.port
    return f'{parts.scheme}://{host}' + (f':{port}' if port and port != (443 if parts.scheme == 'https' else 80) else '')


def loopback(url):
    host = urlsplit(url).hostname
    try:
        return host == 'localhost' or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r'(?i)(?:[\w.-]*(?:password|secret|token|api[_-]?key)[\w.-]*)\s*[:=]\s*[^\s,;]+|'
                   r'\bBearer\s+[^\s,;]+|\bsk-(?:or-)?[A-Za-z0-9_-]{12,}|'
                   r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)', '[REDACTED]', value)
    value = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|\b(?:\+?\d[\d ()-]{8,}\d)\b', '[REDACTED]', value)
    return value


def public_url(url):
    try:
        parts = urlsplit(url)
        return redact(urlunsplit((parts.scheme, urlsplit(origin(url)).netloc, parts.path, '', '')))
    except (TypeError, ValueError):
        return '[invalid URL]'


def policy(scenario):
    saved = scenario.get('safety', {})
    return {'fixture': saved.get('fixture'),
            'allowed_origins': saved.get('allowed_origins', [origin(scenario['url'])]),
            'allowed_operations': saved.get('allowed_operations', []),
            'requests': saved.get('requests', [])}


def problems(scenario, operations):
    found = []
    for key, (default, low, high) in BOUNDS.items():
        value = scenario.get(key, default)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high or \
                key in ('max_visits', 'candidate_limit', 'max_input_chars') and type(value) is not int:
            found.append(f'{key}: {low}..{high}')
    if type(scenario.get('exploration', False)) is not bool:
        found.append('exploration must be boolean (default false)')
    try:
        origin(scenario['url'])
    except (KeyError, TypeError, ValueError):
        found.append('url origin is invalid')
    safety = scenario.get('safety', {})
    if not isinstance(safety, dict) or set(safety) - {'fixture', 'allowed_origins', 'allowed_operations', 'requests'}:
        return found + ['safety fields are invalid']
    fixture = safety.get('fixture')
    if fixture is not None and (not isinstance(fixture, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', fixture)):
        found.append('fixture must name an isolated test fixture/tenant')
    origins = safety.get('allowed_origins', [])
    if not isinstance(origins, list) or len(origins) > 16 or any(not isinstance(v, str) for v in origins):
        found.append('allowed_origins must be a bounded origin list')
    else:
        try:
            if any(origin(v) != v for v in origins) or origins and origin(scenario['url']) not in origins:
                found.append('allowed_origins must contain exact origins including the start URL')
        except (KeyError, ValueError):
            found.append('allowed_origins are invalid')
    allowed = safety.get('allowed_operations', [])
    if not isinstance(allowed, list) or any(not isinstance(v, str) or v not in operations for v in allowed) or len(set(allowed)) != len(allowed):
        found.append('allowed_operations must list known operations once')
    elif allowed and not fixture:
        found.append('effectful operations require an isolated fixture')
    rules = safety.get('requests', [])
    if not isinstance(rules, list) or len(rules) > 64:
        found.append('requests must be a bounded method/path list')
    else:
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) != {'method', 'path'} or rule['method'] not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE') or \
                    not isinstance(rule['path'], str) or not rule['path'].startswith('/') or any(c in rule['path'] for c in ('?', '#', '*')):
                found.append('requests require an exact method/path pair')
            elif rule['method'] not in ('GET', 'HEAD') and not fixture:
                found.append('mutating requests require an isolated fixture')
    return found


def observation(page, scenario, offset=0):
    """전체 로컬 관측과 모델에 보내는 제한된 후보 범위를 구분한다."""
    elements = page['elements']
    if not isinstance(elements, list) or any(not isinstance(e, dict) or not isinstance(e.get('ref'), str) or
            not re.fullmatch(r'e\d+', e['ref']) for e in elements) or len({e['ref'] for e in elements}) != len(elements):
        raise ValueError('invalid or duplicate candidate IDs')
    limit = scenario.get('candidate_limit', BOUNDS['candidate_limit'][0])
    visible = elements[offset:offset + limit]
    return {**page, 'state_id': hashlib.sha256(json.dumps([page['url'], page['digest']], sort_keys=True).encode()).hexdigest(),
            'elements': visible, 'coverage': {'total': len(elements), 'offset': offset, 'observed': len(visible),
                                            'remaining': max(0, len(elements) - offset - len(visible)),
                                            'unsupported': page.get('unsupported', [])}}


def public_page(page):
    result = {'url': public_url(page['url']), 'state_id': page.get('state_id'), 'coverage': page.get('coverage', {})}
    result['elements'] = [{k: redact(e[k]) for k in ('ref', 'role', 'name', 'state', 'near') if k in e} for e in page['elements']]
    return result


def action_denial(safety, page, operation, ref, request_filtering=False):
    if origin(page['url']) not in safety['allowed_origins']:
        return 'origin_not_allowed'
    if operation in ('done', 'blocked', STOP, 'scroll_down', 'observe_more'):
        return None
    target = next((e for e in page['elements'] if e['ref'] == ref), None)
    if target is None:
        return 'candidate_not_in_observation'
    if target.get('sensitive') or any('disabled' in str(s).lower() and 'false' not in str(s).lower() for s in target.get('state', [])):
        return 'disabled_or_sensitive_target'
    if not safety['fixture'] or operation not in safety['allowed_operations']:
        return 'operation_not_allowed'
    if not request_filtering and not loopback(page['url']):
        return 'request_filter_unavailable_for_remote_effects'
    return None


def replay_plan(scenario, steps):
    return {'version': 'web-replay-v1', 'scenario_sha256': hashlib.sha256(
        json.dumps(scenario, sort_keys=True, ensure_ascii=False).encode()).hexdigest(), 'steps': steps}


def validate_replay(scenario, plan, operations):
    if not isinstance(plan, dict) or set(plan) != {'version', 'scenario_sha256', 'steps'} or \
            plan['version'] != 'web-replay-v1' or plan['scenario_sha256'] != replay_plan(scenario, [])['scenario_sha256'] or \
            not isinstance(plan['steps'], list) or len(plan['steps']) > 99:
        raise ValueError('replay must bind exact scenario and bounded steps')
    for step in plan['steps']:
        if not isinstance(step, dict) or set(step) - {'operation', 'target', 'value'} or step.get('operation') not in operations or step['operation'] in ('done', 'blocked', 'observe_more'):
            raise ValueError('invalid replay operation')
        target = step.get('target')
        if step['operation'] != 'scroll_down':
            if not isinstance(target, dict) or not {'role', 'name'} <= set(target) <= {'role', 'name', 'near'} or any(not isinstance(v, str) or not v or redact(v) != v for v in target.values()):
                raise ValueError('replay needs unredacted exact role/name and optional near')
            for value in target.values():
                safe_text(value, 120)
        if step['operation'] in ('fill', 'fill_submit') and step.get('value') not in scenario.get('values', {}):
            raise ValueError('replay value must name a scenario fixture')


def replay_decision(plan, page, step):
    saved = plan['steps'][step - 1] if step <= len(plan['steps']) else {'operation': 'done'}
    target = saved.get('target')
    found = [e for e in page['elements'] if all(e.get(k) == v for k, v in target.items())] if target else []
    if target and len(found) != 1:
        raise SafetyStop('replay_target_missing_or_ambiguous')
    decision = {'operation': {'choice': saved['operation'], 'confidence': None, 'probabilities': {}},
                'risk': None, 'hold': False, 'latency_s': 0, 'cost': 0, 'cached': False,
                'response_model': None, 'decision_source': 'replay'}
    if found:
        decision['target'] = {'choice': found[0]['ref']}
    if 'value' in saved:
        decision['value'] = {'choice': saved['value']}
    return decision
