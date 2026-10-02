"""Edge whitespace is a per-target convention: Narrative's sources are expected
to drop a leading space, AllStringTables renders it. One flag cannot serve
both, so keep_whitespace_targets exempts the targets that need it."""

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


def sources_written(task, po_file, target, out):
    task.write_bilingual_csv(str(po_file), target, dir=out)
    import csv
    rows = {}
    for f in out.rglob("*.csv"):
        with io.open(f, encoding='utf-8-sig', newline='') as fh:
            for row in csv.reader(fh):
                if row and row[0] not in ('Key', 'identifier'):
                    rows[row[0]] = row[1]
    return rows


def make_task(**kwargs):
    task = UpdateSourceFile.__new__(UpdateSourceFile)
    task.split_csv_rules = None
    task.csv_dir = ''
    task.encoding = 'utf-8-sig'
    task.delete_unsafe_whitespace = True
    task.keep_whitespace_targets = []
    task.csv_fields = ['Key', 'SourceString', 'TargetString', 'MaxLength',
                       'Labels', 'CrowdinContext']
    for k, v in kwargs.items():
        setattr(task, k, v)
    return task


def test_whitespace_is_stripped_by_default(po_file, tmp_path):
    out = tmp_path / 'a'
    out.mkdir()
    rows = sources_written(make_task(), po_file, 'Narrative', out)
    assert rows['NS,Keep/Trailing'] == 'Average'
    assert rows['NS,Keep/Leading'] == 'RESEARCHED'


def test_an_exempt_target_keeps_its_whitespace(po_file, tmp_path):
    out = tmp_path / 'b'
    out.mkdir()
    task = make_task(keep_whitespace_targets=['AllStringTables'])
    rows = sources_written(task, po_file, 'AllStringTables', out)
    assert rows['NS,Keep/Trailing'] == 'Average '
    assert rows['NS,Keep/Leading'] == ' RESEARCHED'


def test_the_exemption_is_per_target(po_file, tmp_path):
    """The same task uploads both in one run, so the flag cannot be global."""
    task = make_task(keep_whitespace_targets=['AllStringTables'])
    kept = tmp_path / 'k'; kept.mkdir()
    stripped = tmp_path / 's'; stripped.mkdir()
    assert sources_written(task, po_file, 'AllStringTables', kept)['NS,Keep/Leading'] == ' RESEARCHED'
    assert sources_written(task, po_file, 'Narrative', stripped)['NS,Keep/Leading'] == 'RESEARCHED'


def test_exemption_does_nothing_when_stripping_is_off(po_file, tmp_path):
    out = tmp_path / 'c'
    out.mkdir()
    task = make_task(delete_unsafe_whitespace=False, keep_whitespace_targets=['Other'])
    rows = sources_written(task, po_file, 'Narrative', out)
    assert rows['NS,Keep/Leading'] == ' RESEARCHED'
