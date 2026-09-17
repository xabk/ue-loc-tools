"""Checkout paths resolve against the project, so plugin folders are nameable.

A game feature plugin keeps its string tables at
Plugins/GameFeatures/<Name>/Content/Localization/StringTables, which is outside
the game's own Content/. While these paths were content-relative there was no
way to write that down at all. Satisfactory is the project that needed it.

The second half is the migration: a config written for the old base resolves to
nothing, and silently checking out zero files is the worst way to find out.
"""

import pytest

from tasks.p4_checkout import CheckoutAssets


@pytest.fixture
def project(tmp_path):
    """A project with string tables in Content and in a game feature plugin."""
    game = tmp_path / 'Content' / 'Localization' / 'StringTables'
    game.mkdir(parents=True)
    (game / 'Core.csv').write_text('a', encoding='utf-8')

    plugin = (
        tmp_path
        / 'Plugins'
        / 'GameFeatures'
        / 'PSA'
        / 'Content'
        / 'Localization'
        / 'StringTables'
    )
    plugin.mkdir(parents=True)
    (plugin / 'PSA.csv').write_text('b', encoding='utf-8')

    return tmp_path


def task_for(project, **kwargs):
    t = CheckoutAssets()
    t.project_dir = str(project)
    for key, value in kwargs.items():
        setattr(t, key, value)
    t.post_update()
    return t


def test_a_plugin_path_resolves(project):
    """The point of the change."""
    t = task_for(
        project,
        add_paths_to_checkout=[
            'Plugins/GameFeatures/PSA/Content/Localization/StringTables'
        ],
    )

    resolved = t._project_path / t.add_paths_to_checkout[0]

    assert resolved.is_dir()
    assert [f.name for f in resolved.glob('*.csv')] == ['PSA.csv']


def test_a_content_path_still_resolves(project):
    """Nothing under Content becomes harder to name; it just gains a prefix."""
    t = task_for(
        project, add_paths_to_checkout=['Content/Localization/StringTables']
    )

    resolved = t._project_path / t.add_paths_to_checkout[0]

    assert [f.name for f in resolved.glob('*.csv')] == ['Core.csv']


def test_the_localization_root_sits_under_content(project):
    """Loc targets have not moved: only the base they resolve from has."""
    t = task_for(project)

    assert (t._project_path / 'Content/Localization').is_dir()


def test_a_stale_content_relative_path_is_called_out(project):
    """The migration case: this path was correct before and finds nothing now."""
    from loguru import logger

    messages = []
    sink = logger.add(lambda m: messages.append(m), level='WARNING')
    try:
        task_for(project, add_paths_to_checkout=['Localization/StringTables'])
    finally:
        logger.remove(sink)

    assert any('Localization/StringTables' in m for m in messages)
    assert any('Content/' in m for m in messages)


def test_a_path_that_is_simply_wrong_is_not_explained_away(project):
    """Only paths that would have worked before get the migration hint, so a
    genuine typo is not dressed up as a migration problem."""
    messages = []
    from loguru import logger

    sink = logger.add(lambda m: messages.append(m), level='WARNING')
    try:
        task_for(project, add_paths_to_checkout=['Nowhere/At/All'])
    finally:
        logger.remove(sink)

    assert not messages


def test_a_correct_path_warns_about_nothing(project):
    messages = []
    from loguru import logger

    sink = logger.add(lambda m: messages.append(m), level='WARNING')
    try:
        task_for(
            project,
            add_paths_to_checkout=[
                'Content/Localization/StringTables',
                'Plugins/GameFeatures/PSA/Content/Localization/StringTables',
            ],
        )
    finally:
        logger.remove(sink)

    assert not messages
