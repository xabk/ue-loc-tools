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


def test_each_target_gets_its_own_folder_by_default():
    entry = UpdateSourceFile().cli_files_for_loc_target('Game')

    assert entry['dest'] == 'Game/Game.po'
    assert entry['translation'] == '/Game/%locale%/%original_file_name%'


def test_targets_go_to_the_root_when_subfolders_are_off():
    """A project whose targets are already one file each keeps them at the
    root, which is where its existing Crowdin files live."""
    task = UpdateSourceFile()
    task.subfolder_per_target = False

    entry = task.cli_files_for_loc_target('Game')

    assert entry['dest'] == 'Game.po'


def test_csv_targets_get_their_own_folder_by_default():
    entry = UpdateSourceFile().cli_files_for_csv_loc_target('Tables')

    assert entry['dest'] == 'Tables/%file_name%.csv'
    assert entry['translation'] == '/Tables/%locale%/%original_file_name%'


def test_csv_targets_go_to_the_root_when_subfolders_are_off():
    task = UpdateSourceFile()
    task.subfolder_per_target = False

    entry = task.cli_files_for_csv_loc_target('Tables')

    assert entry['dest'] == '%file_name%.csv'


def test_the_root_layout_leaves_the_source_paths_alone():
    """Only the Crowdin side moves: the files are still read from the same
    place on disk."""
    task = UpdateSourceFile()
    subfoldered = task.cli_files_for_loc_target('Game')['source']
    task.subfolder_per_target = False

    assert task.cli_files_for_loc_target('Game')['source'] == subfoldered


def test_the_root_layout_keeps_the_file_type():
    task = UpdateSourceFile()
    task.subfolder_per_target = False
    task.file_format = 'gettext_unreal'

    entry = task.cli_files_for_loc_target('Game')

    assert entry['type'] == 'gettext_unreal'
    assert entry['dest'] == 'Game.po'


def test_translations_always_export_into_a_folder_per_target():
    """The source layout and the export pattern are separate. Flattening the
    export would break build-and-download, which places translations by
    <Target>/<locale>/<file>."""
    task = UpdateSourceFile()
    expected = '/Game/%locale%/%original_file_name%'

    assert task.cli_files_for_loc_target('Game')['translation'] == expected

    task.subfolder_per_target = False

    assert task.cli_files_for_loc_target('Game')['translation'] == expected


def test_csv_translations_also_keep_the_target_folder():
    task = UpdateSourceFile()
    task.subfolder_per_target = False

    entry = task.cli_files_for_csv_loc_target('Tables')

    assert entry['translation'] == '/Tables/%locale%/%original_file_name%'
