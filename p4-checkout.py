from P4 import P4
from configparser import ConfigParser
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

from libraries import utilities


@dataclass
class AssetsCheckout(utilities.Parameters):

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    # Relative to Game/Content directory
    add_assets_to_checkout: list = None

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    config_name: str = '../Saved/Config/Windows/SourceControlSettings.ini'
    p4_config_section: str = 'PerforceSourceControl.PerforceSourceControlSettings'

    _content_path: Path = None
    _config_path: Path = None

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
            p4.port = cfg[self.p4_config_section]['Port']
            p4.user = cfg[self.p4_config_section]['UserName']
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

        loc_dir = self._content_path / 'Localization'
        files = [item for item in loc_dir.glob('**/*') if item.is_file()]
        files += [self._content_path / asset for asset in self.add_assets_to_checkout]

        logger.info(f'Trying to check out {len(files)} assets')

        try:
            p4.run('edit', files)
        except Exception as err:
            logger.error(f'Check out error: {err}')
            logger.error(
                f'Check files or config. File list: {files}. Config path: {self._config_path}'
            )
            return False

        logger.info(
            'Connected to P4 and checked out the Localization folder and community credits assets.'
        )
        return True


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

    logger.info('--- Checkout Localization and additional assets from P4 server ---')

    cfg = AssetsCheckout()

    cfg.read_config(Path(__file__).name, logger)

    result = cfg.checkout_assets()

    logger.info('--- Checkout assets script end ---')

    if result:
        return 0

    return 1


if __name__ == "__main__":
    main()
