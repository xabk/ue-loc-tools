"""Syncing one Crowdin project into another.

For a game with a professional project and a community one: source and
translations land in the pro project first and move across on release.
"""

import pytest

from tasks.sync_projects import SyncProjects


@pytest.fixture
def task():
    t = SyncProjects()
    t.token = 'tok'
    t.organization = 'org'
    t.source_project_id = 62
    t.target_project_id = 85
    return t


def test_credentials_fall_back_to_the_shared_pair(task):
    """Both projects are usually on one account, so naming the token twice is
    noise. Either side can still override."""
    task.post_update()

    assert task.source_token == 'tok'
    assert task.target_token == 'tok'
    assert task.source_organization == 'org'
    assert task.target_organization == 'org'


def test_a_per_side_credential_wins(task):
    task.target_token = 'other'
    task.target_organization = 'other-org'

    task.post_update()

    assert task.source_token == 'tok'
    assert task.target_token == 'other'
    assert task.target_organization == 'other-org'


def test_the_run_reports_success(task, monkeypatch):
    """run() used to return None, which the task runner reads as failure -- so
    a clean sync was reported as a failed step."""
    task.post_update()
    monkeypatch.setattr(task, '_clean_temp', lambda: None)
    monkeypatch.setattr(task, '_sync_sources', lambda: 0)
    monkeypatch.setattr(task, '_sync_translations', lambda: 0)

    assert task.run() is True


def test_a_failing_step_fails_the_task(task, monkeypatch):
    task.post_update()
    monkeypatch.setattr(task, '_clean_temp', lambda: None)
    monkeypatch.setattr(task, '_sync_sources', lambda: 1)

    assert task.run() is False


def test_translations_are_not_synced_without_their_sources(task, monkeypatch):
    """With sync_src off the sources are still downloaded, because a
    translation cannot be uploaded without the string it belongs to. If that
    download fails there is nothing to sync against."""
    task.sync_src = False
    task.post_update()
    monkeypatch.setattr(task, '_clean_temp', lambda: None)
    monkeypatch.setattr(task, '_download_sources', lambda: 1)
    monkeypatch.setattr(
        task, '_sync_translations', lambda: pytest.fail('should not be reached')
    )

    assert task.run() is False


def test_sync_src_off_still_downloads_the_sources(task, monkeypatch):
    calls = []
    task.sync_src = False
    task.post_update()
    monkeypatch.setattr(task, '_clean_temp', lambda: None)
    monkeypatch.setattr(task, '_download_sources', lambda: calls.append('dl') or 0)
    monkeypatch.setattr(task, '_sync_translations', lambda: 0)

    assert task.run() is True
    assert calls == ['dl']


def test_the_cli_config_lists_the_configured_targets(task):
    task.sync_src_po_targets = ['InputKeys']
    task.sync_src_csv_targets = ['AllStringTables', 'Narrative']

    task.post_update()

    sources = [f['source'] for f in task._cli_config['files']]
    assert len(sources) == 3
    assert any('InputKeys' in s for s in sources)
    assert any('AllStringTables' in s for s in sources)
    assert any('Narrative' in s for s in sources)
