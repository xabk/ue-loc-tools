"""Addressing a task list by name from the command line.

A task list is named by a short key meant to be typed. Its title is what the
menu shows, and it resolves too, as long as it picks out one list.
"""

import pytest

from libraries.task_runner import TaskRunner


def task_list(group, title, description=''):
    return {
        'group': group,
        'title': title,
        'description': description,
        'steps': [],
    }


@pytest.fixture
def runner():
    r = TaskRunner()
    r.config = {
        'crowdin': {'project_id': 1},
        'parameters': {'stop-on-errors': True},
        'script-parameters': {},
        'tasks': {},
        'sync.full': task_list(
            'ALL TARGETS', 'Full sync', 'P4: Check Out, Crowdin: Update Source'
        ),
        'sync.pull': task_list(
            'ALL TARGETS', 'Download only', 'P4: Check Out, Crowdin: Download'
        ),
        'source.manual': task_list('ONE OFF', 'Manual upload'),
    }
    return r


def test_the_name_is_what_you_type(runner):
    assert runner.resolve_task_list_name('sync.full') == 'sync.full'


def test_the_title_also_finds_it(runner):
    assert runner.resolve_task_list_name('Full sync') == 'sync.full'


def test_surrounding_whitespace_is_forgiven(runner):
    assert runner.resolve_task_list_name('  Full sync  ') == 'sync.full'


def test_a_name_that_matches_nothing_says_so(runner):
    with pytest.raises(ValueError, match='not found in configuration'):
        runner.resolve_task_list_name('sync.nope')


def test_a_prefix_is_not_a_match(runner):
    """Matching loosely would make the choice depend on what else is
    configured, and this picks which strings reach translators."""
    with pytest.raises(ValueError, match='not found in configuration'):
        runner.resolve_task_list_name('sync.ful')


def test_a_config_section_is_never_a_task_list(runner):
    with pytest.raises(ValueError, match='not found in configuration'):
        runner.resolve_task_list_name('parameters')


def test_an_ambiguous_title_refuses_and_names_the_candidates(runner):
    """Two lists can share a title and differ only in their steps. Running
    either on a guess is worse than not running."""
    runner.config['sync.full-console'] = task_list(
        'ALL TARGETS', 'Full sync', 'P4: Check Out, Crowdin: Console branch'
    )

    with pytest.raises(ValueError) as err:
        runner.resolve_task_list_name('Full sync')

    message = str(err.value)
    assert 'matches 2 lists' in message
    # The names are what tells them apart, so they have to be in the message.
    assert 'sync.full' in message and 'sync.full-console' in message


def test_an_exact_name_wins_over_an_ambiguous_title(runner):
    runner.config['sync.full-console'] = task_list('ALL TARGETS', 'Full sync')

    assert runner.resolve_task_list_name('sync.full') == 'sync.full'
