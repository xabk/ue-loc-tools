"""Read-only checks against the live Crowdin test project.

libraries/crowdin.py has no coverage at all and is the layer where a mistake
writes to a real translation project, so these pin what it does today before
anything there is refactored.

Run with:  uv run --extra test python -m pytest -m crowdin
"""

import pytest

from conftest import TEST_PROJECT_ID

pytestmark = pytest.mark.crowdin


def test_the_token_reaches_the_right_project(crowdin):
    project = crowdin.projects.get_project(projectId=TEST_PROJECT_ID)['data']

    assert project['id'] == TEST_PROJECT_ID
    assert project['name']


def test_the_project_has_target_languages(crowdin):
    project = crowdin.projects.get_project(projectId=TEST_PROJECT_ID)['data']

    assert project['targetLanguageIds'], 'test project has no target languages'
    assert project['sourceLanguageId']


def test_listing_source_files_returns_a_data_list(crowdin):
    response = crowdin.source_files.list_files(projectId=TEST_PROJECT_ID)

    assert isinstance(response.get('data'), list)


def test_supported_languages_are_paginated_to_500(crowdin):
    """update_file_list_and_project_data asks for 500 in one call, so this
    breaks the day Crowdin supports more than that."""
    languages = crowdin.languages.list_supported_languages(limit=500)['data']

    assert len(languages) < 500, 'the 500 limit is now a truncation, not a ceiling'


def test_update_file_list_and_project_data_populates_the_client(crowdin):
    crowdin.file_list = None
    crowdin.data = {}

    crowdin.update_file_list_and_project_data()

    assert isinstance(crowdin.file_list, list)
    assert crowdin.data['project_data']['id'] == TEST_PROJECT_ID
    assert crowdin.data['supported_languages']


def test_the_wrapper_defaults_to_the_configured_project(crowdin):
    """Methods rely on self.project_id rather than being passed one."""
    assert crowdin.project_id == TEST_PROJECT_ID
