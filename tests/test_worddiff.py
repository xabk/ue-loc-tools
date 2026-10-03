"""Word-level diff of two versions of one string.

The log file gets git's markers and the terminal gets colour, from the same
comparison. Whitespace is the point as much as the words: a lost trailing
space is a real localization bug and invisible in plain text.
"""

import re

import pytest

from libraries.worddiff import ADDED_BG, BG_OFF, REMOVED_BG, word_diff


def plain(old, new):
    return word_diff(old, new)[0]


def colour(old, new):
    return word_diff(old, new)[1]


def test_an_inserted_word_is_marked_on_the_new_side_only():
    old_s, new_s = plain('write file to disk', 'write file {0} to disk')
    assert old_s == 'write file to disk'
    assert new_s == 'write file {+{0} +}to disk'


def test_a_rewritten_phrase_is_one_marker_not_one_per_word():
    old_s, new_s = plain('from dedicated server', 'from Dedicated Server')
    assert old_s == 'from [-dedicated server-]'
    assert new_s == 'from {+Dedicated Server+}'


@pytest.mark.parametrize(
    'old,new,expected_new',
    [
        ('Vulkan', 'Vulkan ', 'Vulkan{+ +}'),
        ('RESEARCHED', ' RESEARCHED', '{+ +}RESEARCHED'),
    ],
)
def test_whitespace_only_changes_are_visible(old, new, expected_new):
    """The reason this exists: these are invisible in an unmarked log."""
    assert plain(old, new)[1] == expected_new


@pytest.mark.parametrize(
    'old,new',
    [
        ('a b c', 'a x c'),
        ('Vulkan', 'Vulkan '),
        ('x', '  x  '),
        ('one two three four', 'one four'),
        ('', 'something'),
        ('something', ''),
        ('same', 'same'),
    ],
)
def test_markers_round_trip_exactly(old, new):
    """Strip the markers and both sides must be byte-identical to the input,
    or the log is showing something the tool did not see."""
    old_s, new_s = plain(old, new)
    assert re.sub(r'\[-(.*?)-\]', r'\1', old_s, flags=re.S) == old
    assert re.sub(r'\{\+(.*?)\+\}', r'\1', new_s, flags=re.S) == new


def test_identical_strings_are_not_marked_at_all():
    assert plain('same text', 'same text') == ('same text', 'same text')
    assert colour('same text', 'same text') == ('same text', 'same text')


def test_colour_wraps_the_same_spans_as_the_markers():
    old_s, new_s = colour('write file to disk', 'write file {0} to disk')
    assert old_s == 'write file to disk'
    assert new_s == f'write file {ADDED_BG}{{0}} {BG_OFF}to disk'
    assert REMOVED_BG in colour('a b', 'a')[0]


def test_game_markup_passes_through_untouched():
    """No markup parser is involved, so angle and square brackets survive --
    loguru would raise on <Bold> and Rich would silently eat [Experimental]."""
    for text in ('<Bold>Auto-Pickup</>', '[Experimental] Vulkan', '{Cost} coupons'):
        assert plain(text, text) == (text, text)
