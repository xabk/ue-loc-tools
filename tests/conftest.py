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
