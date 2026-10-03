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


def _truncate_for_logging(text: str, max_bytes: int = 65536, max_length: int = 1000) -> str:
    if len(text.encode('utf-8')) > max_bytes:
        return text[:max_length]
    return text


@dataclass
class ImportFindings:
    """What importing one locale's CSVs into its PO turned up.

    Collected rather than logged: every one of these is a fact about a
    string, and the same string is usually found in most locales, so they
    only read well once they are rolled up across the locales of a run.
    """

    csv_entries: int = 0
    po_entries: int = 0
    # key -> (source in the PO, source in the CSV)
    source_mismatch: dict[str, tuple[str, str]] = field(default_factory=dict)
    missing_from_crowdin: dict[str, str] = field(default_factory=dict)  # key -> source
    stale_on_crowdin: dict[str, str] = field(default_factory=dict)  # key -> source
    whitespace_ignored: set[str] = field(default_factory=set)
    newlines_normalized: set[str] = field(default_factory=set)
    mismatch_ignored: set[str] = field(default_factory=set)


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
            logger.info('No loc targets specified, skipping PO targets.')
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
    ) -> ImportFindings:
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
        findings = ImportFindings(csv_entries=csv_length, po_entries=len(po_file))

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
                findings.newlines_normalized.add(key)
                translation = '\r\n'.join(translation.splitlines())

            if po_source == csv_source:
                # Update the translation (if source is the same, or if we're ignoring the mismatch)
                entry.msgstr = translation
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
                entry.msgstr = translation
                del csv_data[key]
                continue

            if self.ignore_source_mismatch:
                findings.mismatch_ignored.add(key)
                # Update the translation (if source is the same, or if we're ignoring the mismatch)
                entry.msgstr = translation
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

        findings.source_mismatch = {
            key: (data['po'], data['csv'])
            for key, data in skipped_due_to_mismatch.items()
        }
        findings.missing_from_crowdin = {
            key: data['source'] for key, data in missing_in_CSV.items()
        }
        findings.stale_on_crowdin = {
            key: data['source'] for key, data in csv_data.items()
        }
        findings.whitespace_ignored = set(ignored_unsafe_whitespace_mismatch)

        return findings

    def report_import(self, target: str, per_locale: dict[str, ImportFindings]):
        """One report per target, rolled up across that target's locales.

        A finding is about a string, and the same string turns up in most of
        the locales, so reporting per locale says the same thing dozens of
        times and never says the thing worth knowing: how many locales it
        affects. The roll-up stays inside one target of one project, because
        two projects return different locale sets and pooling them invents
        gaps that are not there.
        """
        locales = sorted(per_locale)
        n = len(locales)
        if not n:
            return

        def spread(found_in: set[str]) -> str:
            if len(found_in) == n:
                return f'all {n} locales'
            shown = ', '.join(sorted(found_in)[:5])
            more = f', +{len(found_in) - 5}' if len(found_in) > 5 else ''
            return f'{len(found_in)}/{n} locales: {shown}{more}'

        def by_key(attr: str) -> dict[str, set[str]]:
            out: dict[str, set[str]] = {}
            for locale, f in per_locale.items():
                for key in getattr(f, attr):
                    out.setdefault(key, set()).add(locale)
            return out

        mismatch = by_key('source_mismatch')
        missing = by_key('missing_from_crowdin')
        stale = by_key('stale_on_crowdin')
        whitespace = by_key('whitespace_ignored')
        newlines = by_key('newlines_normalized')
        first = per_locale[locales[0]]

        logger.info(f'--- project {self.project_id} · {target} · {n} locale(s)')
        logger.info(
            f'    CSV entries {first.csv_entries}    PO entries {first.po_entries}'
        )
        logger.info(
            f'    source mismatch {len(mismatch)}    missing from Crowdin '
            f'{len(missing)}    stale on Crowdin {len(stale)}'
        )
        ignored = by_key('mismatch_ignored')
        logger.info(
            f'    whitespace ignored {len(whitespace)}    newlines normalized '
            f'{len(newlines)}    mismatch ignored {len(ignored)}'
        )

        # A translation was thrown away. Always worth a warning, always listed.
        if mismatch:
            logger.warning(
                f'{len(mismatch)} string(s) kept their old translation dropped, '
                'because the source on Crowdin no longer matches the game:'
            )
            for key, found_in in sorted(mismatch.items()):
                po_src, csv_src = next(
                    per_locale[loc].source_mismatch[key]
                    for loc in locales
                    if key in per_locale[loc].source_mismatch
                )
                logger.warning(f'  {key}  ({spread(found_in)})')
                logger.warning(f'      game    {po_src}')
                logger.warning(f'      crowdin {csv_src}')

        # Expected in every locale of a run: lines dropped on upload on
        # purpose, and strings the community project has not been given yet.
        # In a subset it cannot be explained by either, so it is a warning.
        if missing:
            whole = {k: v for k, v in missing.items() if len(v) == n}
            partial = {k: v for k, v in missing.items() if len(v) != n}
            if whole:
                logger.info(
                    f'{len(whole)} string(s) absent from Crowdin in all {n} '
                    "locale(s) (filtered out before upload, or the new source "
                    "hasn't been uploaded yet):"
                )
                for key in sorted(whole):
                    logger.info(f'  {key}')
            if partial:
                logger.warning(
                    f'{len(partial)} string(s) absent from Crowdin in SOME '
                    'locales but not others. The source is the same for every '
                    'language, so this should not be possible:'
                )
                for key, found_in in sorted(partial.items()):
                    logger.warning(f'  {key}  ({spread(found_in)})')

        # Crowdin still holds a string the game no longer gathers.
        if stale:
            logger.warning(
                f'{len(stale)} string(s) on Crowdin that the game no longer '
                'gathers (removed or renamed in the game, the gather missed '
                "them, or this project's source is out of date). Translators "
                'may still be working on them:'
            )
            for key, found_in in sorted(stale.items()):
                logger.warning(f'  {key}  ({spread(found_in)})')

        if not mismatch and not stale:
            logger.success(
                f'project {self.project_id} · {target}: nothing needs attention.'
            )

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
        per_locale: dict[str, ImportFindings] = {}
        directories = [f for f in (self._temp_path / target).glob('*') if f.is_dir()]
        for dir in directories:
            csv_files = [f for f in dir.glob('*.csv')]
            locale = dir.name
            if dir.name in self.culture_mappings:
                locale = self.culture_mappings[locale]
            dst_path = dest_path / locale / f'{target}.po'
            if csv_files and dst_path.exists():
                pofile = polib.pofile(dst_path, wrapwidth=0, encoding=self.po_encoding)
                findings = self.load_csv_files_to_po(csv_files, pofile)
                if findings is not None:
                    per_locale[locale] = findings
                    pofile.save()
                    processed += [dir.name]
                else:
                    logger.error(f'Failed to load CSV files to PO: {csv_files}')
            else:
                logger.warning(f'Skip: {str(dir)} → {dst_path} / {dst_path.exists()}')

        logger.info(f'Locales processed ({len(processed)}): {processed}')
        self.report_import(target, per_locale)

        if len(processed) > 0:
            return True

        return False

    def process_csv_loc_targets(self) -> bool:
        if not self.csv_loc_targets:
            logger.info('No CSV loc targets specified, skipping CSV targets.')
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

        logger.warning(
            f'Only some CSV targets processed: {targets_processed} out of {self.csv_loc_targets}'
        )

        return False

    def run(self) -> bool:
        if not self.loc_targets and not self.csv_loc_targets:
            logger.error(
                'Nothing to download: set loc_targets, csv_loc_targets, or '
                'both. Leaving one of them empty is fine.'
            )
            return False

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
