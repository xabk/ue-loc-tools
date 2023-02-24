from dataclasses import dataclass
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger
import re

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask
from libraries import polib

@dataclass
class ImportScreenshots(LocTask):

    # Declare Crowdin parameters to load them from config
    token: str = None
    organization: str = None
    project_id: int = None

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    # Link filter for Croql
    # (part of the link common to all screenshots
    # used to fetch strings with screenshot links from Crowdin)
    link_croql_filter: str = 'https://drive.google.com/file/d/'
    
    # Link regex to extract link from comment
    # Group 1 will be used as filename on Crowdin
    link_regex: str = r'(https://drive.google.com/file/d/([^/]+)/view)'

    src_locale: str = 'en-ZA'
   
    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    temp_dir: str = 'Localization/~Temp/Screenshots'

    _fname: str = 'Localization/{target}/{locale}/{target}.po'

    _content_path: Path = None
    _temp_path: Path = None

    _screenshots_to_download: dict = None
    _screens_to_tag: dict = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._temp_path = Path(self._content_path / self.temp_dir)
        self._fname = self._fname.format(locale=self.src_locale, target='{target}')
        self._crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

    def get_screens_names_and_ids_from_crowdin(self) -> dict[str: str]:
        resp = self._crowdin.screenshots.list_screenshots(self.project_id)
        print(resp)

    def get_screens_links_and_string_ids_from_crowdin_strings(
            self
    ) -> dict[str: int]:
        # resp = self._crowdin.source_strings.with_fetch_all().list_strings(
        resp = self._crowdin.source_strings.list_strings(
            self.project_id,
            croql=f'context contains "{self.link_croql_filter}"'
        )
        print(resp)

        if 'data' not in resp:
            logger.error(f'Error, no data in response. Response:\n{resp}')
            return None
        
        screenshots = {}
        for string in resp['data']:
            links = re.findall(self.link_regex, string['data']['context'])
            for link in links:
                if link[0] not in screenshots:
                    screenshots[link[0]] = []
                screenshots[link[0]].append(string['data']['id'])


    def add_screenshot_to_crowdin(
            self,
            filepath: str or Path,
            name: str = None
    ) -> dict[str: int]:
        with open(filepath, mode='rb') as file:
            storage = self._crowdin.storages.add_storage(file)

        if 'data' not in storage or 'id' not in storage['data']:
            logger.error(f'Error, no storage ID recieved. Response:\n{storage}')
            return storage

        self.info(f'{filepath.name} uploaded to storage. Moving to screenshots...')

        if name is None:
            name = Path(filepath).stem

        response = self._crowdin.screenshots.add_screenshot(
            projectId=self.project_id,
            storageId=storage['data']['id'],
            name=name,
            autoTag=False
        )

        if not 'data' in response:
            self.error(f'No data in response. Response:\n{response}')
            return response
        
        return {name: response['data']['id']}

    def import_screens_from_crowdin(self):
        logger.info(f'Content path: {self._content_path}')

        targets_processed = []

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

    task = ImportScreenshots()

    task.read_config(Path(__file__).name, logger)

    result = task.get_screens_links_and_string_ids_from_crowdin_strings()()

    logger.info('')
    logger.info('--- Update source files on Crowdin script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
