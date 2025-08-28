from dataclasses import dataclass, field
from zipfile import ZipFile
import shutil
import requests
from pathlib import Path
from time import sleep
from loguru import logger
import csv

from libraries.utilities import LocTask
from libraries.crowdin import UECrowdinClient
from libraries.utilities import init_logging
from libraries import polib


@dataclass
class BuildAndDownloadTranslations(LocTask):
    # Declare Crowdin parameters to load them from config
    token: str | None = None
    organization: str | None = None
    project_id: int | None = None

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to list to process all loc targets when implemented
    loc_targets: list[str] = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    csv_loc_targets: list[str] | None = None
    # For these, it's expected to have one or more CSV files per {loctarget} directory
    # These CSVs will be combined and used to populate translations in Content/Localization
    ignore_source_mismatch: bool = False
    ignore_unsafe_whitespace_mismatch: bool = True
    ignore_new_lines_mismatch: bool = True
    normalize_newlines_in_translation: bool = True

    po_encoding: str = 'utf-8-sig'
    csv_fields: list[str] = field(
        default_factory=lambda: [
            'Key',
            'SourceString',
            'TargetString',
            'MaxLength',
            'Labels',
            'CrowdinContext',
        ]
    )
    csv_key_field: str = 'Key'
    csv_source_field: str = 'SourceString'
    csv_target_field: str = 'TargetString'

    # Relative to Game/Content directory
    # TODO: Switch to tempfile?
    zip_name: str = 'Localization/~Temp/LocFilesTemp.zip'
    temp_dir: str = 'Localization/~Temp/LocFilesTemp'
    dest_dir: str = 'Localization/{target}/'

    locales_to_delete: list[str] = field(
        default_factory=lambda: ['en-US-POSIX']
    )  # Delete from downloaded locales (and not import them into the game)

    # { Crowdin locale: Unreal locale }
    # You can either set it up on Crowdin, or here, or both
    culture_mappings: dict[str, str] = field(
        default_factory=lambda: {
            'zh-CN': 'zh-Hans',
            'zh-TW': 'zh-Hant',
            'es-US': 'es-419',
        }
    )

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    _zip_path: Path | None = None
    _temp_path: Path | None = None
    _content_path: Path | None = None

    def post_update(self) -> None:
        super().post_update()
        self._content_path = Path(self.content_dir).resolve().absolute()
        self._zip_path = self._content_path / self.zip_name
        self._temp_path = self._content_path / self.temp_dir

    def build_and_download(self) -> None:
        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        build_data = crowdin.check_or_build()

        if build_data['status'] == 'finished':
            logger.info(
                f'Build status and progress: {build_data["status"]} / {build_data["progress"]}'
            )
            build_data = crowdin.check_or_build(build_data)
        else:
            while 'url' not in build_data:
                logger.info(
                    f'Build status and progress: {build_data["status"]} / {build_data["progress"]}'
                )
                sleep(10)
                build_data = crowdin.check_or_build(build_data)

        logger.info(
            f'Build compelete. Trying to download {build_data["url"]} to: {self._zip_path}'
        )

        response = requests.get(build_data['url'])
        self._zip_path.parent.mkdir(parents=True, exist_ok=True)
        self._zip_path.touch(exist_ok=True)
        self._zip_path.write_bytes(response.content)

        logger.info('Download complete.')

    def unzip_file(self) -> None:
        logger.info('Unzipping the file...')
        with ZipFile(self._zip_path, 'r') as zipfile:
            zipfile.extractall(self._temp_path)

        logger.info(f'Extracted to {self._temp_path}')

    def process_target(self, target: str) -> bool:
        logger.info(f'---\nProcessing localization target: {target}')
        if not (self._temp_path / target).is_dir():
            logger.error(
                f'{self._temp_path / target} directory not found for target {target}'
            )
            return False

        logger.info(
            f'Removing locales we do not want to overwrite: {self.locales_to_delete}'
        )

        for loc in self.locales_to_delete:
            item = self._temp_path / target / loc
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

        if self._content_path and self._content_path.is_dir():
            dest_path = self._content_path.absolute() / self.dest_dir.format(
                target=target
            )
        else:
            logger.info(
                'Resolving target directory assuming the file is in /Game/Content/Python/'
            )
            dest_path = Path(
                __file__
            ).absolute().parent.parent.parent / self.dest_dir.format(target=target)
            logger.info(dest_path)

        logger.info(f'Destination directory: {dest_path}')

        logger.info('Copying PO files...')

        processed = []
        directories = [f for f in (self._temp_path / target).glob('*') if f.is_dir()]
        for dir in directories:
            src_path = dir / f'{target}.po'
            locale = dir.name
            if dir.name in self.culture_mappings:
                locale = self.culture_mappings[locale]
            dst_path = dest_path / locale / f'{target}.po'
            if src_path.exists() and dst_path.exists():
                logger.info(f'Moving {src_path} to {dst_path}')
                shutil.move(src_path, dst_path)
                processed += [dir.name]
            else:
                logger.warning(
                    f'Skip: {src_path} / {src_path.exists()} → {dst_path} / {dst_path.exists()}'
                )

        logger.info(f'Locales processed ({len(processed)}): {processed}\n')

        if len(processed) > 0:
            return True

        return False

    def process_loc_targets(self) -> bool:
        if not self.loc_targets:
            logger.error('No loc targets to modify specified.')
            return True

        logger.info(f'Targets to process ({len(self.loc_targets)}): {self.loc_targets}')

        targets_processed = []
        targets_with_errors = []
        for t in self.loc_targets:
            if self.process_target(t):
                targets_processed += [t]
            else:
                targets_with_errors += [t]

        if len(targets_processed) == len(self.loc_targets):
            logger.success(
                f'All targets processed ({len(targets_processed)}): {targets_processed}'
            )
            return True

        if targets_processed:
            logger.error('Not all targets have been processed')
        else:
            logger.error('No targets processed.')

        logger.info(
            f'Targets processed ({len(targets_processed)}): {targets_processed}'
        )

        logger.info(
            f'Targets with errors ({len(targets_with_errors)}): {targets_with_errors}'
        )

        return True

    def load_csv_files_to_po(
        self, csv_files: list[Path], po_file: polib.POFile
    ) -> bool:
        # Load all CSVs into a single dict
        csv_data = {}
        for csv_file in csv_files:
            with open(csv_file, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # If there is no , in key, add the filename to it
                    key = row['Key']
                    if ',' not in key:
                        key = f'{csv_file.stem},{key}'

                    if key in csv_data:
                        logger.warning(f'Duplicate key found in CSV files: {key}')
                    csv_data[key] = {
                        'source': row[self.csv_source_field],
                        'target': row[self.csv_target_field],
                    }

        csv_length = len(csv_data)

        logger.info(f'Loaded {csv_length} entries from {len(csv_files)} CSV files')

        # Load CSV data into PO file, if the key exists
        # Delete CSV entry after loading it into PO
        missing_in_CSV = {}
        skipped_due_to_mismatch = {}
        ignored_unsafe_whitespace_mismatch = {}

        for entry in po_file:
            key = entry.msgctxt
            if key not in csv_data:
                # logger.warning(f'PO key not found in CSV files: {key}')
                missing_in_CSV[key] = {
                    'source': entry.msgid,
                    'target': entry.msgstr,
                }
                # Skip the entry
                continue

            csv_source = csv_data[key]['source']
            po_source = entry.msgid

            if self.ignore_new_lines_mismatch:
                csv_source = csv_source.replace('\r\n', '\n')
                po_source = po_source.replace('\r\n', '\n')

            translation = csv_data[key]['target']
            if (
                self.normalize_newlines_in_translation
                and '\r\n'.join(translation.splitlines()).strip() != translation.strip()
            ):
                logger.warning(f'Normalized newlines in translation: {key}')
                translation = '\r\n'.join(translation.splitlines())

            if po_source == csv_source:
                # Update the translation (if source is the same, or if we're ignoring the mismatch)
                entry.msgstr = csv_data[key]['target']
                del csv_data[key]
                continue

            if (
                self.ignore_unsafe_whitespace_mismatch
                and po_source.strip() == csv_source.strip()
            ):
                # logger.info(f'Ignoring unsafe whitespace mismatch for key {key}')
                ignored_unsafe_whitespace_mismatch[key] = {
                    'po': po_source,
                    'csv': csv_source,
                }
                # Update the translation (if source is the same, or if we're ignoring the mismatch)
                entry.msgstr = csv_data[key]['target']
                del csv_data[key]
                continue

            if self.ignore_source_mismatch:
                logger.warning(f'Ignoring source string mismatch for key {key}')
                # Update the translation (if source is the same, or if we're ignoring the mismatch)
                entry.msgstr = csv_data[key]['target']
                del csv_data[key]
                continue

            # Ignoring the entry because of source mismatch
            # logger.warning(
            #     f'Source string mismatch PO <> CSV for key {key}:\n{po_source}\n!=\n{csv_data[key]["source"]}'
            # )
            skipped_due_to_mismatch[key] = {
                'po': po_source,
                'csv': csv_source,
            }
            del csv_data[key]

        if skipped_due_to_mismatch:
            logger.warning(
                f'--- Skipped / Source mismatch ({len(skipped_due_to_mismatch)}):'
            )
            for key, data in skipped_due_to_mismatch.items():
                logger.warning(f'{key}:\n{data["po"]}\n!=\n{data["csv"]}')
        if missing_in_CSV:
            logger.warning(
                f'--- Missing: PO entries not found in CSV ({len(missing_in_CSV)})'
            )
            for key, data in missing_in_CSV.items():
                logger.warning(f'{key}:\n{data["source"]}')
        if csv_data:
            logger.warning(
                f'--- Missing: CSV entries not found in PO ({len(csv_data)})'
            )
            for key, data in csv_data.items():
                logger.warning(f'{key}:\n{data["source"]}')

        logger.info(f'CSV entries loaded {csv_length}')
        logger.info(f'PO entries loaded {len(po_file)}')
        logger.info(f'Skipped due to mismatch {len(skipped_due_to_mismatch)}')
        logger.info(
            f'Ignored unsafe whitespace mismatch {len(ignored_unsafe_whitespace_mismatch)}'
        )
        logger.info(f'Missing in CSV {len(missing_in_CSV)}')
        logger.info(f'Missing in PO {len(csv_data)}')

        return True

    def process_csv_target(self, target: str) -> bool:
        logger.info(f'---\nProcessing CSV localization target: {target}')
        if not (self._temp_path / target).is_dir():
            logger.error(
                f'{self._temp_path / target} directory not found for target {target}'
            )
            return False

        logger.info(
            f'Removing locales we do not want to overwrite: {self.locales_to_delete}'
        )

        for loc in self.locales_to_delete:
            item = self._temp_path / target / loc
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

        if self._content_path and self._content_path.is_dir():
            dest_path = self._content_path.absolute() / self.dest_dir.format(
                target=target
            )
        else:
            logger.info(
                'Resolving target directory assuming the file is in /Game/Content/Python/'
            )
            dest_path = Path(
                __file__
            ).absolute().parent.parent.parent / self.dest_dir.format(target=target)
            logger.info(dest_path)

        logger.info(f'Destination directory: {dest_path}')

        logger.info('Generating PO files...')

        processed = []
        directories = [f for f in (self._temp_path / target).glob('*') if f.is_dir()]
        for dir in directories:
            csv_files = [f for f in dir.glob('*.csv')]
            locale = dir.name
            if dir.name in self.culture_mappings:
                locale = self.culture_mappings[locale]
            dst_path = dest_path / locale / f'{target}.po'
            if csv_files and dst_path.exists():
                logger.info(f'Processing locale {locale} ({len(csv_files)} CSV files)')
                pofile = polib.pofile(dst_path, wrapwidth=0, encoding=self.po_encoding)
                if self.load_csv_files_to_po(csv_files, pofile):
                    logger.info(f'Saving {dst_path}')
                    pofile.save()
                    processed += [dir.name]
                else:
                    logger.error(f'Failed to load CSV files to PO: {csv_files}')
            else:
                logger.warning(f'Skip: {str(dir)} → {dst_path} / {dst_path.exists()}')

        logger.info(f'Locales processed ({len(processed)}): {processed}\n')

        if len(processed) > 0:
            return True

        return False

    def process_csv_loc_targets(self) -> bool:
        if not self.csv_loc_targets:
            logger.error('No CSV loc targets to modify specified.')
            return True

        logger.info(
            f'CSV targets to process ({len(self.csv_loc_targets)}): {self.csv_loc_targets}'
        )

        targets_processed = []
        for t in self.csv_loc_targets:
            if self.process_csv_target(t):
                targets_processed += [t]

        if targets_processed and len(targets_processed) == len(self.csv_loc_targets):
            logger.info(
                f'CSV targets processed ({len(targets_processed)}): {targets_processed}'
            )
            return True

        if not self.csv_loc_targets:
            logger.error('No CSV loc targets specified.')
            return True

        logger.warning(
            f'Only some CSV targets processed: {targets_processed} out of {self.csv_loc_targets}'
        )

        return False

    def run(self) -> bool:
        self.build_and_download()

        self.unzip_file()

        result = self.process_loc_targets()

        result = result and self.process_csv_loc_targets()

        shutil.rmtree(self._temp_path)

        if result:
            self._zip_path.unlink()

        return result


def main():
    init_logging()
    logger.info(
        '--- Build and download from Crowdin, extract and move to Localization directory ---'
    )

    task = BuildAndDownloadTranslations()

    task.read_config(Path(__file__).name)

    result = task.run()
    logger.info('--- Build, download, and move script end ---')

    if result:
        return 0

    return 1


if __name__ == '__main__':
    main()
