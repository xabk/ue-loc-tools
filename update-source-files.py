from dataclasses import dataclass
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask


@dataclass
class UpdateSourceFile(LocTask):

    # Declare Crowdin parameters to load them from config
    token: str = None
    organization: str = None
    project_id: int = None

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    src_locale: str = 'io'

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    _fname: str = 'Localization/{target}/{locale}/{target}.po'

    _content_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._fname = self._fname.format(locale=self.src_locale, target='{target}')

    def update_source_files(self):

        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        logger.info(f'Content path: {self._content_path}')

        targets_processed = []

        for target in self.loc_targets:
            fpath = self._content_path / self._fname.format(target=target)
            logger.info('Uploading file: {fpath}')
            r = crowdin.update_file(fpath)
            if r == True:
                targets_processed.append(target)
                logger.info('File updated.')
            else:
                logger.error(
                    f'Something went wrong. Here\'s the last response from Crowdin: {r}'
                )

        if len(targets_processed) == len(self.loc_targets):
            print(f'Targets processed ({len(targets_processed)}): {targets_processed}')
            return True
        else:
            logger.error(
                'Not all targets have been processed: '
                f'{len(targets_processed)} out of {len(self.loc_targets)}. '
                f'Loc targets: {self.loc_targets}. '
                f'Processed targets: {targets_processed}'
            )

        return False


def main():
    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
    )

    logger.info('')
    logger.info('--- Update source files on Crowdin script start ---')
    logger.info('')

    task = UpdateSourceFile()

    task.read_config(Path(__file__).name, logger)

    result = task.update_source_files()

    logger.info('')
    logger.info('--- Update source files on Crowdin script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
