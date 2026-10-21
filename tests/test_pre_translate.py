"""Pre-translation runs on Crowdin, so the task's job is to start it with the
right languages and files, wait for it, and say what it did.

Crowdin is replaced with a fake that records the request and plays back a
sequence of statuses, the way a real run moves from created to finished.
"""

import pytest
from loguru import logger

from tasks import pre_translate
from tasks.pre_translate import PreTranslate


@pytest.fixture
def logged():
    captured = []
    sink_id = logger.add(lambda m: captured.append(m.record), level='DEBUG')
    yield captured
    logger.remove(sink_id)


def messages(records) -> str:
    return '\n'.join(r['message'] for r in records)


REPORT = {
    'languages': [
        {
            'id': 'fr',
            # 1 is the folder, 2 the file inside it: the same numbers twice.
            'files': [
                {'id': 1, 'statistics': {'phrases': 77, 'words': 273}},
                {'id': 2, 'statistics': {'phrases': 77, 'words': 273}},
            ],
            'skipped': [],
        }
    ],
    'preTranslateType': 'ai',
}


class FakeCrowdin:
    def __init__(self, statuses, targets=('fr', 'de', 'ja', 'enWC'), files=(2,)):
        self.statuses = list(statuses)
        self.targets = list(targets)
        self.files = list(files)
        self.applied = None

        fake = self

        class Projects:
            def get_project(self, projectId):
                return {'data': {'targetLanguageIds': fake.targets}}

        class SourceFiles:
            def with_fetch_all(self):
                return self

            def list_files(self, projectId):
                return {'data': [{'data': {'id': i}} for i in fake.files]}

        class Translations:
            def apply_pre_translation(self, **kwargs):
                fake.applied = kwargs
                return {'data': fake.next_status()}

            def pre_translation_status(self, preTranslationId, projectId):
                return {'data': fake.next_status()}

            def pre_translation_report(self, preTranslationId, projectId):
                return {'data': REPORT}

        self.projects = Projects()
        self.source_files = SourceFiles()
        self.translations = Translations()

    def next_status(self):
        status, progress, *eta = self.statuses.pop(0)
        run = {'identifier': 'run-1', 'status': status, 'progress': progress}
        if eta:
            run['eta'] = eta[0]
        return run


@pytest.fixture
def task():
    t = PreTranslate()
    t.token = 'token'
    t.project_id = 133
    t.poll_seconds = 0
    return t


def use(monkeypatch, fake: FakeCrowdin):
    monkeypatch.setattr(pre_translate, 'UECrowdinClient', lambda *a, **k: fake)


FINISHES = [('created', 0), ('in_progress', 51), ('finished', 100)]


def test_waits_for_the_run_to_finish(task, monkeypatch, logged):
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)

    assert task.run() is True

    assert fake.statuses == []
    assert 'in_progress: 51%' in messages(logged)


def clock(monkeypatch, *seconds):
    monkeypatch.setattr(pre_translate, 'monotonic', iter(seconds).__next__)


def progress_lines(records) -> list[str]:
    return [r['message'] for r in records if 'in_progress' in r['message']]


def test_a_stuck_percentage_still_logs_once_a_minute(task, monkeypatch, logged):
    """The first fill of 133 sat on single digits for twenty minutes."""
    use(monkeypatch, FakeCrowdin([('in_progress', 4)] * 4 + [('finished', 100)]))
    # Started, then one reading per poll.
    clock(monkeypatch, 0, 0, 30, 59, 75)

    task.run()

    assert progress_lines(logged) == [
        'Pre-translation in_progress: 4% (0 s)',
        'Pre-translation in_progress: 4% (1 min)',
    ]


def test_a_new_percentage_logs_at_once(task, monkeypatch, logged):
    use(monkeypatch, FakeCrowdin([('in_progress', 4), ('in_progress', 5), ('finished', 100)]))
    clock(monkeypatch, 0, 0, 10)

    task.run()

    assert progress_lines(logged) == [
        'Pre-translation in_progress: 4% (0 s)',
        'Pre-translation in_progress: 5% (10 s)',
    ]


