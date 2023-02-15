from pathlib import Path
from dataclasses import dataclass, field
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

    file_format: str = 'gettext_unreal'  # gettext_unreal to use the Unreal PO parser on Crowdin

    src_locale: str = 'io'

    export_pattern: str = '/{target}/%locale%/{target}.po'

    delete_criteria: list = field(
        # list of rules, each rule is a list: [property to check, regex, comment to add]
        #  - property to check: msgid, msgctx, etc. See libraries/polib
        default_factory=lambda: [
            [
                'comment',
                r'SourceLocation:	/Any/Path/You/Want/',
            ],
            [
                'msgctxt',
                r'Any_Key_Pattern_You_Want_To_Delete',
            ],
        ]
    )

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    temp_dir: str = 'Localization/~Temp/FilesToUpload'

    _fname: str = 'Localization/{target}/{locale}/{target}.po'

    _content_path: Path = None
    _temp_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._fname = self._fname.format(locale=self.src_locale, target='{target}')
        self._temp_path = Path(self.temp_dir).resolve()

    def add_source_files(self) -> int:
        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        logger.info(f'Content path: {self._content_path}')

        targets_processed = []

        for target in self.loc_targets:
            fpath = self._content_path / self._fname.format(target=target)
            logger.info(f'Uploading file: {fpath}. Format: {self.file_format}')
            r = crowdin.add_file(
                fpath,
                type=self.file_format,
                export_pattern=self.export_pattern.format(target=target),
            )
            if isinstance(r, int):
                targets_processed += [target]
                logger.info(f'File for {target} added.')
            else:
                logger.error(
                    f'Something went wrong. Here\'s the last response from Crowdin: {r}'
                )

        if len(targets_processed) == len(self.loc_targets):
            print('Targets processed', len(targets_processed), targets_processed)
            return True

        return False

    def pretranslate(self, id: int):
        pass

    def mt(self, id: int):
        pass

    def download_transalted_files(self):
        pass

    def pseudo(self):
        pass

    def create_monster_language(self):
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

    result = task.add_source_files()

    logger.info('')
    logger.info('--- Add source files on Crowdin script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
