"""Harvested from a project that hit these in production."""

from tasks.update_source_files import CROWDIN_CELL_BYTE_LIMIT, UpdateSourceFile


def test_ascii_within_the_limit():
    task = UpdateSourceFile()
    assert task.within_byte_limit('a' * CROWDIN_CELL_BYTE_LIMIT) is True
    assert task.within_byte_limit('a' * (CROWDIN_CELL_BYTE_LIMIT + 1)) is False


def test_the_limit_is_bytes_not_characters():
    """A CJK character is three UTF-8 bytes, so a string a third of the limit
    in length already exceeds it."""
    task = UpdateSourceFile()
    text = '每' * (CROWDIN_CELL_BYTE_LIMIT // 3 + 1)

    assert len(text) < CROWDIN_CELL_BYTE_LIMIT
    assert task.within_byte_limit(text) is False


def test_empty_and_short_strings_pass():
    task = UpdateSourceFile()
    assert task.within_byte_limit('') is True
    assert task.within_byte_limit('Continue') is True
