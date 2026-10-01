"""Every `SourceLocation:` comment becomes `Loc:`, prefix or not."""

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
    t.remove_source_loc_prefixes = ['/Game', 'Source']
    # post_update builds this, and it is not run here: the rest of post_update
    # resolves project paths that a unit test has no business needing.
    t._id_regex = t.id_regex_pattern.format(
        prefix=re.escape(t.debug_prefix), id_length=t.id_length
    )
    t._string_table_refs = {}
    t._narrative_context = {}
    t._external_context = {}
    return t


def locations_after_pass(task, tmp_path, source_location):
    """Run one pass over an entry with this SourceLocation comment and return
    its location lines."""
    path = tmp_path / 'Game.po'
    po = polib.POFile(wrapwidth=0)
    po.append(
        polib.POEntry(
            msgctxt=',KEY1',
            msgid='Source',
            msgstr='?00001',
            comment=f'SourceLocation:\t{source_location}',
        )
    )
    po.save(str(path))

    task.process_debug_ID_locale(str(path), 1)

    entry = polib.pofile(str(path), wrapwidth=0, encoding='utf-8-sig')[0]
    return [
        line
        for line in entry.comment.splitlines()
        if line.startswith(('Loc:', 'SourceLocation:'))
    ]


@pytest.mark.parametrize(
    'source_location, expected',
    [
        ('/Game/ui/HUD/UW_HUD.UW_HUD_C:Text', 'Loc:\t/ui/HUD/UW_HUD.UW_HUD_C:Text'),
        ('Source/fellowship/UI/Widget.cpp(51)', 'Loc:\t/fellowship/UI/Widget.cpp(51)'),
    ],
)
def test_a_listed_prefix_is_stripped(task, tmp_path, source_location, expected):
    assert locations_after_pass(task, tmp_path, source_location) == [expected]


@pytest.mark.parametrize(
    'source_location',
    [
        # Plugin content: the plugin's mount point, not /Game
        '/CRMTXStore/DT_MTXCategories.DT_MTXCategories.bundle.DisplayName',
        # Plugin source: a project-relative path, not Source/
        'Plugins/GameFeatures/CRMTXStore/Source/Runtime/Private/Store.cpp(98)',
        # Plugin string table
        '../Plugins/GameFeatures/CRMTXStore/Content/Localization/ST_Store.csv',
    ],
)
def test_a_path_without_a_listed_prefix_is_still_renamed(
    task, tmp_path, source_location
):
    """The bug: these kept `SourceLocation:`, so rules written for `Loc:`
    never saw them."""
    assert locations_after_pass(task, tmp_path, source_location) == [
        f'Loc:\t{source_location}'
    ]


def test_without_prefixes_every_line_is_renamed_as_is(task, tmp_path):
    task.remove_source_loc_prefixes = None
    assert locations_after_pass(task, tmp_path, '/Game/ui/X.X') == ['Loc:\t/Game/ui/X.X']
