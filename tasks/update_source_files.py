from pathlib import Path
import stat
from dataclasses import dataclass, field
from loguru import logger
import re
import os
import shutil
import csv
import subprocess as subp
import json

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask, init_logging, remove_read_only
from libraries import polib

CROWDIN_CELL_BYTE_LIMIT = 65535


@dataclass
class UpdateSourceFile(LocTask):
    # Declare Crowdin parameters to load them from config
    token: str | None = None
    organization: str | None = None
    project_id: int | None = None

    add_files_only: bool = False

    # TODO: Process all loc targets if none are specified
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    delete_criteria: list | None = None
    # Targets to strip leading and trailing whitespace from before upload.
    # Any other target is uploaded as the gather produced it.
    delete_whitespace_targets: list[str] = field(default_factory=list)
    # Longest source text logged for an entry delete_criteria removes.
    # A removed EULA otherwise fills the log. 0 = no limit.
    log_text_limit: int = 500

    csv_loc_targets: list[str] | None = None
    csv_dir: str = 'CSVs'
    # Locales whose existing translations should be written out as bilingual
    # CSVs too, for a project that was localized before it came to Crowdin
    translated_csv_locales: list[str] | None = None
    translated_csv_dir: str = 'TranslatedCSVs'
    # Split CSV file into multiple files based on rules
    split_csv_rules: list[tuple[str, str, str]] | None = None
    # List of tuples: (column name, regex pattern, output file name)
    namespaces_to_skip: list[str] | None = None

    src_locale: str = 'io'

    encoding: str = 'utf-8-sig'  # PO file encoding

    manual_upload: bool = True
    wait_for_upload_confirmation: bool = True

    cli_dry_run: bool = False
    cli_prep_files: bool = True

    cli_upload: bool = False
    cli_cfg_name: str = '#Config/#crowdin.upload.yaml'  # Relative to temp dir
    cli_source_dir: str = '#Sources'  # Relative to temp dir

    cli_csv_first_line_is_header: bool = True
    cli_csv_scheme: str = (
        'identifier,source_phrase,translation,max_length,labels,context'
    )

    # One Crowdin folder per loc target, or every target at the project root.
    # A folder each keeps a target that is split into many files together.
    # Set this to False for a project whose targets are already one file each,
    # and whose files therefore live at the root.
    # Note: at the root, CSV file names have to be unique across targets.
    # This moves the source files only. Translations always export into a
    # folder per target, because that is the layout the download expects.
    subfolder_per_target: bool = True

    # Crowdin file type for PO sources, e.g. gettext_unreal to get the Unreal
    # parser. Left unset, Crowdin decides for itself and new files land as
    # plain gettext. Only affects files being created: an upload never retypes
    # a file that already exists.
    file_format: str | None = None

    branch: str | None = None

    # An upload only adds and updates, so Crowdin keeps a file after its
    # content moves or is deleted in UE. After the upload, list the files in
    # each target's folder on Crowdin that this run did not produce. Only
    # those folders: anything else on Crowdin may not come from UE at all.
    # Needs subfolder_per_target, since the root is shared with other files.
    report_stale_files: bool = True
    delete_stale_files: bool = False  # Delete the files it reports

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    temp_dir: str = 'Localization/~Temp/FilesToUpload'

    _cli_cfg_path: Path | None = None
    _fname: str = 'Localization/{target}/{locale}/{target}.po'

    _cli_config: dict | None = None
    _content_path: Path | None = None
    _temp_path: Path | None = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._temp_path = Path(self._content_path / self.temp_dir)
        self._fname = self._fname.format(locale=self.src_locale, target='{target}')
        self._cli_cfg_path = self._temp_path / self.cli_cfg_name

        self._cli_config = {}
        self._cli_config['project_id'] = self.project_id
        self._cli_config['base_path'] = str(self._temp_path).replace('\\', '/')
        if self.organization:
            self._cli_config['base_url'] = (
                f'https://{self.organization}.api.crowdin.com'
            )
        else:
            self._cli_config['base_url'] = 'https://api.crowdin.com'
        self._cli_config['preserve_hierarchy'] = True
        self._cli_config['files'] = []

    def cli_files_for_loc_target(self, target: str) -> dict:
        config = {}

        config['source'] = f'{target}.po'
        if self.cli_source_dir:
            config['source'] = f'{self.cli_source_dir}/{config["source"]}'

        prefix = f'{target}/' if self.subfolder_per_target else ''
        config['dest'] = f'{prefix}{target}.po'

        if self.file_format:
            config['type'] = self.file_format

        config['translation'] = f'/{target}/%locale%/%original_file_name%'

        return config

    def cli_files_for_csv_loc_target(
        self,
        target: str,
        ignore: str | list[str] | None = None,
    ) -> dict:
        config = {}

        source_dir = f'{target}'
        if self.csv_dir:
            source_dir = f'{self.csv_dir}/{source_dir}'
        if self.cli_source_dir:
            source_dir = f'{self.cli_source_dir}/{source_dir}'

        config['source'] = f'{source_dir}/*.csv'

        prefix = f'{target}/' if self.subfolder_per_target else ''
        config['dest'] = f'{prefix}%file_name%.csv'

        if isinstance(ignore, str):
            config['ignore'] = [f'{source_dir}/{ignore}.csv']
        elif isinstance(ignore, list):
            config['ignore'] = [f'{source_dir}/{ns}.csv' for ns in ignore]

        config['first_line_contains_header'] = self.cli_csv_first_line_is_header
        config['scheme'] = self.cli_csv_scheme

        config['translation'] = f'/{target}/%locale%/%original_file_name%'

        return config

    def clip_for_log(self, text: str) -> str:
        if not self.log_text_limit or len(text) <= self.log_text_limit:
            return text
        return f'{text[: self.log_text_limit]}… ({len(text)} chars)'

    def need_delete_entry(self, entry: polib.POEntry) -> bool:
        for [prop, crit] in self.delete_criteria:
            if re.search(crit, getattr(entry, prop)):
                return True
        return False

    def filter_file(self, fpath: Path):
        temp_path = self._temp_path
        if self.cli_source_dir:
            temp_path = temp_path / self.cli_source_dir

        filtered_po_path = temp_path / fpath.name

        if not self.delete_criteria:
            shutil.copy(fpath, filtered_po_path)
            return fpath

        po = polib.pofile(fpath, encoding=self.encoding, wrapwidth=0)
        new_po = polib.POFile(encoding=self.encoding, wrapwidth=0)

        for entry in po:
            if self.need_delete_entry(entry):
                logger.info(
                    f'Removed: {fpath.name} / {entry.msgctxt} @ '
                    f'{entry.comment}\n{self.clip_for_log(entry.msgid)}'
                )
                continue
            new_po.append(entry)

        new_po.save(filtered_po_path)
        return filtered_po_path

    def within_byte_limit(
        self, text: str, limit: int = CROWDIN_CELL_BYTE_LIMIT
    ) -> bool:
        if not text:
            return True
        return len(text.encode('utf-8')) <= limit

    def write_bilingual_csv(
        self,
        po_file: str,
        target: str = '',
        dir: Path | None = None,
        locale: str = '',
    ):
        """
        Write a CSV file with source, target, and context fields
        """
        po_path = Path(po_file)
        po = polib.pofile(po_file, wrapwidth=0, encoding=self.encoding)
        po_entries = len(po)
        logger.info(f'Opened PO file: {po_file} with {po_entries} entries')

        csv_path = po_path.parent / self.csv_dir
        if dir:
            csv_path = dir

        if target:
            csv_path = csv_path / target

        if locale:
            csv_path = csv_path / locale

        csv_path.mkdir(parents=True, exist_ok=True)

        strip_whitespace = target in self.delete_whitespace_targets

        csv_data = {}

        if self.split_csv_rules:
            logger.info(f'Splitting CSV file based on rules: {self.split_csv_rules}')
            for rule in self.split_csv_rules:
                column, pattern, output_file = rule
                # key, source, target, max_length, labels, context

                for entry in po[:]:
                    if re.search(pattern, getattr(entry, column)):
                        cat = output_file
                        match = re.search(pattern, str(getattr(entry, column)))
                        if match:
                            if not cat:
                                cat = match.group(1)
                            elif '$1' in cat:
                                cat = cat.replace('$1', match.group(1))

                        # TODO: Assign MaxLength and Labels based on regex criteria / metadata
                        labels = ''
                        maxlength = ''
                        if cat not in csv_data:
                            csv_data[cat] = []
                        src = entry.msgid
                        if strip_whitespace:
                            src = src.strip()
                        csv_data[cat].append(
                            [
                                entry.msgctxt,
                                src,
                                entry.msgstr,
                                maxlength,
                                labels,
                                entry.comment,
                            ]
                        )
                        po.remove(entry)

        if len(po) > 0:
            if not csv_data.get(po_path.stem):
                csv_data[po_path.stem] = []
            for entry in po[:]:
                # TODO: Assign MaxLength and Labels based on regex criteria / metadata
                labels = ''
                maxlength = ''
                src = entry.msgid
                if strip_whitespace:
                    src = src.strip()
                csv_data[po_path.stem].append(
                    [
                        entry.msgctxt,
                        src,
                        entry.msgstr,
                        maxlength,
                        labels,
                        entry.comment,
                    ]
                )
                po.remove(entry)

        if len(po) > 0:
            logger.warning(
                f'Processed entries: {sum([len(v) for v in csv_data.values()])} of {po_entries}'
            )
            logger.error(f'Unprocessed entries: {len(po)}')

        logger.success(
            f'Processed entries: {sum([len(v) for v in csv_data.values()])} of {po_entries}'
        )

        logger.info(f'Writing CSV files: { {k: len(v) for k, v in csv_data.items()} }')

        for output_file, data in csv_data.items():
            csv_file = csv_path / f'{output_file}.csv'
            with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        'Key',
                        'SourceString',
                        'TargetString',
                        'MaxLength',
                        'Labels',
                        'CrowdinContext',
                    ]
                )

                skipped = 0
                for row in data:
                    key, source, target = row[0], row[1], row[2]
                    if not self.within_byte_limit(source) or not self.within_byte_limit(
                        target
                    ):
                        skipped += 1
                        logger.warning(
                            f'Skipping entry: key="{key}" - '
                            f'source byte length: {len(source.encode("utf-8"))}, '
                            f'target byte length: {len(target.encode("utf-8"))} '
                            f'(exceeds the {CROWDIN_CELL_BYTE_LIMIT}-byte limit)'
                        )
                        continue
                    writer.writerow(row)

                if skipped:
                    logger.warning(
                        f'Skipped {skipped} entries that exceed the byte limit'
                    )

            logger.info(f'CSV file saved: {csv_file}')

    def run_cli_command(self, args: list[str]) -> int:
        returncode = 0

        cfg_str = str(self._cli_cfg_path).replace('\\', '/')

        if self.branch:
            args.append(f'--branch={self.branch}')

        logger.info(
            'Running Crowdin CLI command:\n'
            f'crowdin {" ".join(args)} --config={cfg_str} --token=***'
        )

        with subp.Popen(
            [
                'crowdin',
                *args,
                f'--config={cfg_str}',
                f'--token={self.token}',
            ],
            stdout=subp.PIPE,
            stderr=subp.STDOUT,
            universal_newlines=True,
            cwd=self._temp_path,
            shell=True,
            encoding='utf-8',
            errors='replace',
        ) as process:
            while True:
                if not process.stdout:
                    break
                for line in process.stdout:
                    if '[ERROR] ' in line:
                        logger.error(f'| CROWD | {line.strip()}')
                    elif '[WARNING] ' in line:
                        logger.warning(f'| CROWD | {line.strip()}')
                    else:
                        logger.info(f'| CROWD | {line.strip()}')
                if process.poll() is not None:
                    break
            returncode = process.returncode

        return returncode

    def run_cli_config_sources(self, args: list[str] | None = None) -> int:
        if not args:
            args = []
        return self.run_cli_command(['config', 'sources', *args])

    def run_cli_upload_sources(self, args: list[str] | None = None) -> int:
        if not args:
            args = []
        return self.run_cli_command(['upload', 'sources', *args])

    def run_cli_upload_translations(self, args: list[str] | None = None) -> int:
        if not args:
            args = []
        return self.run_cli_command(['upload', 'translations', *args])

    def run_cli_add_files(self, args: list[str] | None = None) -> int:
        if not args:
            args = []
        return self.run_cli_command(['upload', 'sources', '--no-auto-update', *args])

    def prep_source_files(self) -> bool:
        temp_path = self._temp_path

        if self.cli_source_dir:
            temp_path = temp_path / self.cli_source_dir

        temp_path.mkdir(parents=True, exist_ok=True)

        for file in temp_path.glob('*'):
            if file.is_file():
                file.chmod(stat.S_IWRITE)
                file.unlink()
            else:
                shutil.rmtree(file, onexc=remove_read_only)

        logger.info(
            f'Prepping files for upload. Content path: {self._content_path}\n'
            f'Temporary source path for upload: {temp_path}'
        )

        targets_processed = []

        for target in self.loc_targets:
            fpath = self._content_path / self._fname.format(target=target)

            fpath = self.filter_file(fpath)
            if not fpath.exists():
                logger.error('Error during file content filtering. Aborting!')
                return False

            self._cli_config['files'].append(self.cli_files_for_loc_target(target))

            targets_processed.append(target)

        for target in self.csv_loc_targets:
            fpath = self._content_path / self._fname.format(target=target)

            fpath = self.filter_file(fpath)
            if not fpath.exists():
                logger.error('Error during file content filtering. Aborting!')
                return False

            output_path = self._temp_path / self.cli_source_dir
            if self.csv_dir:
                output_path = temp_path / self.csv_dir

            self.write_bilingual_csv(fpath, target, dir=output_path)

            files = ((temp_path / self.csv_dir) / target).glob('*.csv')

            if self.namespaces_to_skip:
                for fpath in files:
                    if fpath.stem in self.namespaces_to_skip:
                        logger.info(
                            f'Deleting CSV file: {fpath} due to namespace skip rule.'
                        )
                        fpath.unlink()

            self._cli_config['files'].append(self.cli_files_for_csv_loc_target(target))

            targets_processed.append(target)

        if self.translated_csv_locales and self.csv_loc_targets:
            for target in self.csv_loc_targets:
                for locale in self.translated_csv_locales:
                    translated_fname = f'Localization/{target}/{locale}/{target}.po'
                    fpath = self._content_path / translated_fname

                    if not fpath.exists():
                        logger.warning(
                            f'Translated PO file not found: {translated_fname}. Skipping.'
                        )
                        continue

                    self.write_bilingual_csv(
                        str(fpath),
                        target,
                        dir=self._temp_path / self.translated_csv_dir,
                        locale=locale,
                    )
                    logger.success(f'Generated translated CSVs for {target}/{locale}')

        if len(targets_processed) == len(self.loc_targets) + len(self.csv_loc_targets):
            logger.success(
                f'All targets prepped ({len(targets_processed)}): {targets_processed}'
            )
            return True

        logger.error(
            'Not all targets have been prepped: '
            f'{len(targets_processed)} out of {len(self.loc_targets)}.\n'
            f'Loc targets: {self.loc_targets}.\n'
            f'Processed targets: {targets_processed}'
        )
        return False

    def uploaded_file_names(self, target: str) -> set[str]:
        """Names of the files this run uploads into the target's folder."""
        if target not in (self.csv_loc_targets or []):
            return {f'{target}.po'}

        csv_path = self._temp_path / (self.cli_source_dir or '')
        csv_path = csv_path / (self.csv_dir or '') / target
        return {p.name for p in csv_path.glob('*.csv')}

    def stale_files(self, crowdin) -> dict[str, list[dict]]:
        """Files in each target's Crowdin folder that this run did not upload."""
        directories = crowdin.source_files.with_fetch_all().list_directories(
            projectId=self.project_id
        )['data']
        # Top-level, outside any branch: where the CLI config puts each target
        folders = {
            d['data']['name']: d['data']['id']
            for d in directories
            if d['data']['directoryId'] is None and d['data']['branchId'] is None
        }

        stale = {}
        for target in [*(self.loc_targets or []), *(self.csv_loc_targets or [])]:
            uploaded = self.uploaded_file_names(target)
            if not uploaded:
                logger.warning(
                    f'Stale files: no local files for {target}, so not checking '
                    'its folder. Everything in it would look stale.'
                )
                continue
            if target not in folders:
                continue

            files = crowdin.source_files.with_fetch_all().list_files(
                projectId=self.project_id, directoryId=folders[target]
            )['data']
            stale[target] = [
                f['data'] for f in files if f['data']['name'] not in uploaded
            ]

        return stale

    def report_stale_files_on_crowdin(self) -> bool:
        if self.branch:
            logger.info('Stale files: not checked for a branch upload.')
            return True
        if not self.subfolder_per_target:
            logger.warning(
                'Stale files: not checked, because subfolder_per_target is off '
                'and the targets share the root with files that are not ours.'
            )
            return True

        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id, silent=True
        )
        stale = self.stale_files(crowdin)

        if not any(stale.values()):
            logger.success('Stale files: none on Crowdin.')
            return True

        for target, files in stale.items():
            for f in files:
                logger.warning(
                    f'Stale file on Crowdin: {f["path"]} '
                    f'(last updated {str(f["updatedAt"])[:10]})'
                )

        if not self.delete_stale_files:
            logger.info(
                'Stale files: nothing deleted. Set delete_stale_files to delete them.'
            )
            return True

        deleted_all = True
        for files in stale.values():
            for f in files:
                try:
                    crowdin.source_files.delete_file(
                        projectId=self.project_id, fileId=f['id']
                    )
                    logger.success(f'Deleted stale file: {f["path"]}')
                except Exception as e:
                    logger.error(f'Could not delete {f["path"]}: {e}')
                    deleted_all = False

        return deleted_all

    def update_source_files(self):
        # TODO: Rewrite without API
        if self.cli_prep_files:
            self.prep_source_files()  # Preps and puts the files in the temp dir
        else:
            logger.info(
                'Skipping prep files step. Assuming files are ready for upload.'
            )
            for target in self.loc_targets:
                self._cli_config['files'].append(self.cli_files_for_loc_target(target))
            for target in self.csv_loc_targets:
                self._cli_config['files'].append(
                    self.cli_files_for_csv_loc_target(
                        target,
                        ignore=self.namespaces_to_skip,
                    ),
                )

        if not (self.manual_upload or self.cli_upload):
            crowdin = UECrowdinClient(
                self.token, logger, self.organization, self.project_id
            )

            crowdin.update_file_list_and_project_data()

        temp_path = self._temp_path

        if self.cli_source_dir:
            temp_path = temp_path / self.cli_source_dir

        logger.info(f'Uploading sources from: {self.cli_source_dir}')

        targets_processed = []

        for target in self.loc_targets:
            fpath = temp_path / f'{target}.po'

            if self.manual_upload or self.cli_upload:
                targets_processed.append(target)
                continue

            # API Upload
            # TODO: #DEPRECATED - use CLI upload
            logger.info(f'Uploading file: {fpath}')
            r = crowdin.update_file(fpath)
            if isinstance(r, int):
                targets_processed.append(target)
                logger.info('File updated.')
            else:
                logger.error(
                    f"Something went wrong. Here's the last response from Crowdin: {r}"
                )

        for target in self.csv_loc_targets:
            if self.manual_upload or self.cli_upload:
                targets_processed.append(target)
                continue

            files = ((temp_path / self.csv_dir) / target).glob('*.csv')

            updated_all_files_in_target = True

            for fpath in files:
                # API Upload
                # TODO: #DEPRECATED - use CLI upload
                logger.info(f'Uploading file: {fpath}')
                r = 0  #  crowdin.update_file(fpath)
                if isinstance(r, int):
                    targets_processed.append(target)
                    logger.info('File updated.')
                else:
                    logger.error(
                        f"Something went wrong. Here's the last response from Crowdin: {r}"
                    )
                    updated_all_files_in_target = False

            if updated_all_files_in_target:
                targets_processed.append(target)

        # Checks and reporting, mostly for API
        # TODO: #DEPRECATED - rewrite when we can remove API
        if len(targets_processed) == len(self.loc_targets) + len(self.csv_loc_targets):
            if not (self.cli_upload or self.manual_upload):
                logger.success(
                    f'Targets processed ({len(targets_processed)}): {targets_processed}'
                )
                return True
        else:
            logger.error(
                'Not all targets have been processed: '
                f'{len(targets_processed)} out of {len(self.loc_targets)}.\n'
                f'Loc targets: {self.loc_targets}.\n'
                f'Processed targets: {targets_processed}'
            )
            if self.cli_upload or self.manual_upload:
                logger.error('Manual or CLI upload is cancelled due to errors.')
            return False

        # Manual upload
        if self.manual_upload:
            logger.info(
                'Created files to upload to Crowdin manually. Openning folder...'
            )
            os.startfile(temp_path / self.csv_dir)

            if self.wait_for_upload_confirmation:
                logger.info(
                    '>>> Waiting for confirmation to continue the script execution <<<'
                )
                while True:
                    y = input('Type Y to continue... ')
                    if y in ['y', 'Y']:
                        logger.info('Got a Yes from user. Continuing...')
                        break

            logger.success(
                f'Targets processed ({len(targets_processed)}): {targets_processed}'
            )
            logger.success(
                'Manual upload considered complete. Ready for the next steps in a task list if any.'
            )
            return True

        # CLI upload
        logger.info(f'Saving CLI upload configuration to: {self._cli_cfg_path}')
        self._cli_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._cli_cfg_path, 'w', encoding='utf-8') as f:
            json.dump(self._cli_config, f, indent=4)

        return_code = 0
        if self.cli_dry_run:
            return_code = self.run_cli_config_sources()
        elif self.add_files_only:
            return_code = self.run_cli_add_files()
        else:
            return_code = self.run_cli_upload_sources()

        if return_code != 0:
            logger.error(
                f'Error while running Crowdin CLI command. Return code: {return_code}'
            )
            return False

        if self.report_stale_files or self.delete_stale_files:
            if not self.report_stale_files_on_crowdin():
                return False

        logger.success(
            f'Targets processed ({len(targets_processed)}): {targets_processed}'
        )
        return True

    def run(self):
        """
        Run the task to update source files on Crowdin.
        This method is called when the script is executed.
        """
        return self.update_source_files()


def main():
    init_logging()

    logger.info('')
    logger.info('--- Update source files on Crowdin script start ---')
    logger.info('')

    task = UpdateSourceFile()

    task.read_config(Path(__file__).name)

    result = task.run()

    logger.info('')
    logger.info('--- Update source files on Crowdin script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == '__main__':
    main()
