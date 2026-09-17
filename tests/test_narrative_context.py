"""Narrative context is loaded from an Excel sheet, not from a refs CSV.

load_narrative_context was handing its files to load_string_table_refs_from_file,
which finds nothing in a workbook and returns an empty dict. Nothing warns: the
caller only logs when the result is non-empty, so the task reports success and
every narrative entry silently loses its context.
"""

import pytest

from tasks.test_lang import ProcessTestAndHashLocales

openpyxl = pytest.importorskip('openpyxl')


@pytest.fixture
def sheet(tmp_path):
    """The shape the loader expects: a Message ID column plus message text."""
    path = tmp_path / 'Narrative Implementation Sheet.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Message ID', 'Message Text', 'General Context'])
    ws.append(['MSG_Tier1_Schematic_1-1', 'Welcome to the planet.', 'ADA greeting'])
    ws.append(['MSG_Tier8_Schematic_8-5', 'The elevator is ready.', 'ADA progress'])
    wb.save(path)
    return path


def test_the_workbook_is_read(sheet):
    task = ProcessTestAndHashLocales()

    context = task.load_narrative_context([str(sheet)])

    assert set(context) == {'MSG_Tier1_Schematic_1-1', 'MSG_Tier8_Schematic_8-5'}


def test_the_message_text_comes_through(sheet):
    """Keys alone would not catch it: the refs loader could in principle return
    something keyed by asset too. The message text only the Excel loader
    produces."""
    task = ProcessTestAndHashLocales()

    context = task.load_narrative_context([str(sheet)])

    assert 'Welcome to the planet.' in str(context['MSG_Tier1_Schematic_1-1'])


def test_no_files_means_no_context(tmp_path):
    task = ProcessTestAndHashLocales()

    assert task.load_narrative_context([]) == {}
    assert task.load_narrative_context(None) == {}
