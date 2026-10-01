"""Getting the pinned Crowdin CLI onto the machine.

A major difference stops a task list that uploads, so leaving it merely
reported leaves the project stuck -- and what it told you to run was the script
that did the reporting. Setting a project up installs over it now.

The one case installing cannot fix is the pinned version already being there
while an older major answers on PATH first. Installing again would change
nothing, so that one says what to remove.
"""

import importlib.util

import pytest
from loguru import logger

from libraries import environment as env

PINNED = '5.3.0'

WINGET_TABLE = """Name        Id                 Version Available Source
-------------------------------------------------------
Crowdin CLI Crowdin.CrowdinCLI 5.3.0   5.3.0     winget
"""


@pytest.fixture(scope='session')
def gc(repo_root):
    path = repo_root / 'loc-project.py'
    spec = importlib.util.spec_from_file_location('loc_project', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def logged():
    captured = []
    sink_id = logger.add(lambda m: captured.append(m.record), level='DEBUG')
    yield captured
    logger.remove(sink_id)


def messages(records) -> str:
    return chr(10).join(r['message'] for r in records)


class Run:
    """A stand-in for subprocess.run that answers one command."""

    def __init__(self, stdout='', returncode=0):
        self.stdout = stdout
        self.returncode = returncode


# --- reading what winget has installed


def test_the_installed_version_is_read_off_the_table(monkeypatch):
    monkeypatch.setattr(env.shutil, 'which', lambda name: 'winget')
    monkeypatch.setattr(
        env.subprocess, 'run', lambda *a, **k: Run(WINGET_TABLE)
    )

    assert env.winget_crowdin_versions() == [PINNED]


def test_no_winget_means_nothing_is_known(monkeypatch):
    """The CLI also ships as a plain installer, so winget knowing nothing is
    not the same as nothing being installed."""
    monkeypatch.setattr(env.shutil, 'which', lambda name: None)

    assert env.winget_crowdin_versions() == []


def test_a_winget_that_fails_is_not_an_answer(monkeypatch):
    monkeypatch.setattr(env.shutil, 'which', lambda name: 'winget')
    monkeypatch.setattr(
        env.subprocess, 'run', lambda *a, **k: Run('', returncode=1)
    )

    assert env.winget_crowdin_versions() == []


# --- the pinned version installed, an older one answering


@pytest.mark.parametrize('on_path', ['4.15.1', '5.0.1'])
def test_another_version_answering_over_the_pinned_one_is_spotted(
    monkeypatch, on_path
):
    """A major apart or a minor apart: either way the pinned one is already
    there and PATH reaches the other first."""
    monkeypatch.setattr(env, 'winget_crowdin_versions', lambda: [PINNED])

    assert env.shadowed_install(on_path, PINNED) == on_path


def test_nothing_is_shadowed_when_the_pin_is_not_installed(monkeypatch):
    """Then installing is exactly the right move."""
    monkeypatch.setattr(env, 'winget_crowdin_versions', lambda: ['4.15.1'])

    assert env.shadowed_install('4.15.1', PINNED) is None


def test_the_pinned_version_itself_is_not_a_shadow(monkeypatch):
    monkeypatch.setattr(env, 'winget_crowdin_versions', lambda: [PINNED])

    assert env.shadowed_install(PINNED, PINNED) is None


# --- what the messages actually say


def test_a_major_difference_names_the_install_command(logged):
    env.report_crowdin_cli('major', '4.15.1', PINNED, blocking=False)

    said = messages(logged)
    assert f'winget install --id {env.CROWDIN_WINGET_ID} -e --version {PINNED}' in said


def test_a_shadowed_install_names_the_uninstall_command(logged):
    env.report_crowdin_cli('major', '4.15.1', PINNED, blocking=False, shadowed='4.15.1')

    said = messages(logged)
    assert f'winget uninstall --id {env.CROWDIN_WINGET_ID} -e --version 4.15.1' in said
    assert 'Installing again will not help' in said
    assert 'Apps & features' in said


def test_a_missing_cli_names_the_install_command(logged):
    env.report_crowdin_cli('missing', None, PINNED, blocking=False)

    assert f'--version {PINNED}' in messages(logged)


def test_reporting_never_shells_out(monkeypatch, logged):
    """It is called from a sync, and it is asserted on in tests. Looking the
    shadow up here would make both depend on what this machine has installed."""

    def fail(*args, **kwargs):
        raise AssertionError('report_crowdin_cli ran a subprocess')

    monkeypatch.setattr(env.subprocess, 'run', fail)

    for state in ('missing', 'major', 'minor', 'patch', 'unknown', 'match'):
        env.report_crowdin_cli(state, '4.15.1', PINNED, blocking=False)


# --- what setting a project up does


def install_calls(monkeypatch, gc, installed, shadowed=None):
    calls = []
    monkeypatch.setattr(gc, 'pinned_crowdin_cli_version', lambda: PINNED)
    monkeypatch.setattr(gc, 'installed_crowdin_cli_version', lambda: installed)
    monkeypatch.setattr(gc, 'shadowed_install', lambda i, p: shadowed)
    monkeypatch.setattr(
        gc, 'install_crowdin_cli', lambda v: calls.append(v) or True
    )
    return calls


def test_a_missing_cli_is_installed(monkeypatch, gc):
    calls = install_calls(monkeypatch, gc, installed=None)

    assert gc.check_crowdin_cli(install_missing=True) is True
    assert calls == [PINNED]


def test_a_different_major_is_installed_over(monkeypatch, gc):
    calls = install_calls(monkeypatch, gc, installed='4.15.1')

    assert gc.check_crowdin_cli(install_missing=True) is True
    assert calls == [PINNED]


def test_a_shadowed_install_is_reported_rather_than_repeated(monkeypatch, gc):
    calls = install_calls(monkeypatch, gc, installed='4.15.1', shadowed='4.15.1')

    assert gc.check_crowdin_cli(install_missing=True) is False
    assert calls == []


def test_a_minor_difference_is_installed_over_too(monkeypatch, gc):
    """Pinning is the point. Left alone, the machine never catches up and the
    advice is to run the script that just declined."""
    calls = install_calls(monkeypatch, gc, installed='5.0.1')

    gc.check_crowdin_cli(install_missing=True)

    assert calls == [PINNED]


def test_the_pinned_version_is_left_alone(monkeypatch, gc):
    calls = install_calls(monkeypatch, gc, installed=PINNED)

    assert gc.check_crowdin_cli(install_missing=True) is True
    assert calls == []


def test_a_sync_never_installs(monkeypatch, gc):
    """Only setting a project up installs. A sync says so and carries on."""
    calls = install_calls(monkeypatch, gc, installed='4.15.1')

    gc.check_crowdin_cli(install_missing=False)

    assert calls == []
