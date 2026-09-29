"""Building the longest locale without going through Crowdin.

A project that wants a locale to stress its UI does not want machine
translation: the translations it measures are the ones already on disk. The
offline flag turns the Crowdin round trip off and leaves only that step.
"""

from pathlib import Path

import pytest

from tasks.mt_pseudo import MTPseudo


@pytest.fixture
def task():
    t = MTPseudo()
    t.token = 'tok'
    t.organization = 'org'
    t.project_id = 5
    t.loc_targets = ['Goat2Mobile']
    return t


def record_pipeline(task, longest=True, copied=True):
    """Stub every step and report which ones ran."""
    called = []

    def step(name, result=None):
        def inner(*args, **kwargs):
            called.append(name)
            return result

        return inner

    task.add_or_update_files = step('add_or_update_files', {})
    task.pretranslate_files = step('pretranslate_files')
    task.mt_files = step('mt_files')
    task.approve_languages = step('approve_languages')
    task.download_transalted_files = step('download_transalted_files')
    task.create_longest_locale_for_targets = step('longest', longest)
    task.create_longest_locale_pack = step('pack')
    task.copy_longest_to_content = step('copy', copied)
    return called


# --- where the locales are read from


def test_offline_reads_the_downloaded_locales(task):
    """The POs are wherever the last download left them, not in the staging
    directory that only a Crowdin round trip fills."""
    task.offline = True

    task.post_update()

    assert task._temp_path == task._content_path / 'Localization'


def test_online_reads_the_staging_directory(task):
    task.offline = False

    task.post_update()

    assert task._temp_path == (task._content_path / task.temp_dir).resolve()
    assert task._temp_path != task._content_path / 'Localization'


# --- what actually runs


def test_offline_touches_nothing_on_crowdin(task):
    task.offline = True
    called = record_pipeline(task)

    assert task.run() is True
    assert called == ['longest']


def test_online_walks_the_whole_pipeline(task):
    task.offline = False
    called = record_pipeline(task)

    assert task.run() is True
    assert called == [
        'add_or_update_files',
        'pretranslate_files',
        'mt_files',
        'approve_languages',
        'download_transalted_files',
        'longest',
        'pack',
        'copy',
    ]


def test_offline_is_off_by_default(task):
    called = record_pipeline(task)

    task.run()

    assert 'add_or_update_files' in called


# --- the verdict the runner reads


def test_a_failed_offline_run_reports_failure(task):
    task.offline = True
    record_pipeline(task, longest=False)

    assert task.run() is False


@pytest.mark.parametrize('longest,copied', [(False, True), (True, False)])
def test_either_half_failing_fails_the_online_run(task, longest, copied):
    task.offline = False
    called = record_pipeline(task, longest=longest, copied=copied)

    assert task.run() is False
    # A failure part way through must not skip the rest: the pack and the copy
    # are what the next run reads.
    assert called[-1] == 'copy'


# --- the separator


def test_the_padded_entry_matches_the_length_it_pads_to(task):
    """The whole point of the locale is that it is as long as the longest
    translation, so the separator has to be counted, not assumed to be two
    characters."""
    base = 'Hi'
    longest = 'Hallo Welt und mehr'

    for separator in ('| ', '>>>> ', '*'):
        task.separator = separator
        out = task.create_longest(base, longest)

        assert out.startswith(task.prefix) and out.endswith(task.suffix)
        body = out[len(task.prefix) : -len(task.suffix)]
        assert len(body) == len(longest), f'separator {separator!r} -> {body!r}'
        assert body.startswith(base + separator)


def test_the_default_separator_is_what_it_always_was(task):
    assert task.separator == '| '
    assert '| ' in task.create_longest('Hi', 'Hallo Welt und mehr')


def test_source_at_least_as_long_as_the_translation_is_left_alone(task):
    out = task.create_longest('A very long source string', 'Kurz')

    assert out == f'{task.prefix}A very long source string{task.suffix}'
