from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic, sleep
from loguru import logger

from crowdin_api.api_resources.translations.enums import (
    PreTranslationApplyMethod,
    PreTranslationScope,
)

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask, init_logging


@dataclass
class PreTranslate(LocTask):
    # Pre-translate every file in a Crowdin project via TM, MT or AI, and wait
    # until Crowdin is done, so a download that follows gets the result.

    # Declare Crowdin parameters to load them from config
    token: str | None = None
    organization: str | None = None
    project_id: int | None = None

    # tm, mt or ai. mt needs engine_id, ai needs ai_prompt_id.
    method: str = 'tm'
    engine_id: int | None = None
    ai_prompt_id: int | None = None

    # Crowdin language IDs. Empty = every target language of the project.
    languages: list[str] = field(default_factory=list)
    exclude_languages: list[str] = field(default_factory=list)

    # untranslated, translated or all. Anything but untranslated pays to
    # translate strings again that already have a translation.
    scope: str = 'untranslated'

    poll_seconds: int = 10
    # A first fill can sit on one percentage for many minutes. Log at least
    # this often anyway, so a long run does not look like a hung one.
    heartbeat_seconds: int = 60

    def check_settings(self) -> bool:
        try:
            method = PreTranslationApplyMethod(self.method)
            PreTranslationScope(self.scope)
        except ValueError as e:
            logger.error(f'{e}. Check method (tm, mt, ai) and scope.')
            return False

        if method is PreTranslationApplyMethod.MT and not self.engine_id:
            logger.error('Machine translation needs engine_id.')
            return False
        if method is PreTranslationApplyMethod.AI and not self.ai_prompt_id:
            logger.error('AI pre-translation needs ai_prompt_id.')
            return False

        return True

    def target_languages(self, project_languages: list[str]) -> list[str] | None:
        unknown = sorted(set(self.languages) - set(project_languages))
        if unknown:
            logger.error(
                f'Not target languages of project {self.project_id}: {unknown}. '
                f'The project has: {project_languages}'
            )
            return None

        languages = self.languages or project_languages
        return [lang for lang in languages if lang not in self.exclude_languages]

    def report(self, report: dict, file_ids: set[int]):
        # The report lists each folder as well as each file, with the same
        # numbers, so only the files are counted.
        for lang in report.get('languages', []):
            stats = [
                f['statistics'] for f in lang['files'] if f['id'] in file_ids
            ]
            strings = sum(s['phrases'] for s in stats)
            words = sum(s['words'] for s in stats)
            # A count per reason, e.g. missing_in_tm on every TM run: the
            # strings that are left for AI.
            skipped = lang.get('skipped')
            if isinstance(skipped, dict):
                skipped = ', '.join(f'{n} {why}' for why, n in skipped.items())
            note = f' (skipped: {skipped})' if skipped else ''
            logger.info(f'    {lang["id"]}: {strings} strings, {words} words{note}')

    def run(self) -> bool:
        if not self.check_settings():
            return False

        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        project = crowdin.projects.get_project(projectId=self.project_id)['data']
        languages = self.target_languages(project['targetLanguageIds'])
        if not languages:
            if languages is not None:
                logger.error('No languages left to pre-translate.')
            return False

        files = (
            crowdin.source_files.with_fetch_all()
            .list_files(projectId=self.project_id)
            .get('data', [])
        )
        file_ids = [f['data']['id'] for f in files]
        if not file_ids:
            logger.error(f'Project {self.project_id} has no files to pre-translate.')
            return False

        logger.info(
            f'Pre-translating project {self.project_id} via {self.method}: '
            f'{len(file_ids)} file(s), {len(languages)} language(s): {languages}'
        )

        # Crowdin rejects an engine or prompt the method does not use, and a
        # project's defaults set both for the task lists that need them.
        method = PreTranslationApplyMethod(self.method)
        run = crowdin.translations.apply_pre_translation(
            projectId=self.project_id,
            languageIds=languages,
            fileIds=file_ids,
            method=method,
            engineId=self.engine_id if method is PreTranslationApplyMethod.MT else None,
            aiPromptId=self.ai_prompt_id if method is PreTranslationApplyMethod.AI else None,
            scope=PreTranslationScope(self.scope),
        )['data']

        started = last_logged = monotonic()
        progress = None
        while run['status'] in ('created', 'in_progress'):
            now = monotonic()
            if (
                run['progress'] != progress
                or now - last_logged >= self.heartbeat_seconds
            ):
                progress = run['progress']
                last_logged = now
                elapsed = int(now - started)
                took = f'{elapsed // 60} min' if elapsed >= 60 else f'{elapsed} s'
                eta = f', Crowdin estimates {run["eta"]}' if run.get('eta') else ''
                logger.info(
                    f'Pre-translation {run["status"]}: {progress}% ({took}{eta})'
                )
            sleep(self.poll_seconds)
            run = crowdin.translations.pre_translation_status(
                preTranslationId=run['identifier'], projectId=self.project_id
            )['data']

        if run['status'] != 'finished':
            logger.error(
                f'Pre-translation {run["identifier"]} ended as {run["status"]}.'
            )
            return False

        logger.success(f'Pre-translation {run["identifier"]} finished:')
        report = crowdin.translations.pre_translation_report(
            preTranslationId=run['identifier'], projectId=self.project_id
        )['data']
        self.report(report, set(file_ids))

        return True


def main():
    init_logging()
    logger.info('--- Pre-translate a Crowdin project ---')

    task = PreTranslate()

    task.read_config(Path(__file__).name)

    result = task.run()
    logger.info('--- Pre-translate script end ---')

    if result:
        return 0

    return 1


if __name__ == '__main__':
    main()
