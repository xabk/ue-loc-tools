from pathlib import Path
from dataclasses import dataclass, field
from time import sleep
from loguru import logger
import polib
import sys

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask

import importlib

build_and_download = importlib.import_module("build-and-download")


@dataclass
class MTPseudo(LocTask):
    # TODO: Function to set up MT project on Crowdin

    # Declare Crowdin parameters to load them from config
    token: str = None
    organization: str = None
    project_id: int = None

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['MTTest']
    )  # Localization targets, empty = process all targets

    # TODO: Empty = all languages for project on Crowdin
    # { Crowdin language : Unreal culture }
    # E.g., { zh-CN : zh-Hans }
    languages: dict = field(
        default_factory=lambda: {
            'ru-RU': 'ru',
        }
    )

    engine_id: int or None = 1

    file_format: str = (
        'gettext_unreal'  # gettext_unreal to use the Unreal PO parser on Crowdin
    )

    src_locale: str = 'io'

    export_pattern: str = '/{target}/%locale%/{target}.po'

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    temp_dir: str = 'Localization/~Temp/FilesToUpload'

    _fname: str = 'Localization/{target}/{locale}/{target}.po'

    _languages: dict[str:str] = None

    _content_path: Path = None
    _temp_path: Path = None

    _crowdin = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._fname = self._fname.format(locale=self.src_locale, target='{target}')
        self._temp_path = Path(self.temp_dir).resolve()
        self._languages = {}
        for crowd_l, ue_l in self.languages.items():
            self._languages[crowd_l] = ue_l if ue_l else crowd_l
        self._crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

    def add_source_file(self, target: str) -> int or dict:
        fpath = self._content_path / self._fname.format(target=target)
        logger.info(f'Uploading file: {fpath}. Format: {self.file_format}')
        r = self._crowdin.add_file(
            fpath,
            type=self.file_format,
            export_pattern=self.export_pattern.format(target=target),
        )
        return r

    def add_source_files(self) -> dict[str:int]:
        # TODO: Check the files on Crowdin, update existing files?
        logger.info(f'Content path: {self._content_path}')

        targets_processed = {}

        for target in self.loc_targets:
            r = self.add_source_file(target)

            if isinstance(r, int):
                targets_processed[target] = r
                logger.info(f'File for {target} added.')
            else:
                logger.error(
                    f'Something went wrong. Here\'s the last response from Crowdin: {r}'
                )

        if len(targets_processed) == len(self.loc_targets):
            logger.info(
                f'SUCCESS: Targets processed ({len(targets_processed)}): {targets_processed}'
            )
            return targets_processed

        return targets_processed

    def pretranslate_file(self, file_id: int):
        response = self._crowdin.translations.apply_pre_translation(
            projectId=self.project_id,
            languageIds=[key.partition('-')[0] for key in self._languages.keys()],
            fileIds=[file_id],
            autoApproveOption='all',
        )

        if not 'data' in response:
            return response

        pre_id = response['data']['identifier']

        response = self._crowdin.translations.pre_translation_status(
            self.project_id, pre_id
        )

        while response['data']['status'] != 'finished':
            logger.info(
                f"Progress: {response['data']['progress']}. "
                f"ETA: {response['data']['eta']}"
            )
            sleep(10)
            response = self._crowdin.translations.pre_translation_status(
                self.project_id, pre_id
            )

        return 0

    def pretranslate_files(self, files: dict[str:int]):
        logger.info(f'Pretranslating {len(files)} files...')
        files_processed = {}

        for target, id in files.items():
            logger.info(f'Pretranslating {target} / {id}')
            r = self.pretranslate_file(id)
            if r == 0:
                files_processed[target] = id
                logger.info(f'File for {target} pretranslated.')
            else:
                logger.error(
                    f'Something went wrong with {target}. '
                    f'Here\'s the last response from Crowdin: {r}'
                )

        if len(files_processed) == len(files):
            logger.info(
                f'SUCCESS: Targets pretranslated ({len(files_processed)}): {files_processed}'
            )
            return files_processed

        return files_processed

    def mt_file(self, file_id: int):
        # logger.info(crowdin.machine_translations.list_mts())

        response = self._crowdin.translations.apply_pre_translation(
            projectId=self.project_id,
            languageIds=[key.partition('-')[0] for key in self._languages.keys()],
            fileIds=[file_id],
            method='mt',
            engineId=self.engine_id,
        )

        if not 'data' in response:
            return response

        pre_id = response['data']['identifier']

        response = self._crowdin.translations.pre_translation_status(
            self.project_id, pre_id
        )

        while response['data']['status'] != 'finished':
            logger.info(
                f"Progress: {response['data']['progress']}. "
                f"ETA: {response['data']['eta']}"
            )
            sleep(10)
            response = self._crowdin.translations.pre_translation_status(
                self.project_id, pre_id
            )

        return 0

    def mt_files(self, files: dict[str:int]):
        logger.info(f'MT {len(files)} files...')
        files_processed = {}

        for target, id in files.items():
            logger.info(f'Applying MT for {target} / {id}...')
            r = self.mt_file(id)
            if r == 0:
                files_processed[target] = id
                logger.info(f'File for {target} machine translated.')
            else:
                logger.error(
                    f'Something went wrong with {target}. '
                    f'Here\'s the last response from Crowdin: {r}'
                )

        if len(files_processed) == len(files):
            logger.info(
                f'SUCCESS: Targets pretranslated ({len(files_processed)}): {files_processed}'
            )
            return files_processed

        return files_processed

    def approve_language(self, lang_id: str):
        r = self._crowdin.string_translations.with_fetch_all().list_language_translations(
            self.project_id,
            lang_id,
            croql='count of approvals = 0 and provider is mt',
        )

        if not 'data' in r:
            return r

        translations = [s['data']['translationId'] for s in r['data']]

        logger.info(f'Approving {len(translations)} translations...')

        for i, id in enumerate(translations):
            self._crowdin.string_translations.add_approval(self.project_id, id)
            if (i + 1) % 50 == 0:
                logger.info('Approved 50 translations...')

    def approve_languages(self):
        languages = self._languages.keys()
        logger.info(f'Approving {len(languages)} languages...')
        lang_processed = {}

        for lang in languages.items():
            logger.info(f'Approving {lang}...')
            r = self.mt_file(id)
            if r == 0:
                lang_processed[lang] = id
                logger.info(f'Language {lang} approved.')
            else:
                logger.error(
                    f'Something went wrong with {lang}. '
                    f'Here\'s the last response from Crowdin: {r}'
                )

        if len(lang_processed) == len(languages):
            logger.info(
                f'SUCCESS: Languages approved ({len(lang_processed)}): {lang_processed}'
            )
            return lang_processed

        return lang_processed

    def download_transalted_files(self):
        task = build_and_download.BuildAndDownloadTranslations(
            token=self.token,
            organization=self.organization,
            project_id=self.project_id,
            loc_targets=self.loc_targets,
        )
        task.post_update()
        task.culture_mappings.update(self.languages)
        print(task)

        task.build_and_download()

        task.unzip_file()

        return task.process_loc_targets()

    def pseudo_file(self, file_path: Path):
        pass

    def pseudo_target(self, file_path: Path):
        pass

    def pseudo_targets(self, file_path: Path):
        pass

    def create_monster_target(self):
        pass

    def create_monster_target(self):
        pass


def main():
    logger.remove()
    logger.add(
        sys.stdout,
        format='<green>{time:HH:mm:ss.SSS}</green> | '
        '<level>{level: <8}</level> | '
        '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>',
        level='INFO',
    )
    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
        encoding='utf-8',
    )

    logger.info('')
    logger.info('--- Add source files on Crowdin script start ---')
    logger.info('')

    task = MTPseudo()

    task.read_config(Path(__file__).name, logger)

    # files = task.add_source_files()

    files = {'MTTest': 1064}

    task.pretranslate_files(files)

    task.mt_files(files)

    task.approve_language('ru')

    # task.download_transalted_files()

    logger.info('')
    logger.info('--- Add source files on Crowdin script end ---')
    logger.info('')

    if 0:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
