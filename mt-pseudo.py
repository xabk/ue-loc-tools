from pathlib import Path
from dataclasses import dataclass, field
from time import sleep
from loguru import logger
import sys

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask


@dataclass
class MTPseudo(LocTask):

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
    # TODO: Add missing Crowdin languages if specified here?
    languages = ['ru']

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

    _content_path: Path = None
    _temp_path: Path = None

    _crowdin = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._fname = self._fname.format(locale=self.src_locale, target='{target}')
        self._temp_path = Path(self.temp_dir).resolve()
        self._crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

    def add_source_file(self, fpath: Path) -> int or dict:
        logger.info(f'Uploading file: {fpath}. Format: {self.file_format}')
        r = self._crowdin.add_file(
            fpath,
            type=self.file_format,
            export_pattern=self.export_pattern.format(target=target),
        )
        return r

    def add_source_files(self) -> dict:
        logger.info(f'Content path: {self._content_path}')

        targets_processed = {}

        for target in self.loc_targets:
            fpath = self._content_path / self._fname.format(target=target)
            r = self.add_source_file(fpath)

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
            languageIds=self.languages,
            fileIds=[file_id],
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
            languageIds=self.languages,
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
            logger.info(f'Pretranslating {target} / {id}')
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

    def approve_file(self, file_id: int):
        pass

    def approve_files(self, files: dict[str:int]):
        pass

    def download_transalted_files(self):
        pass

    def pseudo(self):
        pass

    def create_monster_language(self):
        pass

    def add_to_TM(self, file_id: int):
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

    # result = task.add_source_files()

    # task.pretranslate_file(948)

    # task.mt_file(948)

    task.pretranslate_files({'MTTest': 948})

    task.mt_files({'MTTest': 948})

    logger.info('')
    logger.info('--- Add source files on Crowdin script end ---')
    logger.info('')

    if 0:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
