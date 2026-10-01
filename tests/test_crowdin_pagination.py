"""Listings have to ask the client for every page.

Without with_fetch_all the client resolves `limit = limit or self.page_size`
and its page_size is 25, so a listing comes back with its first 25 rows and
nothing says the rest exist. The projects here hold 6 to 80 files: get_file_ID
could not find a file past the 25th, and get_or_create_directory stopped
finding directories past the 25th and created them a second time.
"""

import pytest

from libraries.crowdin import UECrowdinClient


class FakeResource:
    """Stands in for a client resource, and only answers in full when asked.

    with_fetch_all is a flag the client sets and clears per call, so a listing
    that forgets it gets the first page -- which is what this is here to catch.
    """

    def __init__(self, rows):
        self.rows = rows
        self.page_size = 25
        self._fetch_all = False
        self.calls = []

    def with_fetch_all(self, max_limit=None):
        self._fetch_all = True
        return self

    def _answer(self, name):
        asked_for_all = self._fetch_all
        self._fetch_all = False  # one-shot, as the real client does
        self.calls.append((name, asked_for_all))
        rows = self.rows if asked_for_all else self.rows[: self.page_size]
        return {'data': rows}

    def list_files(self, **kwargs):
        return self._answer('list_files')

    def list_directories(self, **kwargs):
        return self._answer('list_directories')

    def list_supported_languages(self, **kwargs):
        return self._answer('list_supported_languages')


class FakeProjects:
    def get_project(self, **kwargs):
        return {'data': {}}


def entries(count, prefix='file'):
    return [
        {'data': {'id': i, 'name': f'{prefix}{i}.po', 'directoryId': None}}
        for i in range(count)
    ]


@pytest.fixture
def client():
    return UECrowdinClient('token', None, 'org', 1, silent=True)


def attach(monkeypatch, client, rows=0, languages=0):
    """The resources are read-only properties on the client, so they are
    replaced on the class for the duration of the test."""
    source_files = FakeResource(entries(rows))
    language_list = FakeResource(entries(languages, 'lang'))
    for name, fake in (
        ('source_files', source_files),
        ('languages', language_list),
        ('projects', FakeProjects()),
    ):
        monkeypatch.setattr(
            UECrowdinClient, name, property(lambda self, f=fake: f), raising=False
        )
    return source_files, language_list


# --- the listings


@pytest.mark.parametrize('count', [3, 25, 26, 80])
def test_the_whole_file_list_comes_back(monkeypatch, client, count):
    """Fellowship holds 80 files and Satisfactory 59. Both used to arrive as
    25, with nothing to say so."""
    attach(monkeypatch, client, rows=count, languages=1)

    client.update_file_list_and_project_data()

    assert len(client.file_list) == count


def test_the_file_listing_asks_for_every_page(monkeypatch, client):
    source_files, _ = attach(monkeypatch, client, rows=80, languages=1)

    client.update_file_list_and_project_data()

    assert ('list_files', True) in source_files.calls


def test_the_language_listing_asks_for_every_page(monkeypatch, client):
    _, languages = attach(monkeypatch, client, rows=1, languages=307)

    client.update_file_list_and_project_data()

    assert ('list_supported_languages', True) in languages.calls
    assert len(client.data['supported_languages']) == 307


def test_a_file_past_the_first_page_is_found_by_name(monkeypatch, client):
    """get_file_ID looks the name up in that list, so a short list is a file
    that cannot be found at all."""
    attach(monkeypatch, client, rows=80, languages=1)

    assert client.get_file_ID('file60.po') == 60
    assert client.get_file_ID('file79.po') == 79


def test_the_directory_listing_asks_for_every_page(monkeypatch, client):
    source_files, _ = attach(monkeypatch, client, rows=40)

    client.get_or_create_directory('file39.po')

    assert ('list_directories', True) in source_files.calls


def test_a_directory_past_the_first_page_is_reused_not_recreated(monkeypatch, client):
    """Otherwise subfolder_per_target accumulates a second folder per target."""
    attach(monkeypatch, client, rows=40)

    assert client.get_or_create_directory('file30.po') == 30


# --- the error contract the callers rely on


def test_a_directory_response_without_data_is_handed_back(monkeypatch, client):
    class Broken(FakeResource):
        def list_directories(self, **kwargs):
            return {'error': 'nope'}

    monkeypatch.setattr(
        UECrowdinClient, 'source_files', property(lambda self: Broken([]))
    )

    assert client.get_or_create_directory('Game') == {'error': 'nope'}
