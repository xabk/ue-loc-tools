from dataclasses import dataclass, field
from zipfile import ZipFile
import shutil
import requests
from pathlib import Path
from time import sleep
from loguru import logger

from libraries import utilities
from libraries.crowdin import UECrowdinCli


@dataclass
class BuildAndDLParameters(utilities.Parameters):

    # Declare Crowdin parameters to load them from config
    token: str = None
    organization: str = None
    project_id: int = None

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    # Relative to Game/Content directory
    # TODO: Switch to tempfile?
    zip_name: str = 'Localization/~Temp/LocFilesTemp.zip'
    temp_dir: str = 'Localization/~Temp/LocFilesTemp'
    dest_dir: str = 'Localization/{target}/'

    locales_to_delete: list = field(
        default_factory=lambda: ['en-US-POSIX']
    )  # Delete from downloaded locales (and not import them into the game)

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    _zip_path: Path = None
    _temp_path: Path = None
    _content_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir)
        self._zip_path = self._content_path / self.zip_name
        self._temp_path = self._content_path / self.temp_dir

    def build_and_download(self):
        crowdin = UECrowdinCli(self.token, logger, self.organization, self.project_id)

        build_data = crowdin.check_or_build()

        if build_data['status'] == 'finished':
            logger.info(
                f'Build status and progress: {build_data["status"]} / {build_data["progress"]}'
            )
            build_data = crowdin.check_or_build(build_data)
        else:
            while not 'url' in build_data:
                logger.info(
                    f'Build status and progress: {build_data["status"]} / {build_data["progress"]}'
                )
                sleep(10)
                build_data = crowdin.check_or_build(build_data)

        logger.info(
            f'Build compelete. Trying to download {build_data["url"]} to: {self._zip_path}'
        )

        response = requests.get(build_data['url'])
        self._zip_path.touch(exist_ok=True)
        self._zip_path.write_bytes(response.content)

        logger.info('Download complete.')

    def unzip_file(self):

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
            dst_path = dest_path / dir.name / f'{target}.po'
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

    def process_loc_targets(self):
        logger.info(f'Targets to process ({len(self.loc_targets)}): {self.loc_targets}')

        targets_processed = []
        for t in self.loc_targets:
            if self.process_target(t):
                targets_processed += [t]

        shutil.rmtree(self._temp_path)

        if targets_processed:
            logger.info(
                f'Targets processed ({len(targets_processed)}): {targets_processed}'
            )
            self._zip_path.unlink()
            return True

        logger.warning('No targets processed.')

        return False


def main():
    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
        encoding='utf-8',
    )

    logger.info(
        '--- Build and download from Crowdin, extract and move to Localization directory ---'
    )

    cfg = BuildAndDLParameters()

    cfg.read_config(Path(__file__).name, logger)

    cfg.build_and_download()

    cfg.unzip_file()

    result = cfg.process_loc_targets()

    logger.info('--- Build, download, and move script end ---')

    if result:
        return 0

    return 1


if __name__ == "__main__":
    main()
