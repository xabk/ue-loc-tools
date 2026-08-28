import os
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from libraries.task_runner import TaskRunner  # noqa: E402

TEMPLATE_BASE = REPO_ROOT / 'templates' / 'base.config.yaml'
TEMPLATE_SECRET = REPO_ROOT / 'templates' / 'crowdin.config.yaml'

# Sections under script-parameters that are not registered tasks: standalone
# scripts with their own parsers, configured in the same file for convenience.
NON_TASK_SECTIONS = {'targets', 'ue-reimport-assets'}


@pytest.fixture(scope='session')
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope='session')
def runner() -> TaskRunner:
    runner = TaskRunner()
    runner.unattended = True
    runner.load_config(str(TEMPLATE_BASE), str(TEMPLATE_SECRET))
    return runner


@pytest.fixture(scope='session')
def config(runner: TaskRunner) -> dict:
    return runner.config


@pytest.fixture(scope='session')
def task_lists(config: dict) -> dict:
    return {k: v for k, v in config.items() if isinstance(v, list)}


def write_config(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data), encoding='utf-8')
    return path


# ------------------------------ live Crowdin ------------------------------ #
# Credentials live outside every repo, in the file LOCTOOLS_TEST_SECRET points
# at, so the same machine setup serves every project. These tests are marked
# `crowdin` and excluded from the default run.

SECRET_ENV = 'LOCTOOLS_TEST_SECRET'
TEST_PROJECT_ID = 127


@pytest.fixture(scope='session')
def crowdin_credentials() -> dict:
    path = os.environ.get(SECRET_ENV)
    if not path:
        pytest.skip(f'{SECRET_ENV} is not set')

    secret = Path(path)
    if not secret.is_file():
        pytest.skip(f'{SECRET_ENV} points at a missing file: {secret}')

    crowdin = (yaml.safe_load(secret.read_text(encoding='utf-8')) or {}).get('crowdin')
    if not crowdin or not crowdin.get('token') or 'PASTE' in str(crowdin['token']):
        pytest.skip(f'no Crowdin token in {secret}')

    project_id = crowdin.get('project_id')
    if project_id != TEST_PROJECT_ID:
        pytest.fail(
            f'{secret} points at project {project_id}, but these tests only run '
            f'against the test project {TEST_PROJECT_ID}. They create and delete '
            'content, so refusing rather than touching a real project.',
            pytrace=False,
        )

    return crowdin


@pytest.fixture(scope='session')
def crowdin(crowdin_credentials: dict):
    from libraries.crowdin import UECrowdinClient

    return UECrowdinClient(
        crowdin_credentials['token'],
        organization=crowdin_credentials.get('organization'),
        project_id=crowdin_credentials['project_id'],
        silent=True,
    )
