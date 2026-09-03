"""The confirmation prompt offers to go back to the task list. It has to
actually do that: returning None instead made loc-sync fail the config lookup
with "Task list 'None' not found in configuration"."""

import pytest

from libraries.task_runner import TaskRunner

FIRST = 'First list\nP4: Check Out, UE: Gather'
SECOND = 'Second list\nCrowdin: Update Source'


def make_runner() -> TaskRunner:
    runner = TaskRunner()
    runner.unattended = False
    runner.config = {
        'parameters': {'not': 'a task list'},
        FIRST: [{'description': 'one', 'script': 'test-lang'}],
        SECOND: [
            {'description': 'two', 'script': 'update-source-files', 'updates-source': True}
        ],
    }
    return runner


def answers(monkeypatch, *replies):
    """Feed the prompts in order, and fail rather than hang if it asks again."""
    queue = list(replies)

    def fake_input(_prompt=''):
        if not queue:
            raise AssertionError('asked for more input than the test provided')
        return queue.pop(0)

    monkeypatch.setattr('builtins.input', fake_input)
    return queue


def test_confirming_returns_the_chosen_list(monkeypatch):
    left = answers(monkeypatch, '1', 'Y')

    assert make_runner().get_task_list_from_user() == FIRST
    assert left == []


def test_lower_case_y_also_confirms(monkeypatch):
    answers(monkeypatch, '1', 'y')

    assert make_runner().get_task_list_from_user() == FIRST


def test_declining_goes_back_to_the_selection(monkeypatch):
    """'n' at the confirmation returns to the menu, where a different list can
    be picked. It used to return None and blow up in loc-sync."""
    left = answers(monkeypatch, '1', 'n', '2', 'Y')

    assert make_runner().get_task_list_from_user() == SECOND
    assert left == []


def test_declining_repeatedly_keeps_going_back(monkeypatch):
    answers(monkeypatch, '1', 'n', '2', 'no', '1', 'Y')

    assert make_runner().get_task_list_from_user() == FIRST


def test_it_never_returns_none(monkeypatch):
    answers(monkeypatch, '2', 'anything else', '2', 'Y')

    assert make_runner().get_task_list_from_user() is not None


def test_a_list_can_be_chosen_by_name(monkeypatch):
    answers(monkeypatch, SECOND, 'Y')

    assert make_runner().get_task_list_from_user() == SECOND


def test_choosing_by_name_does_not_report_invalid_input(monkeypatch, capsys):
    """The name was accepted; only the int() after it failed."""
    answers(monkeypatch, FIRST, 'Y')

    make_runner().get_task_list_from_user()

    assert 'Invalid input' not in capsys.readouterr().out


def test_a_bad_choice_asks_again(monkeypatch, capsys):
    answers(monkeypatch, '99', 'not a list', '1', 'Y')

    assert make_runner().get_task_list_from_user() == FIRST
    assert 'Invalid input' in capsys.readouterr().out


def test_config_sections_are_not_offered_as_task_lists(monkeypatch, capsys):
    answers(monkeypatch, '1', 'Y')

    make_runner().get_task_list_from_user()

    out = capsys.readouterr().out
    assert 'parameters' not in out.split('Selected task list')[0]


def test_a_source_updating_list_warns_before_confirming(monkeypatch, capsys):
    answers(monkeypatch, '2', 'Y')

    make_runner().get_task_list_from_user()

    assert 'update the source files' in capsys.readouterr().out


def test_unattended_refuses_to_prompt():
    runner = make_runner()
    runner.unattended = True

    with pytest.raises(ValueError):
        runner.get_task_list_from_user()
