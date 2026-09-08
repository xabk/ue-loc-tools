"""An empty target list is only wrong when both lists are empty.

Goat 1 has no CSV targets, and every successful sync logged
'No CSV loc targets to modify specified.' at error level, which reads like a
failure in a producer's log.

loguru does not route through stdlib logging, so caplog stays empty here: these
tests capture with a loguru sink instead. Each one also asserts the message it
expects, so a broken sink fails the test rather than passing it vacuously.
"""

import pytest
from loguru import logger

from tasks.build_and_download import BuildAndDownloadTranslations


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


@pytest.fixture
def task():
    t = BuildAndDownloadTranslations()
    t.loc_targets = []
    t.csv_loc_targets = []
    return t


def no_side_effects(task, monkeypatch, reached):
    """Stub everything run() touches after the guard."""
    monkeypatch.setattr(task, 'build_and_download', lambda: reached.append('built'))
    monkeypatch.setattr(task, 'unzip_file', lambda: reached.append('unzipped'))
    monkeypatch.setattr(task, 'process_loc_targets', lambda: True)
    monkeypatch.setattr(task, 'process_csv_loc_targets', lambda: True)
    monkeypatch.setattr('shutil.rmtree', lambda _p: None)
    monkeypatch.setattr(
        task, '_zip_path', type('P', (), {'unlink': lambda self: None})()
    )


def test_no_po_targets_is_only_information(task, logged):
    assert task.process_loc_targets() is True

    assert 'No loc targets specified' in messages(logged)
    assert 'ERROR' not in levels(logged)
    assert 'WARNING' not in levels(logged)


def test_no_csv_targets_is_only_information(task, logged):
    """Goat 1's everyday case: PO targets, no CSV targets."""
    task.loc_targets = ['Game']

    assert task.process_csv_loc_targets() is True

    assert 'No CSV loc targets specified' in messages(logged)
    assert 'ERROR' not in levels(logged)
    assert 'WARNING' not in levels(logged)


def test_both_lists_empty_is_an_error(task, monkeypatch, logged):
    no_side_effects(task, monkeypatch, [])

    assert task.run() is False

    assert 'Nothing to download' in messages(logged)
    assert 'ERROR' in levels(logged)


def test_both_lists_empty_does_not_build_on_crowdin(task, monkeypatch):
    """Fail before spending a minute and a half building a project we have
    nothing to do with."""
    reached = []
    no_side_effects(task, monkeypatch, reached)

    task.run()

    assert reached == []


def test_csv_targets_alone_are_enough_to_proceed(task, monkeypatch):
    task.csv_loc_targets = ['Tables']
    reached = []
    no_side_effects(task, monkeypatch, reached)

    assert task.run() is True
    assert 'built' in reached


def test_po_targets_alone_are_enough_to_proceed(task, monkeypatch):
    task.loc_targets = ['Game']
    reached = []
    no_side_effects(task, monkeypatch, reached)

    assert task.run() is True
    assert 'built' in reached
