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
from libraries.utilities import LocTask, init_logging
from libraries import polib


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
    delete_unsafe_whitespace: bool = False

    csv_loc_targets: list[str] | None = None
    csv_dir: str = 'CSVs'
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

    branch: str | None = None

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

        config['dest'] = f'{target}/{target}.po'

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

        config['dest'] = f'{target}/%file_name%.csv'

        if isinstance(ignore, str):
            config['ignore'] = [f'{source_dir}/{ignore}.csv']
        elif isinstance(ignore, list):
            config['ignore'] = [f'{source_dir}/{ns}.csv' for ns in ignore]

        config['first_line_contains_header'] = self.cli_csv_first_line_is_header
        config['scheme'] = self.cli_csv_scheme

        config['translation'] = f'/{target}/%locale%/%original_file_name%'

        return config

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
                    f'{entry.comment}\n{entry.msgid}'
                )
                continue
            new_po.append(entry)

        new_po.save(filtered_po_path)
        return filtered_po_path

    def write_bilingual_csv(
        self, po_file: str, target: str = '', dir: Path | None = None
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

        csv_path.mkdir(parents=True, exist_ok=True)

        csv_data = {}

        if self.split_csv_rules:
            logger.info(f'Splitting CSV file based on rules: {self.split_csv_rules}')
            for rule in self.split_csv_rules:
                column, pattern, output_file = rule
                # key, source, target, max_length, labels, context

                for entry in po[:]:
                    if re.search(pattern, getattr(entry, column)):
                        cat = output_file
                        if not cat:
                            # logger.info(
                            #     f'Trying to match category for {getattr(entry, column)}'
                            # )
                            # logger.info(f'Using pattern: {pattern}')
                            match = re.search(pattern, str(getattr(entry, column)))
                            # logger.info(f'Match: {match}')
                            cat = match.group(1)

                        # TODO: Assign MaxLength and Labels based on regex criteria / metadata
                        labels = ''
                        maxlength = ''
                        if cat not in csv_data:
                            csv_data[cat] = []
                        src = entry.msgid
                        if self.delete_unsafe_whitespace:
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
                csv_data[po_path.stem].append(
                    [
                        entry.msgctxt,
                        entry.msgid,
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

                for row in data:
                    writer.writerow(row)

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
                shutil.rmtree(file)

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
