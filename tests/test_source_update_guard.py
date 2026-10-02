"""The source-update guard: only named branches may push source to a CAT tool.

Branch identity comes from Engine/Build/Build.version, which is the one place
that knows it without a Perforce connection, editor settings or a network.
"""

import json

import pytest

from libraries.task_runner import TaskRunner
from libraries.uetools import branch_name_from_build_version

UPLOAD = {'description': 'upload', 'script': 'update-source-files', 'updates-source': True}
DOWNLOAD = {'description': 'download', 'script': 'build-and-download'}


def write_build_version(root, branch):
    path = root / 'Engine' / 'Build'
    path.mkdir(parents=True)
    (path / 'Build.version').write_text(
        json.dumps({'MajorVersion': 5, 'BranchName': branch}), encoding='utf-8'
    )
    return root


def runner(engine_dir, allowed=None):
    params = {'engine_dir': str(engine_dir)}
    if allowed is not None:
        params['source-update-branches'] = allowed
    r = TaskRunner.__new__(TaskRunner)
    r.config = {'parameters': params}
    return r


def test_reads_the_branch_name(tmp_path):
    write_build_version(tmp_path, '++FactoryGame+rel-main-ficsmas-2026')
    assert branch_name_from_build_version(tmp_path) == '++FactoryGame+rel-main-ficsmas-2026'


@pytest.mark.parametrize(
    'missing', ['no-engine-dir', 'no-file', 'not-json', 'no-branch-name']
)
def test_unreadable_branch_is_none(tmp_path, missing):
    if missing == 'no-file':
        (tmp_path / 'Engine' / 'Build').mkdir(parents=True)
    elif missing == 'not-json':
        (tmp_path / 'Engine' / 'Build').mkdir(parents=True)
        (tmp_path / 'Engine' / 'Build' / 'Build.version').write_text('{oops')
    elif missing == 'no-branch-name':
        (tmp_path / 'Engine' / 'Build').mkdir(parents=True)
        (tmp_path / 'Engine' / 'Build' / 'Build.version').write_text('{"MajorVersion": 5}')
    assert branch_name_from_build_version(tmp_path) is None


def test_a_task_that_does_not_update_source_is_never_blocked(tmp_path):
    write_build_version(tmp_path, '++FactoryGame+dev')
    r = runner(tmp_path, ['++FactoryGame+rel-main-*'])
    assert r.source_update_blocked(DOWNLOAD) is None


def test_no_allow_list_means_no_policy(tmp_path):
    write_build_version(tmp_path, '++FactoryGame+dev')
    assert runner(tmp_path).source_update_blocked(UPLOAD) is None
    assert runner(tmp_path, []).source_update_blocked(UPLOAD) is None


def test_allowed_branch_passes(tmp_path):
    write_build_version(tmp_path, '++FactoryGame+rel-main-ficsmas-2026')
    r = runner(tmp_path, ['++FactoryGame+rel-main-ficsmas-2026'])
    assert r.source_update_blocked(UPLOAD) is None


def test_glob_covers_the_release_branches(tmp_path):
    write_build_version(tmp_path, '++FactoryGame+rel-main-anniversary-2026')
    r = runner(tmp_path, ['++FactoryGame+rel-main-*'])
    assert r.source_update_blocked(UPLOAD) is None


def test_dev_is_blocked_and_says_which_branch(tmp_path):
    write_build_version(tmp_path, '++FactoryGame+dev')
    reason = runner(tmp_path, ['++FactoryGame+rel-main-*']).source_update_blocked(UPLOAD)
    assert reason is not None
    assert '++FactoryGame+dev' in reason
    assert '++FactoryGame+rel-main-*' in reason


def test_unreadable_branch_blocks_when_a_list_is_set(tmp_path):
    """A guard that gives up when it cannot see is no guard."""
    reason = runner(tmp_path, ['++FactoryGame+rel-main-*']).source_update_blocked(UPLOAD)
    assert reason is not None
    assert 'Build.version' in reason
