"""What the project needs from the machine, and how loudly to say it.

The rule these tests pin down: a missing tool or a major version difference
stops a task list that needs it; anything smaller is a warning. A project that
never runs the task never hears about it at all.
"""

import pytest
from loguru import logger

from libraries.environment import (
    check_before_running,
    crowdin_cli_state,
    report_crowdin_cli,
    report_p4_settings,
    report_unreal_binary,
    task_list_needs,
)


@pytest.fixture
def logged():
    captured = []
    sink_id = logger.add(lambda m: captured.append(m.record), level='DEBUG')
    yield captured
    logger.remove(sink_id)


def levels(records) -> set[str]:
    return {r['level'].name for r in records}


def messages(records) -> str:
    return '\n'.join(r['message'] for r in records)


# --------------------------- version states --------------------------- #


@pytest.mark.parametrize(
    'installed,pinned,expected',
    [
        ('5.0.1', '5.0.1', 'match'),
        (None, '5.0.1', 'missing'),
        ('5.0.1', None, 'no_pin'),
        ('4.15.1', '5.0.1', 'major'),
        ('6.0.0', '5.0.1', 'major'),
        ('5.1.0', '5.0.1', 'minor'),
        ('5.0.2', '5.0.1', 'patch'),
        # Crowdin's previews are semver, which packaging.version rejects.
        ('5.0.0-next.6', '5.0.1', 'patch'),
        ('5.0.0-next.6', '4.9.0', 'major'),
        ('nonsense', '5.0.1', 'unknown'),
    ],
)
def test_version_states(installed, pinned, expected):
    assert crowdin_cli_state(installed, pinned) == expected


# --------------------------- how loudly --------------------------- #


def test_a_major_difference_blocks_a_list_that_uploads(logged):
    assert report_crowdin_cli('major', '4.15.1', '5.0.1', blocking=True) == 1
    assert 'ERROR' in levels(logged)


def test_a_minor_difference_only_warns_even_when_blocking(logged):
    """Your call: a minor bump is worth knowing about, not worth stopping."""
    assert report_crowdin_cli('minor', '5.1.0', '5.0.1', blocking=True) == 0
    assert 'ERROR' not in levels(logged)
    assert 'WARNING' in levels(logged)


def test_a_patch_difference_only_warns(logged):
    assert report_crowdin_cli('patch', '5.0.2', '5.0.1', blocking=True) == 0
    assert 'ERROR' not in levels(logged)


def test_a_missing_cli_blocks_a_list_that_uploads(logged):
    assert report_crowdin_cli('missing', None, '5.0.1', blocking=True) == 1
    assert 'ERROR' in levels(logged)
    assert 'update-loc-tools.bat' in messages(logged)


def test_a_missing_cli_only_warns_at_launch(logged):
    """Launch does not know which list will be picked, so it never blocks."""
    assert report_crowdin_cli('missing', None, '5.0.1', blocking=False) == 0
    assert 'ERROR' not in levels(logged)
    assert 'update-loc-tools.bat' in messages(logged)


def test_a_matching_cli_says_so_and_is_silent_otherwise(logged):
    assert report_crowdin_cli('match', '5.0.1', '5.0.1', blocking=False) == 0
    assert 'ERROR' not in levels(logged)
    assert 'WARNING' not in levels(logged)


def test_missing_unreal_binary_blocks_a_ue_list(tmp_path, logged):
    assert report_unreal_binary(tmp_path / 'UE4Editor-Cmd.exe', blocking=True) == 1
    assert 'ERROR' in levels(logged)


def test_missing_unreal_binary_only_warns_at_launch(tmp_path, logged):
    assert report_unreal_binary(tmp_path / 'UE4Editor-Cmd.exe', blocking=False) == 0
    assert 'ERROR' not in levels(logged)
    assert 'WARNING' in levels(logged)


