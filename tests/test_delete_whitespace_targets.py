"""Edge whitespace is a per-target convention: one target's subtitles carry a
leading space its sources are expected to drop, another renders ' / {time}'
with it. delete_whitespace_targets names the ones to strip."""

import csv
import io

import pytest

from tasks.update_source_files import UpdateSourceFile

PO = '''msgid ""
msgstr ""

msgctxt "NS,Keep/Trailing"
msgid "Average "
msgstr ""

msgctxt "NS,Keep/Leading"
msgid " RESEARCHED"
msgstr ""
'''


@pytest.fixture
def po_file(tmp_path):
    p = tmp_path / 'AllStringTables.po'
    io.open(p, 'w', encoding='utf-8-sig', newline='').write(PO)
    return p


def make_task(**kwargs):
    task = UpdateSourceFile.__new__(UpdateSourceFile)
    task.split_csv_rules = None
    task.csv_dir = ''
    task.encoding = 'utf-8-sig'
    task.delete_whitespace_targets = []
    task.csv_fields = ['Key', 'SourceString', 'TargetString', 'MaxLength',
                       'Labels', 'CrowdinContext']
    for k, v in kwargs.items():
        setattr(task, k, v)
    return task


def sources_written(task, po_file, target, out):
    task.write_bilingual_csv(str(po_file), target, dir=out)
    rows = {}
    for f in out.rglob('*.csv'):
        with io.open(f, encoding='utf-8-sig', newline='') as fh:
            for row in csv.reader(fh):
                if row and row[0] != 'Key':
                    rows[row[0]] = row[1]
    return rows


def test_an_unlisted_target_is_uploaded_as_gathered(po_file, tmp_path):
    out = tmp_path / 'a'
    out.mkdir()
    rows = sources_written(make_task(), po_file, 'AllStringTables', out)
    assert rows['NS,Keep/Trailing'] == 'Average '
    assert rows['NS,Keep/Leading'] == ' RESEARCHED'


def test_a_listed_target_is_stripped(po_file, tmp_path):
    out = tmp_path / 'b'
    out.mkdir()
    task = make_task(delete_whitespace_targets=['Narrative'])
    rows = sources_written(task, po_file, 'Narrative', out)
    assert rows['NS,Keep/Trailing'] == 'Average'
    assert rows['NS,Keep/Leading'] == 'RESEARCHED'


def test_the_decision_is_per_target(po_file, tmp_path):
    """One run uploads several targets, so this cannot be a single switch."""
    task = make_task(delete_whitespace_targets=['Narrative'])
    kept = tmp_path / 'k'; kept.mkdir()
    stripped = tmp_path / 's'; stripped.mkdir()
    assert sources_written(task, po_file, 'AllStringTables', kept)['NS,Keep/Leading'] == ' RESEARCHED'
    assert sources_written(task, po_file, 'Narrative', stripped)['NS,Keep/Leading'] == 'RESEARCHED'


def test_the_default_strips_nothing(po_file, tmp_path):
    out = tmp_path / 'c'
    out.mkdir()
    rows = sources_written(make_task(), po_file, 'Narrative', out)
    assert rows['NS,Keep/Leading'] == ' RESEARCHED'
