"""Tagging a string on a screenshot.

Both calls in tag_string take screenshotId first and projectId second, and both
were passing the project id first. add_tag was worse: its second parameter is
the tag data, so the screenshot id went in as the payload and the payload went
in as the project id. Every other call in the module names its arguments.
"""

import pytest

from tasks.import_screens import ImportScreenshots

PROJECT = 5
SCREEN = 77
STRING = 1234


class FakeScreenshots:
    """Accepts keywords only, so a positional call fails the way it should."""

    def __init__(self, tagged=()):
        self.tagged = list(tagged)
        self.calls = []

    def with_fetch_all(self):
        self.calls.append(('with_fetch_all', {}))
        return self

    def list_tags(self, **kwargs):
        self.calls.append(('list_tags', kwargs))
        return {'data': [{'data': {'stringId': s}} for s in self.tagged]}

    def add_tag(self, **kwargs):
        self.calls.append(('add_tag', kwargs))
        self.tagged.append(kwargs['data'][0]['stringId'])
        return {'data': {'id': 1}}


class FakeCrowdin:
    def __init__(self, tagged=()):
        self.screenshots = FakeScreenshots(tagged)


@pytest.fixture
def task():
    t = ImportScreenshots()
    t.project_id = PROJECT
    t._crowdin = FakeCrowdin()
    return t


def named(task, method):
    return next(kw for name, kw in task._crowdin.screenshots.calls if name == method)


def test_the_tags_are_read_for_the_right_screenshot(task):
    task.tag_string(SCREEN, STRING)

    assert named(task, 'list_tags') == {
        'projectId': PROJECT,
        'screenshotId': SCREEN,
    }


def test_the_tag_is_added_for_the_right_screenshot(task):
    task.tag_string(SCREEN, STRING)

    assert named(task, 'add_tag') == {
        'projectId': PROJECT,
        'screenshotId': SCREEN,
        'data': [{'stringId': STRING}],
    }


def test_tagging_reports_success(task):
    assert task.tag_string(SCREEN, STRING) is True


def test_every_tag_of_the_screenshot_is_looked_at(task):
    """A screenshot can carry more than one page of tags, and a tag on a later
    page reads as missing and gets added a second time."""
    task.tag_string(SCREEN, STRING)

    assert ('with_fetch_all', {}) in task._crowdin.screenshots.calls


def test_a_string_that_is_already_tagged_is_left_alone(task):
    task._crowdin = FakeCrowdin(tagged=[STRING])

    assert task.tag_string(SCREEN, STRING) is True
    assert not [c for c, _ in task._crowdin.screenshots.calls if c == 'add_tag']


def test_a_different_string_on_the_same_screenshot_is_still_added(task):
    task._crowdin = FakeCrowdin(tagged=[STRING + 1])

    assert task.tag_string(SCREEN, STRING) is True
    assert named(task, 'add_tag')['data'] == [{'stringId': STRING}]


def test_a_response_without_tags_is_a_failure(task):
    task._crowdin.screenshots.list_tags = lambda **kw: {'error': 'nope'}

    assert task.tag_string(SCREEN, STRING) is False