def test_an_unresolvable_binary_is_still_a_problem(logged):
    assert report_unreal_binary(None, blocking=True) == 1


def test_a_present_binary_is_fine(tmp_path):
    binary = tmp_path / 'UE4Editor-Cmd.exe'
    binary.touch()

    assert report_unreal_binary(binary, blocking=True) == 0


def test_missing_p4_settings_block_a_list_that_checks_out(tmp_path, logged):
    assert report_p4_settings(tmp_path / 'nope.ini', blocking=True) == 1
    assert 'ERROR' in levels(logged)


def test_missing_p4_settings_only_warn_at_launch(tmp_path, logged):
    """A project whose CI checks files out externally never runs p4-checkout,
    so it must not be told its Perforce setup is broken."""
    assert report_p4_settings(tmp_path / 'nope.ini', blocking=False) == 0
    assert 'ERROR' not in levels(logged)


# --------------------------- what a list needs --------------------------- #


class FakeRunner:
    """create_task_instance only has to answer the cli questions here."""

    def __init__(self, cli_upload=False, add_files_only=False, explode=False):
        self.cli_upload = cli_upload
        self.add_files_only = add_files_only
        self.explode = explode

    def create_task_instance(self, script, entry):
        if self.explode:
            raise RuntimeError('cannot build')
        merged = dict(entry.get('script-parameters') or {})
        return type(
            'T',
            (),
            {
                'cli_upload': merged.get('cli_upload', self.cli_upload),
                'add_files_only': merged.get('add_files_only', self.add_files_only),
            },
        )()


def test_a_gather_step_needs_unreal():
    needs = task_list_needs(FakeRunner(), [{'script': 'ue-loc-gather-cmd'}])

    assert needs == {'ue'}


def test_a_ue_python_step_needs_unreal_too():
    """`unreal: True` runs through the editor's Python and needs the binary."""
    needs = task_list_needs(FakeRunner(), [{'script': 'anything', 'unreal': True}])

    assert needs == {'ue'}


def test_a_checkout_step_needs_perforce():
    needs = task_list_needs(FakeRunner(), [{'script': 'p4-checkout'}])

    assert needs == {'p4'}


def test_a_source_update_needs_the_cli_when_configured_to_use_it():
    entry = {'script': 'update-source-files', 'script-parameters': {'cli_upload': True}}

    assert task_list_needs(FakeRunner(), [entry]) == {'cli'}


def test_a_source_update_without_cli_upload_does_not_need_the_cli():
    entry = {
        'script': 'update-source-files',
        'script-parameters': {'cli_upload': False},
    }

    assert task_list_needs(FakeRunner(), [entry]) == set()


def test_adding_files_needs_the_cli():
    entry = {
        'script': 'update-source-files',
        'script-parameters': {'add_files_only': True},
    }

    assert task_list_needs(FakeRunner(), [entry]) == {'cli'}


def test_an_unbuildable_task_is_assumed_to_need_the_cli():
    """Better a warning that turns out to be unnecessary than a silent skip."""
    entry = {'script': 'update-source-files'}

    assert task_list_needs(FakeRunner(explode=True), [entry]) == {'cli'}


def test_a_full_cycle_needs_everything():
    tasks = [
        {'script': 'p4-checkout'},
        {'script': 'ue-loc-gather-cmd'},
        {'script': 'test-lang'},
        {'script': 'update-source-files', 'script-parameters': {'cli_upload': True}},
    ]

    assert task_list_needs(FakeRunner(), tasks) == {'p4', 'ue', 'cli'}


def test_a_list_needing_nothing_is_checked_for_nothing(monkeypatch):
    """test-lang is pure local file work, so nothing should be probed."""
    probed = []
    monkeypatch.setattr(
        'libraries.environment.resolved_task_path',
        lambda *a: probed.append(a) or None,
    )

    assert check_before_running(FakeRunner(), [{'script': 'test-lang'}]) == 0
    assert probed == []
