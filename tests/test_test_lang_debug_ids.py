"""The `Debug ID:` comment has to name the entry's own ID."""

import re

import pytest

from libraries import polib
from tasks.test_lang import ProcessTestAndHashLocales


@pytest.fixture
def task():
    t = ProcessTestAndHashLocales()
    t.debug_prefix = '?'
    t.id_length = 5
    t.clear_translations = False
    t.sort_po = False
    t.comments_criteria = []
    t.delete_comments_criteria = []
    t.additional_context = {}
    t.add_context_fields = []
    # post_update builds this, and it is not run here: the rest of post_update
    # resolves project paths that a unit test has no business needing.
    t._id_regex = t.id_regex_pattern.format(
        prefix=re.escape(t.debug_prefix), id_length=t.id_length
    )
    # Normally filled by load_external_data from the refs CSV and the context
    # workbook. Empty here: this is about IDs, not about context.
    t._string_table_refs = {}
    t._narrative_context = {}
    t._external_context = {}
    return t


def write_po(path, entries):
    """entries: (msgctxt, msgid, msgstr) triples."""
    po = polib.POFile(wrapwidth=0)
    for msgctxt, msgid, msgstr in entries:
        po.append(polib.POEntry(msgctxt=msgctxt, msgid=msgid, msgstr=msgstr))
    po.save(str(path))
    return str(path)


def debug_ids_in(path, encoding='utf-8-sig'):
    """The `Debug ID:` value of every entry, in file order."""
    po = polib.pofile(path, wrapwidth=0, encoding=encoding)
    out = []
    for entry in po:
        for line in entry.comment.splitlines():
            if line.startswith('Debug ID:'):
                out.append(line.partition('Debug ID:\t')[2].split('\t')[0].strip())
    return out


def test_every_entry_keeps_its_own_id(task, tmp_path):
    """The bug: all three came back labelled with the same ID."""
    po_file = write_po(
        tmp_path / 'Game.po',
        [
            (',KEY1', 'Source one', '?01693'),
            (',KEY2', 'Source two', '?01621'),
            (',KEY3', 'Source three', '?00918'),
        ],
    )

    task.process_debug_ID_locale(po_file, 1)

    assert debug_ids_in(po_file) == ['?01693', '?01621', '?00918']


def test_a_whole_target_does_not_collapse_onto_one_id(task, tmp_path):
    """The shape of the regression, stated directly."""
    po_file = write_po(
        tmp_path / 'Game.po',
        [(f',KEY{i}', f'Source {i}', f'?{i:05d}') for i in range(1, 51)],
    )

    task.process_debug_ID_locale(po_file, 1)

    assert len(set(debug_ids_in(po_file))) == 50


def test_the_comment_never_disagrees_with_the_translation(task, tmp_path):
    """Whatever the ID is, the label and the value cannot contradict."""
    po_file = write_po(
        tmp_path / 'Game.po',
        [(',KEY1', 'One', '?00007'), (',KEY2', 'Two', '?00008')],
    )

    task.process_debug_ID_locale(po_file, 1)

    po = polib.pofile(po_file, wrapwidth=0, encoding='utf-8-sig')
    for entry, comment in zip(po, debug_ids_in(po_file)):
        assert entry.msgstr.startswith(comment)


def test_an_untranslated_entry_still_gets_a_minted_id(task, tmp_path):
    """The other half: a new string gets an ID from the counter, and the
    comment names that one rather than the one after it."""
    po_file = write_po(
        tmp_path / 'Game.po',
        [(',KEY1', 'Already done', '?00042'), (',KEY2', 'Brand new', '')],
    )

    task.process_debug_ID_locale(po_file, 7)

    po = polib.pofile(po_file, wrapwidth=0, encoding='utf-8-sig')
    comments = debug_ids_in(po_file)

    assert comments[0] == '?00042'
    assert po[1].msgstr.startswith('?00007')
    assert comments[1] == '?00007'
