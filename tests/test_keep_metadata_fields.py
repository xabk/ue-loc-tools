"""Which gathered metadata fields reach the translator.

Two things were wrong: delete_comments_criteria was tested against the raw
line, so a rule naming a field ('^Type:') could never match the still-wrapped
'InfoMetaData:\t"Type" : "Game"'; and there was no way to say which fields to
keep without writing a regex per field.
"""

import pytest

from tasks.test_lang import ProcessTestAndHashLocales as Task

RAW = [
    'Key:\tArchitecture/BarrierLow',
    'SourceLocation:\tLocalization/StringTables/Architecture_Data.csv',
    'InfoMetaData:\t"Tag" : "#buildable\\r\\n#item"',
    'InfoMetaData:\t"Type" : "Game"',
]


def task(**kwargs):
    t = Task.__new__(Task)
    t.delete_comments_criteria = []
    t.keep_metadata_fields = None
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


def unwrapped(line):
    """What the loop holds once InfoMetaData has been unwrapped."""
    import re
    if line.startswith('InfoMetaData:\t'):
        line = line.partition('InfoMetaData:\t')[2]
        line = re.sub(r'^"(.*?)" : "(.*?)"$', r'\1: \2', line)
    return line


@pytest.mark.parametrize('raw,name', [
    ('Key:\tArchitecture/BarrierLow', 'Key'),
    ('Loc:\tLocalization/StringTables/Architecture_Data.csv', 'Loc'),
    ('Type: Game', 'Type'),
    ('Tag: #buildable\\r\\n#item', 'Tag'),
    ('Refs: /Game/FactoryGame/Thing.Default__Thing_C.mDisplayName', 'Refs'),
])
def test_field_name_is_read_from_the_line(raw, name):
    assert Task.metadata_field_name(raw) == name


def test_a_continuation_line_is_not_a_field():
    assert Task.metadata_field_name('#item') is None


def test_an_empty_column_is_dropped_without_a_regex():
    """Every project carried the same raw-form regex for these."""
    assert Task.metadata_field_value('Description: ') == ''
    assert Task.metadata_field_value('Mood: Agitated') == 'Agitated'


def test_a_rule_naming_a_field_now_matches_once_unwrapped():
    """This is the bug: the rule was always written for the unwrapped form."""
    t = task(delete_comments_criteria=['^Type:.*$'])
    assert t.should_delete_comment('InfoMetaData:\t"Type" : "Game"') is False
    assert t.should_delete_comment(unwrapped('InfoMetaData:\t"Type" : "Game"')) is True


def test_no_keep_list_keeps_everything():
    t = task()
    assert all(t.should_keep_metadata_field(unwrapped(l)) for l in RAW)


def test_an_empty_keep_list_keeps_none_of_them():
    t = task(keep_metadata_fields=[])
    assert not any(t.should_keep_metadata_field(unwrapped(l)) for l in RAW)


def test_a_keep_list_keeps_what_it_names():
    t = task(keep_metadata_fields=['Refs'])
    kept = [unwrapped(l) for l in RAW if t.should_keep_metadata_field(unwrapped(l))]
    assert kept == []
    assert t.should_keep_metadata_field('Refs: /Game/Thing.mDisplayName') is True


def test_a_continuation_line_survives_the_keep_list():
    """It is not a field, so it is not judged as one. It only reaches the
    output if its field did -- Tag's value is one string until the very end."""
    t = task(keep_metadata_fields=[])
    assert t.should_keep_metadata_field('#item') is True


def test_tag_and_its_value_are_one_line_at_this_point():
    """Which is why dropping the field takes the '#item' with it."""
    assert unwrapped(RAW[2]) == 'Tag: #buildable\\r\\n#item'
    assert task(keep_metadata_fields=[]).should_keep_metadata_field(unwrapped(RAW[2])) is False
