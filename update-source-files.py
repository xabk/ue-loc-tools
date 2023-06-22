from dataclasses import dataclass
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger
import re
import os
import shutil

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask
from libraries import polib


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

    encoding: str = 'utf-8-sig'  # PO file encoding

    manual_upload: bool = False

    wait_for_upload_confirmation: bool = False

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
        self._temp_path = Path(self._content_path / self.temp_dir)
        self._fname = self._fname.format(locale=self.src_locale, target='{target}')

    def need_delete_entry(self, entry):
        for [prop, crit] in self.delete_criteria:
            if re.search(crit, getattr(entry, prop)):
                return True
        return False

    def filter_file(self, fpath: Path):
        po = polib.pofile(fpath, encoding=self.encoding, wrapwidth=0)
        new_po = polib.POFile(encoding=self.encoding, wrapwidth=0)
        for entry in po:
            if self.need_delete_entry(entry):
                logger.info(
                    f'Removed: {fpath.name} / {entry.msgstr} @ {entry.comment}\n{entry.msgid}'
                )
                continue
            new_po.append(entry)

        new_po.save(self._temp_path / fpath.name)
        return self._temp_path / fpath.name

    def update_source_files(self):
        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        crowdin.update_file_list_and_project_data()

        self._temp_path.mkdir(parents=True, exist_ok=True)

        logger.info(f'Content path: {self._content_path}')

        targets_processed = []

        for target in self.loc_targets:
            fpath = self._content_path / self._fname.format(target=target)
            if self.delete_criteria:
                logger.info(
                    f'Filtering file: {fpath} to {self._temp_path}/{fpath.name}'
                )
                fpath = self.filter_file(fpath)
                if not fpath.exists():
                    logger.error('Error during file content filtering. Aborting!')
                    return False
            
            if self.manual_upload:
                shutil.copy(fpath, self._temp_path / fpath.name)
                targets_processed.append(target)
                continue
            
            logger.info(f'Uploading file: {fpath}')
            r = crowdin.update_file(fpath)
            if isinstance(r, int):
                targets_processed.append(target)
                logger.info('File updated.')
            else:
                logger.error(
                    f'Something went wrong. Here\'s the last response from Crowdin: {r}'
                )

        if self.manual_upload:
            logger.info('Created files to upload to Crowdin manually. Openning folder...')
            os.startfile(self._temp_path)

            if self.wait_for_upload_confirmation:
                logger.info('>>> Waiting for confirmation to continue the script execution <<<')
                while True:
                    y = input('Type Y to continue... ')
                    if y in ['y','Y']:
                        break


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
