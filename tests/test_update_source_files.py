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


# --------- wiping a staging directory that Perforce has left read-only --------


def test_staging_clears_read_only_files_in_subdirectories(tmp_path):
    """The staging directory is inside the Perforce workspace, so anything not
    checked out is read-only. The wipe cleared the flag on files at the top
    level but called rmtree on subdirectories, which then failed on the CSVs
    inside -- and the CSVs are always in a subdirectory."""
    import shutil
    import stat

    from libraries.utilities import remove_read_only

    nested = tmp_path / 'CSVs' / 'AllStringTables'
    nested.mkdir(parents=True)
    csv = nested / 'Architecture_Data.csv'
    csv.write_text('Key,SourceString\n', encoding='utf-8')
    csv.chmod(stat.S_IREAD)

    shutil.rmtree(tmp_path / 'CSVs', onexc=remove_read_only)

    assert not (tmp_path / 'CSVs').exists()


def test_a_read_only_file_is_still_removed(tmp_path):
    import shutil
    import stat

    from libraries.utilities import remove_read_only

    d = tmp_path / 'dir'
    d.mkdir()
    f = d / 'locked.csv'
    f.write_text('x', encoding='utf-8')
    f.chmod(stat.S_IREAD)

    shutil.rmtree(d, onexc=remove_read_only)

    assert not d.exists()


def test_a_fixed_output_name_needs_no_capture_group(tmp_path):
    """A rule can name its file outright -- ['msgctxt', '^Narrative/MAM,', 'Alien-MAM'].
    The $1 substitution reached for group 1 regardless, so such a rule raised
    IndexError against a pattern that has no group."""
    from libraries import polib
    from tasks.update_source_files import UpdateSourceFile

    po_path = tmp_path / 'Narrative.po'
    po = polib.POFile(wrapwidth=0)
    po.append(polib.POEntry(msgctxt='Narrative/MAM,AlienTech/Foo', msgid='A', msgstr='=1'))
    po.append(polib.POEntry(msgctxt='Narrative/Alien,Bar', msgid='B', msgstr='=2'))
    po.save(str(po_path))

    task = UpdateSourceFile()
    task.csv_dir = ''
    task.split_csv_rules = [
        ['msgctxt', '^Narrative/MAM,AlienTech/', 'Alien-MAM'],
        ['msgctxt', '^[^/,]*/(.*?),.*?$', ''],
    ]

    task.write_bilingual_csv(str(po_path), dir=tmp_path / 'out')

    written = {p.name for p in (tmp_path / 'out').glob('*.csv')}
    assert written == {'Alien-MAM.csv', 'Alien.csv'}


def test_whitespace_is_stripped_in_both_branches(tmp_path):
    """Stripping was honoured only for entries that matched a
    split rule; the ones that fell through to {target}.csv kept their leading
    space, so the same setting gave two different answers in one file."""
    from libraries import polib
    from tasks.update_source_files import UpdateSourceFile

    po_path = tmp_path / 'Narrative.po'
    po = polib.POFile(wrapwidth=0)
    po.append(polib.POEntry(msgctxt='Narrative/Alien,Bar', msgid=' matched ', msgstr='=1'))
    po.append(polib.POEntry(msgctxt=',NoNamespace', msgid=' fell through ', msgstr='=2'))
    po.save(str(po_path))

    task = UpdateSourceFile()
    task.csv_dir = ''
    task.delete_whitespace_targets = ['Narrative']
    task.split_csv_rules = [['msgctxt', '^[^/,]*/(.*?),.*?$', '']]

    task.write_bilingual_csv(str(po_path), 'Narrative', dir=tmp_path / 'out')

    import csv as _csv
    import io as _io

    rows = {}
    for p in (tmp_path / 'out').rglob('*.csv'):
        for r in _csv.DictReader(_io.open(p, encoding='utf-8-sig', newline='')):
            rows[r['Key']] = r['SourceString']

    assert rows['Narrative/Alien,Bar'] == 'matched'
    assert rows[',NoNamespace'] == 'fell through'


def test_a_long_text_is_cut_for_the_log_and_says_how_long_it_was():
    task = UpdateSourceFile()
    task.log_text_limit = 10

    assert task.clip_for_log('a' * 25) == 'aaaaaaaaaa… (25 chars)'


def test_a_text_within_the_log_limit_is_logged_whole():
    task = UpdateSourceFile()
    task.log_text_limit = 10

    assert task.clip_for_log('a' * 10) == 'a' * 10


def test_a_log_limit_of_zero_logs_everything():
    task = UpdateSourceFile()
    task.log_text_limit = 0

    assert task.clip_for_log('a' * 70000) == 'a' * 70000
