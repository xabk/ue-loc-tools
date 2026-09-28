from pathlib import Path
from dataclasses import dataclass
from loguru import logger
import shutil
import subprocess as subp
import json

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask, init_logging

# Sync sources:
# - Generate configs to only include listed folders and files
# - Download sources from Source
# - Figure out how they're downloaded and saved, rename if necessary
# - Generate CLI configs
# - Upload sources to Target with the same settings

# Sync translations:
# - Download translations from Source
# - Figure out how they're downloaded and saved, rename if necessary
# - Generate CLI configs, only listed langs or all source langs
# - Upload translations to Target with the same settings


@dataclass
class SyncProjects(LocTask):
    # Declare default Crowdin parameters to load them from config
    token: str = None
    organization: str = None

    source_token: str = None
    source_organization: str = None
    source_project_id: int = None
    source_branch: str = None

    target_token: str = None
    target_organization: str = None
    target_project_id: int = None
    target_branch: str = None

    sync_src: bool = True
    # Folders to sync from source to target
    sync_src_csv_targets: list[str] = None
    # Files to sync from source to target
    sync_src_po_targets: list[str] = None

    sync_trans: bool = True
    # Languages to sync from source to target (None = all present in source project)
    sync_trans_langs: list[str] = None
    sync_trans_eq_to_source: bool = True
    sync_trans_approve: bool = True

    sync_issues: bool = False
    # Issues to sync from target to source
    sync_issues_resolve_in_target: bool = True
    sync_replies_to_target: bool = False
    sync_issues_types: list[int] = None
    sync_issues_source_to_target: bool = False

    cli_dry_run: bool = True
    cli_cfg_name: str = '#Config/#crowdin.sync.projects.yaml'  # Relative to temp dir

    cli_csv_first_line_is_header: bool = True
    cli_csv_scheme: str = (
        'identifier,source_phrase,translation,max_length,labels,context'
    )

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    temp_dir: str = 'Localization/~Temp'
    cli_temp_files_dir: str = '#ProjectSync'  # Relative to temp dir

    _project_tagline: str = None
    _cli_cfg_path: Path = None
    _cli_config: dict = None
    _content_path: Path = None
    _temp_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._temp_path = Path(self._content_path / self.temp_dir)

        self._cli_cfg_path = self._temp_path / self.cli_cfg_name

        self.source_token = self.source_token or self.token
        self.source_organization = self.source_organization or self.organization

        self.target_token = self.target_token or self.token
        self.target_organization = self.target_organization or self.organization

        self._cli_config = {}
        self._cli_config['base_path'] = str(
            self._temp_path / self.cli_temp_files_dir
        ).replace('\\', '/')
        self._cli_config['preserve_hierarchy'] = True
        self._cli_config['files'] = []

        if self.sync_src_po_targets:
            for target in self.sync_src_po_targets:
                config = self._cli_files_for_loc_target(target)
                self._cli_config['files'].append(config)

        if self.sync_src_csv_targets:
            for target in self.sync_src_csv_targets:
                config = self._cli_files_for_csv_loc_target(target)
                self._cli_config['files'].append(config)

    def _prep_config(self):
        self._cli_config['project_id'] = self.project_id
        if self.organization:
            self._cli_config['base_url'] = (
                f'https://{self.organization}.api.crowdin.com'
            )
        else:
            self._cli_config['base_url'] = 'https://api.crowdin.com'

        self._project_tagline = self._get_project_tagline(self.project_id)

        logger.info(f'Saving CLI upload configuration to: {self._cli_cfg_path}')

        if not self._cli_cfg_path.parent.exists():
            self._cli_cfg_path.parent.mkdir(parents=True)
        with open(self._cli_cfg_path, 'w', encoding='utf-8') as f:
            json.dump(self._cli_config, f, indent=4)

    def _prep_source_config(self) -> None:
        self.token = self.source_token
        self.organization = self.source_organization
        self.project_id = self.source_project_id
        self._prep_config()

    def _prep_target_config(self) -> None:
        self.token = self.target_token
        self.organization = self.target_organization
        self.project_id = self.target_project_id
        self._prep_config()

    def _get_project_tagline(self, project_id: int) -> str:
        output = self._run_cli_command(['project', 'list'], capture_output=True)
        if not output:
            logger.warning(f'Crowdin CLI error: {output}')
            return f'{project_id} (Project not found, check token access)'

        for line in output:
            if f'#{project_id} ' in line:
                return line

    def _cli_files_for_loc_target(self, target: str) -> dict[str, str]:
        config = {}

        config['source'] = f'/{target}/{target}.po'

        # config['dest'] = f'/{target}/{target}.po'

        config['translation'] = f'/{target}/%locale%/%original_file_name%'

        return config

    def _cli_files_for_csv_loc_target(
        self,
        target: str,
        ignore: str or list[str] = None,
    ) -> dict[str, str]:
        config = {}

        config['source'] = f'/{target}/*.csv'

        # config['dest'] = f'/{target}/%file_name%.csv'

        if isinstance(ignore, str):
            config['ignore'] = [f'/{target}/{ignore}.csv']
        elif isinstance(ignore, list):
            config['ignore'] = [f'/{target}/{ns}.csv' for ns in ignore]

        config['first_line_contains_header'] = self.cli_csv_first_line_is_header
        config['scheme'] = self.cli_csv_scheme

        config['translation'] = f'/{target}/%locale%/%original_file_name%'

        return config

    def _run_cli_command(
        self,
        args: list[str],
        add_args: list[str] = None,
        capture_output: bool = False,
    ) -> int or list[str]:
        returncode = 0

        cfg_str = str(self._cli_cfg_path).replace('\\', '/')

        if self.cli_dry_run:
            logger.info('CLI dry run')
            args.append('--dryrun')

        logger.info(
            'Running Crowdin CLI command:\n'
            f'crowdin {" ".join(args)} --config={cfg_str} --token=***'
        )

        if add_args:
            args += add_args

        output = []

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
                    output.append(line.strip())
                    if '[ERROR] ' in line:
                        logger.error(f'| CROWD | {line.strip()}')
                    elif '[WARNING] ' in line:
                        logger.warning(f'| CROWD | {line.strip()}')
                    else:
                        logger.info(f'| CROWD | {line.strip()}')
                if process.poll() is not None:
                    break
            returncode = process.returncode
            if capture_output:
                return output

        if returncode != 0:
            logger.error(
                f'Error while running Crowdin CLI command. Return code: {returncode}'
            )

        return returncode

    def _download_sources(self, args: list[str] = None) -> int:
        self._prep_source_config()

        logger.info(f'Downloading sources from project: {self._project_tagline}')

        return self._run_cli_command(['download', 'sources'], add_args=args)

    def _upload_sources(self, args: list[str] = None) -> int:
        self._prep_target_config()

        logger.info(f'Uploading sources to project: {self._project_tagline}')

        return self._run_cli_command(['upload', 'sources'], add_args=args)

    def _download_translations(self, args: list[str] = None) -> int:
        self._prep_source_config()

        logger.info(f'Downloading translations from project: {self._project_tagline}')

        return self._run_cli_command(['download', 'translations'], add_args=args)

    def _upload_translations(self, args: list[str] = None) -> int:
        self._prep_target_config()

        if not args:
            args = ['--translate-hidden']

        if self.sync_trans_approve:
            args.append('--auto-approve-imported')

        if self.sync_trans_eq_to_source:
            args.append('--import-eq-suggestions')

        return self._run_cli_command(['upload', 'translations'], add_args=args)

    def _clean_temp(self):
        temp_path = self._temp_path / self.cli_temp_files_dir
        if temp_path.exists():
            logger.info(f'Cleaning temp folder: {temp_path}')
            shutil.rmtree(temp_path, ignore_errors=True)

        temp_path.mkdir(parents=True)

    def _sync_sources(self) -> int:
        return_code = self._download_sources()
        return_code = return_code or self._upload_sources()
        if return_code != 0:
            logger.error('Error while syncing sources')
        else:
            logger.info('Sources synced successfully')
        return return_code

    def _sync_translations(self) -> int:
        return_code = self._download_translations()
        return_code = return_code or self._upload_translations()
        if return_code != 0:
            logger.error('Error while syncing translations')
        else:
            logger.info('Translations synced successfully')
        return return_code

    def _sync_issues(self) -> int:
        return 0

    def run(self) -> bool:
        self._clean_temp()

        if self.sync_src:
            if self._sync_sources():
                return False
        elif self._download_sources():
            # Translations cannot be uploaded without the sources they belong to
            logger.error('Could not download the sources to sync against.')
            return False

        if self.sync_trans and self._sync_translations():
            return False

        if self.sync_issues and self._sync_issues():
            return False

        logger.success(
            f'Synced project {self.source_project_id} to {self.target_project_id}.'
        )
        return True


def main():
    init_logging()
    logger.info('--- Sync sources and translations between Crowdin projects ---')

    task = SyncProjects()

    task.read_config(Path(__file__).name)

    result = task.run()
    logger.info('--- Sync projects script end ---')

    if result:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == '__main__':
    main()
