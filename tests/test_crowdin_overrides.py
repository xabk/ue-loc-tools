"""Crowdin credentials can come from the command line instead of a file, so a
caller decides where its secrets live and nothing has to be committed."""

import pytest

from conftest import TEMPLATE_BASE, write_config
from libraries.task_runner import TaskRunner


@pytest.fixture
def base(config, tmp_path):
    return write_config(
        tmp_path / 'base.config.yaml',
        {'tasks': config['tasks'], 'parameters': {'loc_targets': ['Game']}},
    )


@pytest.fixture
def secret(tmp_path):
    return write_config(
        tmp_path / 'crowdin.config.yaml',
        {'crowdin': {'organization': 'from-file', 'token': 'file-token', 'project_id': 1}},
    )


def load(base, secret, **overrides):
    runner = TaskRunner()
    runner.unattended = True
    runner.load_config(str(base), str(secret), overrides or None)
    return runner


def test_overrides_win_over_the_secret_file(base, secret):
    runner = load(base, secret, token='cli-token', project_id=42)

    assert runner.config['crowdin']['token'] == 'cli-token'
    assert runner.config['crowdin']['project_id'] == 42
    assert runner.config['crowdin']['organization'] == 'from-file'


def test_none_values_do_not_erase_the_file(base, secret):
    runner = load(base, secret, token=None, organization=None, project_id=None)

    assert runner.config['crowdin']['token'] == 'file-token'
    assert runner.config['crowdin']['project_id'] == 1


def test_a_token_makes_the_secret_file_optional(base, tmp_path):
    runner = load(base, tmp_path / 'nope.yaml', token='cli-token', project_id=7)

    assert runner.config['crowdin']['token'] == 'cli-token'


def test_a_missing_secret_file_without_a_token_still_raises(base, tmp_path):
    with pytest.raises(FileNotFoundError):
        load(base, tmp_path / 'nope.yaml', organization='acme')


def test_overrides_reach_the_task(base, secret):
    runner = load(base, secret, token='cli-token', project_id=42)
    task = runner.create_task_instance(
        'build-and-download', {'script': 'build-and-download'}
    )

    assert task.token == 'cli-token'
    assert task.project_id == 42


def test_the_token_is_not_logged(base, secret, tmp_path):
    from loguru import logger

    log = tmp_path / 'run.log'
    logger.remove()
    logger.add(str(log), format='{message}', level='TRACE')
    load(base, secret, token='super-secret-cli-token')
    logger.remove()

    assert 'super-secret-cli-token' not in log.read_text(encoding='utf-8')
