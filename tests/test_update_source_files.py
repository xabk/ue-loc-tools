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


def test_no_file_type_is_sent_unless_configured():
    """Crowdin decides for itself when type is absent, which is what every
    project relying on autodetect already gets."""
    task = UpdateSourceFile()

    assert 'type' not in task.cli_files_for_loc_target('Game')


def test_the_configured_file_type_reaches_the_cli_config():
    """Without this, a PO file created by the CLI lands as plain gettext and
    loses the Unreal parser."""
    task = UpdateSourceFile()
    task.file_format = 'gettext_unreal'

    assert task.cli_files_for_loc_target('Game')['type'] == 'gettext_unreal'


def test_the_file_type_does_not_disturb_the_other_keys():
    task = UpdateSourceFile()
    task.file_format = 'gettext_unreal'
    entry = task.cli_files_for_loc_target('Game')

    assert entry['dest'] == 'Game/Game.po'
    assert entry['translation'] == '/Game/%locale%/%original_file_name%'
    assert entry['source'].endswith('Game.po')
