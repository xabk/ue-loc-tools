"""Windows' 260-character path limit, caught before Python trips over it.

uv installs past the limit without a word, and Python then cannot import from
there: on a workspace a little too deep, six of ten tasks went missing with
"No module named 'crowdin_api...'".
"""

import os
from pathlib import Path

import pytest
from loguru import logger

from libraries import environment as env


@pytest.fixture
def logged():
    captured = []
    sink_id = logger.add(lambda m: captured.append(m.record), level='DEBUG')
    yield captured
    logger.remove(sink_id)


def venv_of_length(length: int) -> Path:
    return Path('C:/' + 'v' * (length - 3))


def test_the_allowance_covers_the_deepest_file_in_the_real_venv():
    """The check is arithmetic on VENV_DEEPEST_PATH, so it has to stay true:
    a dependency that installs deeper fails here, not on someone's machine."""
    venv = env.current_venv()
    if venv is None:
        pytest.skip('not running in a venv')

    deepest = max(
        len(os.path.relpath(os.path.join(root, f), venv))
        for root, _dirs, files in os.walk(venv)
        for f in files
    )

    assert deepest <= env.VENV_DEEPEST_PATH, (
        f'A file in the venv is {deepest} characters deep. '
        f'Raise VENV_DEEPEST_PATH from {env.VENV_DEEPEST_PATH}.'
    )


def test_a_short_venv_never_asks_the_registry(monkeypatch):
    def fail():
        raise AssertionError('registry read for a path well within the limit')

    monkeypatch.setattr(env, 'long_paths_enabled', fail)

    assert env.report_venv_path_length(venv_of_length(60), blocking=True) == 0


def test_too_deep_blocks_and_says_how_much_shorter_the_path_must_be(
    monkeypatch, logged
):
    monkeypatch.setattr(env, 'long_paths_enabled', lambda: False)

    assert env.report_venv_path_length(venv_of_length(176), blocking=True) == 1

    message = logged[-1]['message']
    assert logged[-1]['level'].name == 'ERROR'
    # 176 + 1 + VENV_DEEPEST_PATH = 307, and the longest path is 259
    assert 'at least 48 characters shorter' in message
    assert 'long path' not in message.lower()


def test_too_deep_is_fine_once_long_paths_are_on(monkeypatch, logged):
    monkeypatch.setattr(env, 'long_paths_enabled', lambda: True)

    assert env.report_venv_path_length(venv_of_length(176), blocking=True) == 0
    assert logged == []


def test_at_launch_it_only_warns(monkeypatch, logged):
    monkeypatch.setattr(env, 'long_paths_enabled', lambda: False)

    assert env.report_venv_path_length(venv_of_length(176), blocking=False) == 0
    assert logged[-1]['level'].name == 'WARNING'


def test_the_limit_is_where_windows_puts_it(monkeypatch):
    """260 including the terminator, so 259 characters is the longest path."""
    monkeypatch.setattr(env, 'long_paths_enabled', lambda: False)
    fits = env.WINDOWS_MAX_PATH - 1 - 1 - env.VENV_DEEPEST_PATH

    assert env.report_venv_path_length(venv_of_length(fits), blocking=True) == 0
    assert env.report_venv_path_length(venv_of_length(fits + 1), blocking=True) == 1


def test_no_venv_is_nothing_to_check():
    assert env.report_venv_path_length(None, blocking=True) == 0
