"""A task list's description shares the title's line when both fit the
console, and gets a line of its own when not.

The default console is about 30 rows, so two lines for every list pushed the
everyday lists at the top of the menu out of view.
"""

import re

from libraries.task_runner import MENU_SEPARATOR, TaskRunner, menu_entry_lines

ANSI = re.compile(r'\x1b\[[0-9;]*m')


def plain(lines: list[str]) -> list[str]:
    return [ANSI.sub('', line) for line in lines]


def test_a_short_description_shares_the_line():
    assert plain(menu_entry_lines(1, 'Full sync', 'P4: Check Out', 120)) == [
        f' 1. Full sync{MENU_SEPARATOR}P4: Check Out'
    ]


def test_a_long_description_gets_its_own_line():
    description = 'Crowdin: ' + 'x' * 120

    assert plain(menu_entry_lines(1, 'Full sync', description, 120)) == [
        ' 1. Full sync',
        f'\t{description}',
    ]


def test_a_list_without_a_description_is_one_line():
    assert plain(menu_entry_lines(12, 'Import and compile in Unreal', '', 120)) == [
        '12. Import and compile in Unreal'
    ]


def test_the_line_stops_one_short_of_the_console_edge():
    """A line exactly as wide as the console wraps before its newline on some
    consoles and leaves an empty line under it, so it goes on two lines."""
    head = f' 1. Title{MENU_SEPARATOR}'
    fits = 'd' * (40 - len(head) - 1)
    too_wide = 'd' * (40 - len(head))

    assert len(menu_entry_lines(1, 'Title', fits, 40)) == 1
    assert len(menu_entry_lines(1, 'Title', too_wide, 40)) == 2


def make_runner() -> TaskRunner:
    runner = TaskRunner()
    runner.unattended = False
    runner.config = {
        'short': {
            'group': 'ALL TARGETS',
            'title': 'Pull the latest translations only',
            'description': 'P4: Check Out, Crowdin: Download AI and main, UE: Import + Compile',
            'steps': [{'description': 'one', 'script': 'test-lang'}],
        },
        'bare': {
            'group': 'ONE STEP',
            'title': 'Import and compile in Unreal',
            'steps': [{'description': 'two', 'script': 'test-lang'}],
        },
    }
    return runner


def menu(monkeypatch, capsys, columns: int) -> list[str]:
    monkeypatch.setenv('COLUMNS', str(columns))
    replies = iter(['1', 'y'])
    monkeypatch.setattr('builtins.input', lambda _prompt='': next(replies))
    make_runner().get_task_list_from_user()
    return plain(capsys.readouterr().out.splitlines())


def test_a_wide_console_gets_one_line_per_list(monkeypatch, capsys):
    out = menu(monkeypatch, capsys, 120)

    assert (
        ' 1. Pull the latest translations only / '
        'P4: Check Out, Crowdin: Download AI and main, UE: Import + Compile'
    ) in out
    assert ' 2. Import and compile in Unreal' in out


def test_a_narrow_console_moves_the_description_down(monkeypatch, capsys):
    out = menu(monkeypatch, capsys, 60)

    assert ' 1. Pull the latest translations only' in out
    assert '\tP4: Check Out, Crowdin: Download AI and main, UE: Import + Compile' in out
