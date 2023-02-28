from dataclasses import dataclass
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger
import re
import requests
from time import sleep

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask
from libraries import polib

@dataclass
class ImportScreenshots(LocTask):

    # Declare Crowdin parameters to load them from config
    token: str = None
    organization: str = None
    project_id: int = None

    # Link filter for Croql
    # (part of the link common to all screenshots
    # used to fetch strings with screenshot links from Crowdin)
    link_croql_filter: str = 'https://drive.google.com/file/d/'
    
    # Link regex to extract link from comment
    # Group 0 will be used as link
    # Group 1 will be used as filename on Crowdin
    # and as {name} to create a download link if dl_link is set
    link_regex: str = '(https://drive.google.com/file/d/([^/]+)/view)'

    # If set, it will be formatted with {name} and used to download the file
    dl_link: str = 'https://drive.google.com/uc?id={name}&export=download'

    def_ext: str = '.png'
   
    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    temp_dir: str = 'Localization/~Temp/Screenshots'

    _content_path: Path = None
    _temp_path: Path = None    

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._temp_path = Path(self._content_path / self.temp_dir)
        self._crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

    def get_screens_names_and_ids_from_crowdin(self) -> dict[str: dict]:
        resp = self._crowdin.screenshots.with_fetch_all().list_screenshots(self.project_id)        
        # print(f'Screens resp:\n{resp}')

        if 'data' not in resp:
            logger.error(f'Error, no data in response. Response:\n{resp}')
            return None
        
        screens_on_crowdin = {}
        for screen in resp['data']:
            (name, _, ext) = screen['data']['name'].rpartition('.')
            if not name:
                name = ext
            screens_on_crowdin[name] = {
                'id': screen['data']['id'],
                'tags': [tag['stringId'] for tag in screen['data']['tags']]
            }

        # print(f'Screens:\n{self._screens_on_crowdin}')
        return screens_on_crowdin

    def get_screens_links_and_string_ids_from_crowdin_strings(
            self
    ) -> dict[str: list[int]]:
        resp = self._crowdin.source_strings.with_fetch_all().list_strings(
        # resp = self._crowdin.source_strings.list_strings(
            self.project_id,
            croql=f'context contains "{self.link_croql_filter}"'
        )
        # print(f'Strings resp:\n{resp}')

        if 'data' not in resp:
            logger.error(f'Error, no data in response. Response:\n{resp}')
            return None
        
        screens_linked_in_strings = {}
        for string in resp['data']:
            links = re.findall(self.link_regex, string['data']['context'])
            for link in links:
                if link[0] not in screens_linked_in_strings:
                    screens_linked_in_strings[link[0]] = []
                screens_linked_in_strings[link[0]].append(string['data']['id'])
        
        # print(f'Screens:\n{self._screens_to_dl}')
        return screens_linked_in_strings
    
    def get_screenshots_to_download(
            self, 
            screens_linked_in_strings: dict,
            screens_on_crowdin: dict,
    ) -> dict[str: str]:
        if not screens_linked_in_strings:
            screens_linked_in_strings = self.get_screens_links_and_string_ids_from_crowdin_strings()

        if not screens_on_crowdin:
            screens_on_crowdin = self.get_screens_names_and_ids_from_crowdin()
        
        links = {}
        for link in screens_linked_in_strings.keys():
            id = re.search(self.link_regex, link)[2]
            if id not in screens_on_crowdin.keys():
                links[id] = link
    
        return links

    def download_screenshot(
            self,
            url: str or Path,
            name: str = None,
            path: Path = None
    ):
        if not path:
            path = self._temp_path

        if not name:
            _name = re.search(self.link_regex, url)[2]
            if (path / f'{_name}{self.def_ext}').exists():
                logger.info(f'Found the file, skipping download: { path / (_name + self.def_ext)}')
                return path / f'{_name}{self.def_ext}'

        _url = url
        if self.dl_link is not None:
            _url = self.dl_link.format(name=re.search(self.link_regex, url)[2])

        logger.info(f'Trying to download the file: {_url}')
        r = requests.get(_url, allow_redirects=True)

        if r.status_code == 403:
            logger.error('Response 403, Google hates me :( Use VPN to download more screens.')
            raise

        suffix: str = ''

        cd = r.headers.get('content-disposition', None)
        if cd:
            fname = re.findall('filename=(.+)', cd)
            if len(fname) > 0:
                suffix = Path(fname[0]).suffix
        
        if not suffix:
            logger.warning(f'No filename in headers. Assuming the screenshots is {self.def_ext}...')
            suffix = self.def_ext
        
        file_path = path / f'{_name}{suffix}'

        logger.info(f'Saving: {file_path}')

        open(file_path, 'wb').write(r.content)

        return file_path
    
    def download_screenshots(self, urls: list[str], path: Path = None) -> list[Path]:
        processed_screens = []
        for url in urls:
            processed_screens.append(self.download_screenshot(url=url, path=path))            

        if len(processed_screens) == len(urls):
            logger.info(f'All good, uploaded {len(urls)} screenshots!')
        else:
            logger.error(f'Uploaded only {len(processed_screens)}/{len(urls)} screenshots:\n'
                         f'{processed_screens}')
        
        return processed_screens


    def add_screenshot_to_crowdin(
            self,
            path: str or Path,
            name: str = None
    ) -> dict[str: int]:
        with open(path, mode='rb') as file:
            storage = self._crowdin.storages.add_storage(file)

        if 'data' not in storage or 'id' not in storage['data']:
            logger.error(f'Error, no storage ID recieved. Response:\n{storage}')
            return storage

        logger.info(f'{path.name} uploaded to storage. Moving to screenshots...')

        if name is None:
            name = Path(path).name

        response = self._crowdin.screenshots.add_screenshot(
            projectId=self.project_id,
            storageId=storage['data']['id'],
            name=name,
            autoTag=False
        )

        if not 'data' in response:
            logger.error(f'No data in response. Response:\n{response}')
            return response
        
        return {name: response['data']['id']}
    
    def add_screenshots_to_crowdin(self, paths: list[Path]) -> list[dict]:
        processed_screens = []
        for path in paths:
            processed_screens.append(self.add_screenshot_to_crowdin(path=path))
        if len(processed_screens) == len(paths):
            logger.info(f'All good, uploaded {len(paths)} screenshots!')
        else:
            logger.error(f'Uploaded only {len(processed_screens)}/{len(paths)} '
                         f'screenshots:\n{processed_screens}')
        
        return processed_screens
    
    def get_strings_to_tag(
            self, 
            screens_linked_in_strings: dict[str: list[int]] = None,
            screens_on_crowdin: dict[str:dict] = None,
    ) -> dict[str: str]:
        if not screens_linked_in_strings:
            screens_linked_in_strings = self.get_screens_links_and_string_ids_from_crowdin_strings()

        if not screens_on_crowdin:
            screens_on_crowdin = self.get_screens_names_and_ids_from_crowdin()
        
        tags = []
        for link, string_ids in screens_linked_in_strings.items():
            id = re.search(self.link_regex, link)[2]
            if id not in screens_on_crowdin.keys():
                logger.warning(f'Missing screenshot on Crowdin: {id}. Please upload missing screens, then tag.')

            for string_id in string_ids:
                if string_id in screens_on_crowdin[id]['tags']:
                    continue
                tags.append((screens_on_crowdin[id]['id'], string_id))

        return tags
    
    def tag_string(self, screen_id: int, string_id: int) -> bool:
        logger.info(f'Tagging string {string_id} on screenshot {screen_id}...')
        tags = self._crowdin.screenshots.list_tags(self.project_id, screen_id)
        if not 'data' in tags:
            logger.error(f'No data in response for screenshot {screen_id}')
            return None
        
        if string_id in [tag['data']['stringId'] for tag in tags['data']]:
            logger.info(f'String {string_id} already tagged on screenshot {screen_id}.')
            return True
        
        response = self._crowdin.screenshots.add_tag(self.project_id, screen_id, [{'stringId': string_id}])
        if 'data' in response:
            return True
        else:
            logger.error(f'No data in response:\n{response}')
            return None
    
    def tag_strings(self, tags: list[tuple]) -> list[tuple]:
        processed_tags = []
        for tag in tags:
            tag = self.tag_string(tag[0], tag[1])
            if tag is not None:
                processed_tags.append(tag)

        if len(processed_tags) == len(tags):
            logger.info(f'All good, tagged {len(tags)} strings!')
        else:
            logger.error(f'Tagged only {len(processed_tags)}/{len(tags)} '
                         f'screenshots:\n{processed_tags}'
                         f'Failed to process:\n{[tag for tag in tags if tag not in processed_tags]}')
        
        return processed_tags

    def import_screens_from_crowdin(self):
        strings_processed = []

        logger.info('Downloading links from strings on Crowdin...')
        links_in_strings = self.get_screens_links_and_string_ids_from_crowdin_strings()
        logger.info(f'Links from strings on Crowdin: {len(links_in_strings)}')

        logger.info('Downloading list of screenshots on Crowdin...')
        screens_on_crowdin = self.get_screens_names_and_ids_from_crowdin()
        logger.info(f'Screenshots already on Crowdin: {len(screens_on_crowdin)}')
        
        logger.info('Making a list of screenshots to dowlnoad via links and upload to Crowdin...')
        screens_to_add = self.get_screenshots_to_download(links_in_strings, screens_on_crowdin)
        logger.info(f'Screenshots to download and upload: {len(screens_to_add)}')

        logger.info('Downloading screenshots...')
        paths = self.download_screenshots(screens_to_add.values())
        if len(paths) != len(screens_to_add):
            logger.error(f'Not all screenshots have been downloaded. Downloaded screenshots:\n'
                         f'{paths}\n'
                         f'Screenshots to upload:\n'
                         f'{screens_to_add}\n')
        else:
            logger.info(f'Downloaded screenshots: {len(paths)}')

        logger.info('Uploading screenshots to Crowdin...')
        added_screens = self.add_screenshots_to_crowdin(paths)
        if len(added_screens) != len(paths):
            logger.error(f'Not all screenshots have been uploaded. Uploaded screenshots:\n'
                         f'{added_screens}\n'
                         f'Screenshots to upload:\n'
                         f'{paths}\n')
        else:
            logger.info(f'Downloaded screenshots: {len(added_screens)}')
        
        logger.info('Dwonloading updated list of screenshots on Crowdin...')
        screens_on_crowdin = self.get_screens_names_and_ids_from_crowdin()

        missing_screens = [s for s in added_screens if s.keys()[0] not in screens_on_crowdin.keys()]

        if missing_screens:
            logger.error(f'Not all screenshots are uploaded. Missing screenshots:\n'
                         f'{missing_screens}')
        else:
            logger.info(f'No missing screenshots! Proceeding to tagging.')
        
        logger.info('Making a list of strings to tag...')
        strings_to_tag = self.get_strings_to_tag(links_in_strings, screens_on_crowdin)
        logger.info(f'Success. Strings to tag: {len(strings_to_tag)}')

        logger.info('Tagging strings...')
        tagged_strings = self.tag_strings(strings_to_tag)
        if not len(tagged_strings) == len(strings_to_tag):
            strings_to_tag = self.get_strings_to_tag()
            logger.warning(f'Not all strings have been tagged, missing {len(strings_to_tag)}')

        return True


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

    result = task.import_screens_from_crowdin()

    logger.info('')
    logger.info('--- Update source files on Crowdin script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
