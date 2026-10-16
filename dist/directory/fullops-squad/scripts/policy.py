"""운영 모드와 테스트 범위의 정본을 읽는다. 역할·브랜치·기존 검사 계약은 보존한다."""
import json
from pathlib import Path
import re
import subprocess


LEVELS = ('minimal', 'lite', 'standard', 'full', 'exhaustive')
SUBAGENT_LEVELS = ('off', 'lite', 'standard', 'full')
TEST_BRIEF = {
    'minimal': '기동과 변경 경로의 스모크 검사만 수행한다.',
    'lite': '변경한 핵심 동작과 필요한 실패 경계만 짧게 검증한다. 사소한 문구 변경에는 새 테스트를 만들지 않는다.',
    'standard': '변경 동작·실패 경계와 영향을 받는 연동의 회귀를 검증한다.',
    'full': '안정된 통합 후보에서 전체 자동 회귀와 필요한 통합·수락 검사를 담당자별로 한 번 수행한다.',
    'exhaustive': 'full 범위에 프로젝트에 필요한 E2E·성능·장시간·환경 검수를 더해 안정된 후보에서 한 번 수행한다.',
}
SUBAGENT_BRIEF = {
    'off': '선택형 하위 위임을 사용하지 않는다.',
    'lite': '독립 조사·리뷰 하위 에이전트를 최대 1개 활용한다.',
    'standard': '파일 소유를 분리한 병렬 구현을 포함해 하위 에이전트를 최대 2개 활용한다.',
    'full': '독립 작업의 하위 에이전트를 최대 4개 활용한다.',
}


class PolicyError(ValueError):
    pass


def transition_path(root):
    common = Path(subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--git-common-dir'], text=True).strip())
    return (common if common.is_absolute() else Path(root) / common).resolve() / 'fullops-mode-transition.json'


def validate(config):
    if not isinstance(config, dict) or config.get('schema_version') != 1 or not isinstance(config.get('roles', {}), dict):
        raise PolicyError('FullOps 설정의 schema_version·roles를 확인하세요')
    mode = config.get('mode', 'coor')
    level = config.get('test_level', 'standard')
    subagent_level = config.get('subagent_level', 'off')
    if mode not in ('coor', 'dev'):
        raise PolicyError('mode는 coor 또는 dev여야 합니다. setup.py --mode로 수정하세요')
    if level not in LEVELS:
        raise PolicyError('test_level은 ' + ', '.join(LEVELS) + ' 중 하나여야 합니다')
    if subagent_level not in SUBAGENT_LEVELS:
        raise PolicyError('subagent_level은 ' + ', '.join(SUBAGENT_LEVELS) + ' 중 하나여야 합니다')
    role, branch = config.get('primary_role'), config.get('primary_branch')
    if role is not None and (not isinstance(role, str) or role not in config.get('roles', {})):
        raise PolicyError('primary_role은 등록된 역할이어야 합니다')
    if mode == 'dev' and (not role or not isinstance(branch, str) or branch == 'HEAD' or
                         not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', branch)):
        raise PolicyError('dev 모드의 primary_role·primary_branch를 setup.py에서 지정하세요')
    return {**config, 'mode': mode, 'test_level': level, 'subagent_level': subagent_level}


def load(root):
    if transition_path(root).exists():
        raise PolicyError('운영 모드 전환이 중단됐습니다. 같은 setup 명령으로 재개하거나 --rollback으로 복구하세요')
    path = Path(root) / '.fullops-squad/fullops.json'
    try:
        return validate(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError) as error:
        if isinstance(error, PolicyError):
            raise
        raise PolicyError('FullOps 설정을 읽지 못했습니다. setup.py에서 복구하세요') from error


def identity(root, config, coordinator=None, dispatched=False):
    process = subprocess.run(['git', '-C', str(root), 'symbolic-ref', '--short', 'HEAD'], capture_output=True, text=True)
    branch = process.stdout.strip() if process.returncode == 0 else subprocess.check_output(
        ['git', '-C', str(root), 'rev-parse', '--abbrev-ref', 'HEAD'], text=True).strip()
    role = next((role for role, name in config['roles'].items() if name == branch), None)
    if config['mode'] == 'coor':
        primary = role is None or role == (config.get('primary_role') or coordinator)
        return ('coordinator' if primary else role), primary and not dispatched
    primary = branch == config['primary_branch'] or role == config['primary_role']
    return (config['primary_role'] if primary else role or 'unregistered'), primary and not dispatched


def test_brief(level):
    if level not in LEVELS:
        raise PolicyError('알 수 없는 테스트 레벨')
    return (f'테스트 레벨 {level}: {TEST_BRIEF[level]} 보안·데이터 손실 방지와 프로젝트 필수 검사는 모든 레벨에서 유지한다. '
            '검사가 통과하면 인계하고, 새 변경·실패·근거 결함이 있을 때만 재검증한다.')


def command_selected(command, level):
    if level not in LEVELS or ('required' in command and type(command['required']) is not bool):
        raise PolicyError('검사 test_level·required(boolean)를 확인하세요')
    minimum = command.get('level')
    if minimum is not None and (minimum not in LEVELS or command.get('kind') != 'test'):
        raise PolicyError('검사 level은 test 명령의 ' + ', '.join(LEVELS) + '만 허용합니다')
    # Untagged commands remain mandatory; adopting levels cannot silently weaken an existing gate.
    return minimum is None or command.get('required', False) or LEVELS.index(minimum) <= LEVELS.index(level)


def subagent_brief(level):
    if level not in SUBAGENT_LEVELS:
        raise PolicyError('알 수 없는 하위 에이전트 레벨')
    return (f'하위 에이전트 레벨 {level}: {SUBAGENT_BRIEF[level]} 테스트 레벨과 독립된 선택형 위임 예산이며 '
            '호스트 전체 프로세스의 강제 제한이 아니다. 필수 역할 배정·독립 리뷰는 별도 계약으로 유지한다. '
            '하위 에이전트는 부모 권한·테스트 레벨을 상속하고 런타임 깊이 제한을 따른다. '
            '위임 전 rules/delegation.md를 읽고 지시에 Purpose: research|review|implementation을 선언한다. '
            '부모는 결과를 취합하고 완료 전에 하위 작업을 회수한다.')


def at_ref(root, ref):
    """작업 브랜치가 기준 설정의 검사 범위를 낮추지 못하게 한다."""
    process = subprocess.run(['git', '-C', str(root), 'cat-file', 'blob',
                              f'{ref}:.fullops-squad/fullops.json'], capture_output=True)
    raw = process.stdout if process.returncode == 0 else None
    config = validate(json.loads(raw)) if raw else {'test_level': 'standard'}
    import hashlib
    return config['test_level'], hashlib.sha256(raw).hexdigest() if raw else None
