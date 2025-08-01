from P4 import P4
from configparser import ConfigParser
from pathlib import Path
from dataclasses import dataclass
from loguru import logger
from itertools import chain

from libraries.utilities import LocTask, init_logging


@dataclass
class CheckoutAssets(LocTask):
    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented
    loc_targets: list | None = None
    csv_loc_targets: list | None = None

    # Relative to Game/Content directory
    add_assets_to_checkout: list | None = None
    add_paths_to_checkout: list | None = None

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    config_name: str = '../Saved/Config/WindowsEditor/SourceControlSettings.ini'
    p4_config_section: str = 'PerforceSourceControl.PerforceSourceControlSettings'

    _content_path: Path | None = None
    _config_path: Path | None = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir)
        self._config_path = (self._content_path / self.config_name).resolve()

    def checkout_assets(self):
        cfg = ConfigParser()

        logger.info(
            f'Reading P4 config from: {self._config_path} -> [{self.p4_config_section}]'
        )

        p4 = P4()

        try:
            cfg.read(self._config_path)

            if not cfg.has_section(self.p4_config_section):
                logger.error(
                    f'P4 config section [{self.p4_config_section}] not found in {self._config_path}'
                )
                return False

            if 'Port' not in cfg[self.p4_config_section]:
                logger.error(
                    f'P4 config section [{self.p4_config_section}] does not contain Port'
                )
                return False
            p4.port = cfg[self.p4_config_section]['Port']

            if 'UserName' not in cfg[self.p4_config_section]:
                logger.error(
                    f'P4 config section [{self.p4_config_section}] does not contain UserName'
                )
                return False
            p4.user = cfg[self.p4_config_section]['UserName']

            if 'Workspace' not in cfg[self.p4_config_section]:
                logger.error(
                    f'P4 config section [{self.p4_config_section}] does not contain Workspace'
                )
                return False
            p4.client = cfg[self.p4_config_section]['Workspace']
        except Exception as err:
            logger.error(f'P4 config file error: {err}')
            logger.error(f'Check p4 config file: {self._config_path}')
            return False

        logger.info(f'Trying to connect to p4 with: {p4.user} @ {p4.port}/{p4.client}')

        try:
            p4.connect()
        except Exception as err:
            logger.error(f'P4 connection error: {err}')
            logger.error(f'Check network or p4 config file: {self._config_path}')
            return False

        logger.info('Connected to p4.')

        loc_root = self._content_path / 'Localization'
        loc_root = loc_root.resolve().absolute()
        logger.info(f'Localization root: {loc_root}')
        files = list(
            chain.from_iterable(
                [item for item in (loc_root / target).glob('**/*') if item.is_file()]
                for target in [*self.loc_targets, *self.csv_loc_targets]
            )
        )

        files += [self._content_path / asset for asset in self.add_assets_to_checkout]
        if self.add_paths_to_checkout is not None:
            files += list(
                chain.from_iterable(
                    [
                        str(item).replace('#', '%23')
                        for item in (self._content_path / path).glob('**/*')
                        if item.is_file()
                    ]
                    for path in self.add_paths_to_checkout
                )
            )

        logger.info(f'Trying to check out {len(files)} assets in chunks of 20.')

        error = False
        for chunk in [files[i : i + 20] for i in range(0, len(files), 20)]:
            try:
                p4.run('edit', chunk)
            except Exception as err:
                logger.error(f'Check out error: {err}')
                logger.error(f'Check files or config. Config path: {self._config_path}')
                error = True

        if error:
            logger.warning('Some files were not checked out. Check logs for details.')
            return False

        logger.info(
            'Connected to P4 and checked out the Localization folder '
            'and community credits assets.'
        )
        return True


def main():
    init_logging()

    logger.info('--- Checkout Localization and additional assets from P4 server ---')

    task = CheckoutAssets()

    task.read_config(script=Path(__file__).name)

    result = task.checkout_assets()

    logger.info('--- Checkout assets script end ---')

    if result:
        return 0

    return 1


if __name__ == '__main__':
    main()
