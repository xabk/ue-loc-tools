"""Addressing a task list by name from the command line.

Task list names run over two lines: a title, then the steps. The menu prints
both, but a newline cannot be typed into -u, so before this the two-line lists
the template itself tells you to write could not be run unattended at all.
"""

import pytest

from libraries.task_runner import TaskRunner

FULL = (
    'ALL TARGETS: Full sync\n'
    'P4: Check Out, UE: Gather + Export, Crowdin: Update Source'
)
DOWNLOAD = (
    'ALL TARGETS: Download only\nP4: Check Out, Crowdin: Build + Download'
)
SINGLE = '[SRV] Manual upload'


@pytest.fixture
def runner():
    r = TaskRunner()
    r.config = {
        'crowdin': {'project_id': 1},
        'parameters': {'stop-on-errors': True},
        'script-parameters': {},
        'tasks': {},
        FULL: [],
        DOWNLOAD: [],
        SINGLE: [],
    }
    return r


def test_the_title_alone_finds_a_two_line_name(runner):
    assert runner.resolve_task_list_name('ALL TARGETS: Full sync') == FULL


def test_the_whole_name_still_works(runner):
    assert runner.resolve_task_list_name(FULL) == FULL


def test_a_single_line_name_is_unaffected(runner):
    assert runner.resolve_task_list_name(SINGLE) == SINGLE


def test_surrounding_whitespace_is_forgiven(runner):
    assert runner.resolve_task_list_name('  ALL TARGETS: Full sync  ') == FULL


def test_a_title_that_matches_nothing_says_so(runner):
    with pytest.raises(ValueError, match='not found in configuration'):
        runner.resolve_task_list_name('ALL TARGETS: Nope')


def test_a_prefix_of_a_title_is_not_a_match(runner):
    """Matching loosely would make the choice depend on what else is
    configured, and this picks which strings reach translators."""
    with pytest.raises(ValueError, match='not found in configuration'):
        runner.resolve_task_list_name('ALL TARGETS: Full')


def test_a_config_section_is_never_a_task_list(runner):
    with pytest.raises(ValueError, match='not found in configuration'):
        runner.resolve_task_list_name('parameters')


def test_an_ambiguous_title_refuses_and_shows_the_difference(runner):
    """Two lists can share a title and differ only in their steps. Running
    either on a guess is worse than not running."""
    other = 'ALL TARGETS: Full sync\nA different pipeline'
    runner.config[other] = []

    with pytest.raises(ValueError) as err:
        runner.resolve_task_list_name('ALL TARGETS: Full sync')

    message = str(err.value)
    assert 'matches 2 lists' in message
    # The titles are identical, so the steps are what tells them apart.
    assert 'Crowdin: Update Source' in message
    assert 'A different pipeline' in message


def test_an_exact_name_wins_over_an_ambiguous_title(runner):
    runner.config['ALL TARGETS: Full sync\nA different pipeline'] = []

    assert runner.resolve_task_list_name(FULL) == FULL
