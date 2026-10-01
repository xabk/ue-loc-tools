"""Stale files: only the target folders we upload into are ever touched."""

from pathlib import Path

import pytest

from tasks import update_source_files as usf
from tasks.update_source_files import UpdateSourceFile


def rows(items):
    return {'data': [{'data': i} for i in items]}


class FakeSourceFiles:
    def __init__(self, directories, files):
        self.directories = directories
        self.files = files
        self.deleted = []

        self.fetch_all = False

    def with_fetch_all(self):
        self.fetch_all = True
        return self

    def _all(self, items):
        """Without with_fetch_all, a listing stops at the first page."""
        fetch_all, self.fetch_all = self.fetch_all, False
        return rows(items if fetch_all else items[:1])

    def list_directories(self, projectId):
        return self._all(self.directories)

    def list_files(self, projectId, directoryId):
        return self._all([f for f in self.files if f['directoryId'] == directoryId])

    def delete_file(self, projectId, fileId):
        self.deleted.append(fileId)


class FakeCrowdin:
    def __init__(self, directories, files):
        self.source_files = FakeSourceFiles(directories, files)


def directory(id, name, parent=None, branch=None):
    return {'id': id, 'name': name, 'directoryId': parent, 'branchId': branch}


def file(id, name, directory_id, path):
    return {
        'id': id,
        'name': name,
        'directoryId': directory_id,
        'path': path,
        'updatedAt': '2026-07-06T13:42:00+00:00',
    }


@pytest.fixture
def task(tmp_path):
    t = UpdateSourceFile()
    t.loc_targets = []
    t.csv_loc_targets = ['Game']
    t._temp_path = tmp_path
    csv_dir = tmp_path / t.cli_source_dir / t.csv_dir / 'Game'
    csv_dir.mkdir(parents=True)
    for name in ['C_ui.csv', 'S_UI.csv']:
        (csv_dir / name).write_text('Key\n', encoding='utf-8')
    return t


@pytest.fixture
def crowdin():
    return FakeCrowdin(
        directories=[
            directory(1, 'Game'),
            directory(2, 'Glossaries translate app'),
            directory(3, 'Old', parent=1),
            directory(4, 'Game', branch=9),  # same name, inside a branch
        ],
        files=[
            file(10, 'C_ui.csv', 1, '/Game/C_ui.csv'),
            file(11, 'S_Vendor.csv', 1, '/Game/S_Vendor.csv'),
            file(12, 'Glossary.tbx', 2, '/Glossaries translate app/Glossary.tbx'),
            file(13, 'Leftover.csv', 3, '/Game/Old/Leftover.csv'),
            file(14, 'Branch.csv', 4, '/WordCount/Game/Branch.csv'),
            file(15, 'Root.csv', None, '/Root.csv'),
        ],
    )


def stale_paths(task, crowdin):
    return [f['path'] for files in task.stale_files(crowdin).values() for f in files]


def test_a_file_we_no_longer_upload_is_stale(task, crowdin):
    assert stale_paths(task, crowdin) == ['/Game/S_Vendor.csv']


def test_nothing_outside_the_target_folder_is_considered(task, crowdin):
    """Not the root, not another folder, not a subfolder, not a branch."""
    paths = stale_paths(task, crowdin)

    assert '/Root.csv' not in paths
    assert '/Glossaries translate app/Glossary.tbx' not in paths
    assert '/Game/Old/Leftover.csv' not in paths
    assert '/WordCount/Game/Branch.csv' not in paths


def test_a_target_with_no_local_files_is_not_checked(task, crowdin, tmp_path):
    """A failed prep must not make the whole folder look stale."""
    for p in (tmp_path / task.cli_source_dir / task.csv_dir / 'Game').glob('*'):
        p.unlink()

    assert task.stale_files(crowdin) == {}


def test_a_po_target_expects_its_own_po_file(task):
    task.loc_targets = ['InputKeys']

    assert task.uploaded_file_names('InputKeys') == {'InputKeys.po'}


@pytest.fixture
def patched(task, crowdin, monkeypatch):
    monkeypatch.setattr(usf, 'UECrowdinClient', lambda *a, **k: crowdin)
    return task, crowdin


def test_reporting_deletes_nothing(patched):
    task, crowdin = patched

    assert task.report_stale_files_on_crowdin() is True
    assert crowdin.source_files.deleted == []


def test_deleting_removes_only_the_stale_file(patched):
    task, crowdin = patched
    task.delete_stale_files = True

    assert task.report_stale_files_on_crowdin() is True
    assert crowdin.source_files.deleted == [11]


@pytest.mark.parametrize(
    'setting', [{'branch': 'WordCount'}, {'subfolder_per_target': False}]
)
def test_not_checked_where_the_folder_is_not_ours_alone(patched, setting):
    task, crowdin = patched
    task.delete_stale_files = True
    for key, value in setting.items():
        setattr(task, key, value)

    assert task.report_stale_files_on_crowdin() is True
    assert crowdin.source_files.deleted == []
