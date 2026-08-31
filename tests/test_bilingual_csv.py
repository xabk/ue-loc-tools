"""write_bilingual_csv, including the translated-locale variant used when a
project arrives already localized."""

import csv

import pytest

from libraries import polib
from tasks.update_source_files import CROWDIN_CELL_BYTE_LIMIT, UpdateSourceFile


def make_po(path, entries):
    po = polib.POFile(wrapwidth=0)
    for msgctxt, msgid, msgstr in entries:
        po.append(polib.POEntry(msgctxt=msgctxt, msgid=msgid, msgstr=msgstr))
    po.save(str(path))
    return path


@pytest.fixture
def task():
    task = UpdateSourceFile()
    task.split_csv_rules = None
    return task


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.reader(f))


def test_source_csv_lands_under_the_target(task, tmp_path):
    po = make_po(tmp_path / 'Game.po', [('UI,Continue', 'Continue', '#0001:Continue')])

    task.write_bilingual_csv(str(po), 'Game', dir=tmp_path / 'out')

    rows = read_csv(tmp_path / 'out' / 'Game' / 'Game.csv')
    assert rows[0][:3] == ['Key', 'SourceString', 'TargetString']
    assert rows[1][:3] == ['UI,Continue', 'Continue', '#0001:Continue']


def test_a_locale_adds_a_directory_level(task, tmp_path):
    """Translated CSVs are written per locale, so several can coexist."""
    po = make_po(tmp_path / 'Game.po', [('UI,Continue', 'Continue', 'Fortsetzen')])

    task.write_bilingual_csv(str(po), 'Game', dir=tmp_path / 'out', locale='de')

    rows = read_csv(tmp_path / 'out' / 'Game' / 'de' / 'Game.csv')
    assert rows[1][2] == 'Fortsetzen'


def test_oversized_rows_are_skipped(task, tmp_path):
    po = make_po(
        tmp_path / 'Game.po',
        [
            ('UI,Ok', 'Ok', 'Ok'),
            ('UI,Huge', 'a' * (CROWDIN_CELL_BYTE_LIMIT + 1), ''),
        ],
    )

    task.write_bilingual_csv(str(po), 'Game', dir=tmp_path / 'out')

    keys = [row[0] for row in read_csv(tmp_path / 'out' / 'Game' / 'Game.csv')[1:]]
    assert keys == ['UI,Ok']


def test_split_rules_substitute_the_capture_group(task, tmp_path):
    task.split_csv_rules = [('msgctxt', r'([^,]*),.*', 'Split_$1')]
    po = make_po(
        tmp_path / 'Game.po',
        [('UI,Continue', 'Continue', ''), ('Dialogue,Hi', 'Hi', '')],
    )

    task.write_bilingual_csv(str(po), 'Game', dir=tmp_path / 'out')

    written = sorted(p.name for p in (tmp_path / 'out' / 'Game').glob('*.csv'))
    assert written == ['Split_Dialogue.csv', 'Split_UI.csv']