def test_progress_carries_the_crowdin_estimate(task, monkeypatch, logged):
    use(monkeypatch, FakeCrowdin([('in_progress', 8, '20 minutes'), ('finished', 100)]))
    clock(monkeypatch, 0, 1260)

    task.run()

    assert progress_lines(logged) == [
        'Pre-translation in_progress: 8% (21 min, Crowdin estimates 20 minutes)'
    ]


def test_a_failed_run_fails_the_task(task, monkeypatch, logged):
    use(monkeypatch, FakeCrowdin([('in_progress', 10), ('failed', 10)]))

    assert task.run() is False

    assert 'ended as failed' in messages(logged)


def test_every_target_language_but_the_excluded_ones(task, monkeypatch):
    task.exclude_languages = ['enWC']
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)

    task.run()

    assert fake.applied['languageIds'] == ['fr', 'de', 'ja']


def test_only_the_languages_asked_for(task, monkeypatch):
    task.languages = ['ja', 'fr']
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)

    task.run()

    assert fake.applied['languageIds'] == ['ja', 'fr']


def test_a_language_the_project_lacks_starts_nothing(task, monkeypatch, logged):
    task.languages = ['fr', 'xx']
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)

    assert task.run() is False

    assert fake.applied is None
    assert "['xx']" in messages(logged)


def test_every_file_and_only_untranslated_strings(task, monkeypatch):
    fake = FakeCrowdin(FINISHES, files=(2, 5, 9))
    use(monkeypatch, fake)

    task.run()

    assert fake.applied['fileIds'] == [2, 5, 9]
    assert fake.applied['scope'].value == 'untranslated'


def test_ai_sends_its_prompt(task, monkeypatch):
    task.method = 'ai'
    task.ai_prompt_id = 12
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)

    task.run()

    assert fake.applied['method'].value == 'ai'
    assert fake.applied['aiPromptId'] == 12


@pytest.mark.parametrize('method', ['tm', 'mt'])
def test_only_ai_sends_the_prompt(task, monkeypatch, method):
    """A project sets the prompt once in its defaults. Crowdin rejects a TM or
    MT request that carries it, so the task leaves it out."""
    task.method = method
    task.engine_id = 7
    task.ai_prompt_id = 12
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)

    assert task.run() is True

    assert fake.applied['aiPromptId'] is None


@pytest.mark.parametrize('method, engine', [('mt', 7), ('tm', None), ('ai', None)])
def test_only_mt_sends_the_engine(task, monkeypatch, method, engine):
    task.method = method
    task.engine_id = 7
    task.ai_prompt_id = 12
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)

    task.run()

    assert fake.applied['engineId'] == engine


@pytest.mark.parametrize(
    'settings, complaint',
    [
        ({'method': 'ai'}, 'ai_prompt_id'),
        ({'method': 'mt'}, 'engine_id'),
        ({'method': 'llm'}, 'method'),
        ({'scope': 'everything'}, 'scope'),
    ],
)
def test_bad_settings_start_nothing(task, monkeypatch, logged, settings, complaint):
    for key, value in settings.items():
        setattr(task, key, value)
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)

    assert task.run() is False

    assert fake.applied is None
    assert complaint in messages(logged)


def test_report_counts_files_not_folders(task, monkeypatch, logged):
    use(monkeypatch, FakeCrowdin(FINISHES))

    task.run()

    assert 'fr: 77 strings, 273 words' in messages(logged)


def test_report_names_what_was_skipped(task, monkeypatch, logged):
    """A TM run always skips what the TM lacks. That is what AI is for, so
    it is information, not a warning."""
    fake = FakeCrowdin(FINISHES)
    use(monkeypatch, fake)
    report = {
        'languages': [
            {
                'id': 'es',
                'files': [{'id': 2, 'statistics': {'phrases': 23, 'words': 112}}],
                'skipped': {'missing_in_tm': 51},
            }
        ]
    }
    monkeypatch.setattr(
        fake.translations, 'pre_translation_report', lambda **k: {'data': report}
    )

    task.run()

    assert 'es: 23 strings, 112 words (skipped: 51 missing_in_tm)' in messages(logged)
    assert 'WARNING' not in {r['level'].name for r in logged}
