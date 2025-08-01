from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger
import re
import requests

from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask, init_logging


@dataclass
class ImportScreenshots(LocTask):
    # Declare Crowdin parameters to load them from config
    token: str | None = None
    organization: str | None = None
    project_id: int | None = None

    src_google_drive: bool = False
    src_local: bool = False

    ####################################################################################
    # Google Drive sourcing: Get links from context, DL from GDrive, push and tag on Crowdin
    ####################################################################################

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

    ####################################################################################
    # Local sourcing: Taking screenshots from a folder and matching by string key
    ####################################################################################

    # Detach all screens to keep things tidy
    # and avoid having a bunch of outdated screens attached to a string over time
    # ### Filtered by `local_scr_name_prefix` ###
    local_detach_all_auto_screens: bool = True

    # Delete all screens and reupload from scratch
    # (useful if you want to clean up auto Screenshots on Crowdin)
    # ### Filtered by `local_scr_name_prefix` ###
    local_delete_all_auto_screens: bool = False

    # Base directory for screenshots
    local_screens_base_dir: str = 'StringTables/Screenshots'

    # Subdirectory for screenshots, this is to allow for dirrerent types of screenshots
    local_screens_sub_dir: str = 'Cards'

    local_scr_name_preprocessing: list[tuple[str, str]] = field(
        default_factory=lambda: [
            (r'(?<!\s)(?=[A-Z])', ' '),  # CamelCase → Camel Case
        ]
    )
    # Screenshot names prefixed before upload to make them easy to maintain
    local_scr_name_prefix: str = 'AutoCardScreenshot_'

    # Croql filter to fetch strings to attach screenshots to
    local_croql_filter: str = ''

    local_multi_tagging: bool = True

    ### Single-Tagging ###

    local_match_field: str = 'context'

    local_match_regex: str = r'Screenshot:\s+{screenshot}'

    ### Multi-Tagging ###

    # Only string keys matching this pattern will be used to match against screenshot names
    local_all_strings_key_scope: str = r'^Gameplay_Strings,.*_Name$'
    # Group 1 will be used as a stem to find all relevant strings to attach the screenshot
    local_extract_key_stem_pattern: str = r'^(Gameplay_Strings,.*)_Name$'
    # Patterns to filter out strings that are not relevant to the screenshot
    local_relevant_strings_key_filter: list[str] = field(
        default_factory=lambda: [
            r'^{stem}_.*$',
        ]
    )
    # Patterns to exclude from filtered strings that are relevant to the screenshot
    local_relevant_strings_key_exclude: list[str] = field(
        default_factory=lambda: [
            # r'^{stem}_NameModifier', # E.g., we can exclude BaseKey_NameModifier strings
        ]
    )

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    temp_dir: str = 'Localization/~Temp/Screenshots'

    _content_path: Path | None = None
    _temp_path: Path | None = None

    _src_base_path: Path | None = None
    _src_path: Path | None = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._temp_path = Path(self._content_path / self.temp_dir)
        self._crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        self._src_base_path = self._content_path / self.local_screens_base_dir
        self._src_path = self._src_base_path
        if self.local_screens_sub_dir:
            self._src_path = self._src_path / self.local_screens_sub_dir

    def get_screens_names_and_ids_from_crowdin(self) -> dict[str, dict] | None:
        logger.info('Fetching list of screenshots on Crowdin...')
        resp = self._crowdin.screenshots.with_fetch_all().list_screenshots(
            projectId=self.project_id
        )

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
                'tags': [tag['stringId'] for tag in screen['data']['tags']],
            }

        logger.info(f'Fetched {len(screens_on_crowdin)} screenshots.')
        return screens_on_crowdin

    def get_screens_links_and_string_ids_from_crowdin_strings(
        self,
    ) -> dict[str, list[int]] | None:
        resp = self._crowdin.source_strings.with_fetch_all().list_strings(
            self.project_id, croql=f'context contains "{self.link_croql_filter}"'
        )

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

        return screens_linked_in_strings

    def get_screenshots_to_download(
        self,
        screens_linked_in_strings: dict,
        screens_on_crowdin: dict,
    ) -> dict[str, str]:
        if not screens_linked_in_strings:
            screens_linked_in_strings = (
                self.get_screens_links_and_string_ids_from_crowdin_strings()
            )

        if not screens_on_crowdin:
            screens_on_crowdin = self.get_screens_names_and_ids_from_crowdin()

        links = {}
        for link in screens_linked_in_strings.keys():
            id = re.search(self.link_regex, link)[2]
            if id not in screens_on_crowdin.keys():
                links[id] = link

        return links

    def download_screenshot(
        self, url: str | Path, name: str | None = None, path: Path | None = None
    ):
        if not path:
            path = self._temp_path

        if not name:
            _name = re.search(self.link_regex, url)
            if _name:
                _name = _name[2]
            if (path / f'{_name}.{self.def_ext}').exists():
                logger.info(
                    f'Found the file, skipping download: {path / f"{_name}.{self.def_ext}"}'
                )
                return path / f'{_name}.{self.def_ext}'

        _url = url
        if self.dl_link is not None:
            _name = re.search(self.link_regex, url)
            if _name:
                _name = _name[2]
                _url = self.dl_link.format(name=_name)

        logger.info(f'Trying to download the file: {_url}')
        r = requests.get(_url, allow_redirects=True)

        if r.status_code == 403:
            logger.error(
                'Response 403, Google hates me :( Use VPN to download more screens.'
            )
            raise

        suffix: str = ''

        cd = r.headers.get('content-disposition', None)
        if cd:
            fname = re.findall('filename=(.+)', cd)
            if len(fname) > 0:
                suffix = Path(fname[0]).suffix

        if not suffix:
            logger.warning(
                f'No filename in headers. Assuming the screenshots is {self.def_ext}...'
            )
            suffix = f'.{self.def_ext}'

        file_path = path / f'{_name}{suffix}'

        logger.info(f'Saving: {file_path}')

        open(file_path, 'wb').write(r.content)

        return file_path

    def download_screenshots(
        self, urls: list[str], path: Path | None = None
    ) -> list[Path]:
        processed_screens = []
        for url in urls:
            processed_screens.append(self.download_screenshot(url=url, path=path))

        if len(processed_screens) == len(urls):
            logger.info(f'All good, uploaded {len(urls)} screenshots!')
        else:
            logger.error(
                f'Uploaded only {len(processed_screens)}/{len(urls)} screenshots:\n'
                f'{processed_screens}'
            )

        return processed_screens

    def add_screenshot_to_crowdin(
        self, path: Path, name: str | None = None
    ) -> dict[str, int]:
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
            autoTag=False,
        )

        if 'data' not in response:
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
            logger.error(
                f'Uploaded only {len(processed_screens)}/{len(paths)} '
                f'screenshots:\n{processed_screens}'
            )

        return processed_screens

    def get_strings_to_tag(
        self,
        screens_linked_in_strings: dict[str, list[int]] | None = None,
        screens_on_crowdin: dict[str, dict] | None = None,
    ) -> list[tuple]:
        if not screens_linked_in_strings:
            screens_linked_in_strings = (
                self.get_screens_links_and_string_ids_from_crowdin_strings()
            )

        if not screens_on_crowdin:
            screens_on_crowdin = self.get_screens_names_and_ids_from_crowdin()

        tags = []
        for link, string_ids in screens_linked_in_strings.items():
            id = re.search(self.link_regex, link)[2]
            if id not in screens_on_crowdin.keys():
                logger.warning(
                    f'Missing screenshot on Crowdin: {id}. Please upload missing screens, then tag.'
                )

            for string_id in string_ids:
                if string_id in screens_on_crowdin[id]['tags']:
                    continue
                tags.append((screens_on_crowdin[id]['id'], string_id))

        return tags

    def tag_string(self, screen_id: int, string_id: int) -> bool:
        logger.info(f'Tagging string {string_id} on screenshot {screen_id}...')
        tags = self._crowdin.screenshots.list_tags(self.project_id, screen_id)
        if 'data' not in tags:
            logger.error(f'No data in response for screenshot {screen_id}')
            return False

        if string_id in [tag['data']['stringId'] for tag in tags['data']]:
            logger.info(f'String {string_id} already tagged on screenshot {screen_id}.')
            return True

        response = self._crowdin.screenshots.add_tag(
            self.project_id, screen_id, [{'stringId': string_id}]
        )
        if 'data' in response:
            return True
        else:
            logger.error(f'No data in response:\n{response}')
            return False

    def tag_strings(self, tags: list[tuple]) -> list[tuple]:
        processed_tags = []
        for tag in tags:
            tag = self.tag_string(tag[0], tag[1])
            if tag is not None:
                processed_tags.append(tag)

        if len(processed_tags) == len(tags):
            logger.info(f'All good, tagged {len(tags)} strings!')
        else:
            logger.error(
                f'Tagged only {len(processed_tags)}/{len(tags)} '
                f'screenshots:\n{processed_tags}'
                f'Failed to process:\n{[tag for tag in tags if tag not in processed_tags]}'
            )

        return processed_tags

    def import_screens_from_crowdin(self):
        strings_processed = []

        logger.info('Downloading links from strings on Crowdin...')
        links_in_strings = self.get_screens_links_and_string_ids_from_crowdin_strings()
        logger.info(f'Links from strings on Crowdin: {len(links_in_strings)}')

        logger.info('Downloading list of screenshots on Crowdin...')
        screens_on_crowdin = self.get_screens_names_and_ids_from_crowdin()
        logger.info(f'Screenshots already on Crowdin: {len(screens_on_crowdin)}')

        logger.info(
            'Making a list of screenshots to dowlnoad via links and upload to Crowdin...'
        )
        screens_to_add = self.get_screenshots_to_download(
            links_in_strings, screens_on_crowdin
        )
        logger.info(f'Screenshots to download and upload: {len(screens_to_add)}')

        logger.info('Downloading screenshots...')
        paths = self.download_screenshots(screens_to_add.values())
        if len(paths) != len(screens_to_add):
            logger.error(
                f'Not all screenshots have been downloaded. Downloaded screenshots:\n'
                f'{paths}\n'
                f'Screenshots to upload:\n'
                f'{screens_to_add}\n'
            )
        else:
            logger.info(f'Downloaded screenshots: {len(paths)}')

        logger.info('Uploading screenshots to Crowdin...')
        added_screens = self.add_screenshots_to_crowdin(paths)
        if len(added_screens) != len(paths):
            logger.error(
                f'Not all screenshots have been uploaded. Uploaded screenshots:\n'
                f'{added_screens}\n'
                f'Screenshots to upload:\n'
                f'{paths}\n'
            )
        else:
            logger.info(f'Downloaded screenshots: {len(added_screens)}')

        if len(added_screens) > 0:
            logger.info('Dwonloading updated list of screenshots on Crowdin...')
            screens_on_crowdin = self.get_screens_names_and_ids_from_crowdin()

        missing_screens = [
            s for s in added_screens if s.keys()[0] not in screens_on_crowdin.keys()
        ]

        if missing_screens:
            logger.error(
                f'Not all screenshots are uploaded. Missing screenshots:\n'
                f'{missing_screens}'
            )
        else:
            logger.info('No missing screenshots! Proceeding to tagging.')

        logger.info('Making a list of strings to tag...')
        strings_to_tag = self.get_strings_to_tag(links_in_strings, screens_on_crowdin)
        logger.info(f'Success. Strings to tag: {len(strings_to_tag)}')

        logger.info('Tagging strings...')
        tagged_strings = self.tag_strings(strings_to_tag)
        if not len(tagged_strings) == len(strings_to_tag):
            strings_to_tag = self.get_strings_to_tag()
            logger.warning(
                f'Not all strings have been tagged, missing {len(strings_to_tag)}'
            )

        return True

    ### Local sourcing ###

    def preprocess_local_screenshots(self) -> list[Path]:
        files = [f for f in self._src_path.glob(f'*.{self.def_ext}')]
        logger.info(f'Found {len(files)} screenshots to preprocess.')
        processed_files = []
        for file in files:
            stem = file.stem

            if stem.startswith(self.local_scr_name_prefix):
                processed_files.append(file)
                continue

            for rule in self.local_scr_name_preprocessing:
                if re.search(rule[0], stem):
                    # replace all occurences of the rule
                    stem = re.sub(rule[0], rule[1], stem)

            if stem != file.stem:
                logger.info(f'Preprocessed: {file.stem} → {stem}')
                new_name = file.parent / f'{stem}{file.suffix}'
                if new_name.exists():
                    logger.warning(f'File {new_name} already exists. Overwriting...')
                    new_name.unlink()
                file.rename(new_name)

            processed_files.append(file)

        logger.info('Preprocessed screenshots.')

        return processed_files

    def copy_and_prefix_local_screenshots(self) -> list[Path]:
        files = [f for f in self._src_path.glob(f'*.{self.def_ext}')]
        logger.info(f'Found {len(files)} screenshots to copy and process.')
        processed_files = []
        for file in files:
            new_name = self.local_scr_name_prefix + file.name
            new_path = self._temp_path / self.local_screens_sub_dir / new_name

            if not new_path.parent.exists():
                new_path.parent.mkdir(parents=True, exist_ok=True)

            if new_path.exists():
                logger.warning(f'File {new_path} already exists. Overwriting...')
                new_path.unlink()

            new_path.write_bytes(file.read_bytes())

            processed_files.append(new_path)

        logger.info('Copied and prefixed screenshots.')

        return processed_files

    def detach_Crowdin_screenshots_tags(self, screens: dict[str, dict]):
        new_screens = {}
        for name, screen in screens.items():
            if self.local_scr_name_prefix and not name.startswith(
                self.local_scr_name_prefix
            ):
                new_screens[name] = screen
                continue

            logger.info(f'Detaching tags from screenshot {name} {screen["id"]}...')

            response = self._crowdin.screenshots.clear_tags(
                projectId=self.project_id, screenshotId=screen['id']
            )
            if response:
                logger.error(f'Error in response:\n{response}')
            else:
                new_screens[name] = {'id': screen['id'], 'tags': []}

        return new_screens

    def delete_Crowdin_screenshots(self, screens: dict[str, dict]):
        new_screens = {}
        for name, screen in screens.items():
            if self.local_scr_name_prefix and not name.startswith(
                self.local_scr_name_prefix
            ):
                new_screens[name] = screen
                continue

            logger.info(f'Deleting screenshot {name} {screen["id"]}...')

            response = self._crowdin.screenshots.delete_screenshot(
                projectId=self.project_id, screenshotId=screen['id']
            )
            if response:
                logger.error(f'Error in response:\n{response}')
                new_screens[name] = screen

        return new_screens

    def get_all_strings(self) -> list[dict]:
        logger.info(
            f'Fetching all strings from Crowdin that match CroQL: `{self.local_croql_filter}`'
        )
        strings = self._crowdin.source_strings.with_fetch_all().list_strings(
            projectId=self.project_id, croql=self.local_croql_filter
        )
        if 'data' not in strings:
            logger.error(f'Error, no data in response. Response:\n{strings}')
            return []

        strings = [s['data'] for s in strings['data']]

        logger.info(f'Fetched {len(strings)} strings.')

        return strings

    def get_card_name_strings(self, strings: list[dict]) -> list[dict]:
        return [
            s
            for s in strings
            if re.match(self.local_all_strings_key_scope, s['identifier'])
        ]

    def find_stem_for_screenshot(
        self, strings: list[dict], scr_name: str
    ) -> list[dict] | None:
        def norm(s: str) -> str:
            return re.sub(r'[\s\-_]', '', s).lower()

        stem = None
        for string in strings:
            if norm(string['text']) == norm(scr_name):
                stem = re.match(
                    self.local_extract_key_stem_pattern, string['identifier']
                )
            if stem:
                return stem.group(1)
        return None

    def match_at_least_one_rule_by_stem(
        self, patterns: list[str], stem: str, string: str
    ) -> bool:
        for pattern in patterns:
            pattern = pattern.format(stem=stem)
            if re.match(pattern, string):
                return True
        return False

    def find_strings_for_stem(self, strings: list[dict], stem: str) -> list[dict]:
        return [
            s
            for s in strings
            if self.match_at_least_one_rule_by_stem(
                self.local_relevant_strings_key_filter, stem, s['identifier']
            )
            and not self.match_at_least_one_rule_by_stem(
                self.local_relevant_strings_key_exclude, stem, s['identifier']
            )
        ]

    def process_screenshot_multi(
        self, file: Path, strings: dict, card_name_strings: dict, screens: dict
    ):
        # Find the key stem
        card_text = file.stem
        if card_text.startswith(self.local_scr_name_prefix):
            card_text = card_text[len(self.local_scr_name_prefix) :]
        stem = self.find_stem_for_screenshot(card_name_strings, card_text)
        if not stem:
            logger.warning(
                f'No strings found that match the screenshot `{card_text}`. Skipping...'
            )
            return False
        logger.info(f'Stem for screenshot `{file.stem}`: {stem}')

        # Find all relevant strings to tag
        relevant_strings = self.find_strings_for_stem(strings, stem)
        logger.info(
            f'Relevant strings for screenshot `{file.stem}`: ({len(relevant_strings)})'
        )

        # Check if the screenshot is already on Crowdin
        screen = screens.get(file.stem, None)
        screen_id = None
        existing_tags = []
        if not screen:
            logger.info(f'Uploading screenshot {file.stem} to Crowdin...')
            screen_id = self.add_screenshot_to_crowdin(file)[file.name]
        else:
            logger.info(f'Screenshot {file.stem} already exists on Crowdin. Tagging...')
            screen_id = screen['id']
            existing_tags = screen['tags']

        # Tag all relevant strings
        string_ids = []
        for string in relevant_strings:
            if string['id'] not in existing_tags:
                string_ids.append({'stringId': string['id']})

        if not string_ids:
            logger.info(f'No new strings to tag for screenshot {file.stem}.')
            return True

        logger.info(f'Tagging strings for screenshot {file.stem}...')

        response = self._crowdin.screenshots.add_tag(
            projectId=self.project_id, screenshotId=screen_id, data=string_ids
        )
        if 'data' in response:
            logger.success(
                f'Successfully tagged {len(string_ids)} strings for {file.stem}.'
            )
            return True
        else:
            logger.error(f'No data in response:\n{response}')
            return False

    def process_screenshot_single(
        self, file: Path, local_screens_and_strings: dict, crowdin_screens: dict
    ):
        # Find the key stem
        screen_stem = file.stem
        if screen_stem.startswith(self.local_scr_name_prefix):
            screen_stem = screen_stem[len(self.local_scr_name_prefix) :]

        # Find all relevant strings to tag
        string_ids_to_tag = local_screens_and_strings.get(screen_stem, [])
        if not string_ids_to_tag:
            logger.warning(
                f'No strings found that match the screenshot `{screen_stem}`. Skipping...'
            )
            return False

        # Check if the screenshot is already on Crowdin
        screen = crowdin_screens.get(file.stem, None)
        screen_id = None
        existing_tags = []
        if not screen:
            logger.info(f'Uploading screenshot {file.stem} to Crowdin...')
            screen_id = self.add_screenshot_to_crowdin(file)[file.name]
        else:
            logger.info(f'Screenshot {file.stem} already exists on Crowdin. Tagging...')
            screen_id = screen['id']
            existing_tags = screen['tags']

        # Tag all relevant strings
        string_ids = []
        for string_id in string_ids_to_tag:
            if string_id not in existing_tags:
                string_ids.append({'stringId': string_id})

        if not string_ids:
            logger.info(f'No new strings to tag for screenshot {file.stem}.')
            return True

        logger.info(f'Tagging strings for screenshot {file.stem}...')

        response = self._crowdin.screenshots.add_tag(
            projectId=self.project_id, screenshotId=screen_id, data=string_ids
        )
        if 'data' in response:
            logger.success(
                f'Successfully tagged {len(string_ids)} strings for {file.stem}.'
            )
            return True
        else:
            logger.error(f'No data in response:\n{response}')
            return False

    def process_local_screenshots(self):
        self.preprocess_local_screenshots()
        files = self.copy_and_prefix_local_screenshots()

        screens = self.get_screens_names_and_ids_from_crowdin()
        strings = self.get_all_strings()

        card_name_strings = {}
        screens_and_strings = {}
        files_processed = []
        if self.local_multi_tagging:
            card_name_strings = self.get_card_name_strings(strings)
        else:
            for file in files:
                screen = file.stem
                if screen.startswith(self.local_scr_name_prefix):
                    screen = screen[len(self.local_scr_name_prefix) :]
                for string in strings:
                    regex = self.local_match_regex.format(screenshot=screen)
                    if re.search(regex, string[self.local_match_field]):
                        if screen in screens_and_strings:
                            screens_and_strings[screen].append(string['id'])
                        else:
                            screens_and_strings[screen] = [string['id']]
                        files_processed.append(file)

            logger.info(
                f'Found {len(screens_and_strings)} / {len(files)} matches for screenshots'
            )
            no_matches = [f for f in files if f not in files_processed]
            if no_matches:
                logger.warning(
                    f'No matches for screenshots:\n{[f.stem for f in no_matches]}'
                )

        if self.local_delete_all_auto_screens:
            screens = self.delete_Crowdin_screenshots(screens)
        elif self.local_detach_all_auto_screens:
            screens = self.detach_Crowdin_screenshots_tags(screens)

        processed_files = []
        for file in files:
            logger.info(f'> Processing: {file.stem}')
            if self.local_multi_tagging and self.process_screenshot_multi(
                file, strings, card_name_strings, screens
            ):
                processed_files.append(file)
            elif self.process_screenshot_single(file, screens_and_strings, screens):
                processed_files.append(file)
            else:
                logger.warning(f'Error or match for screenshot: {file.stem}')

        logger.info(f'Total processed files: {len(processed_files)} / {len(files)}')

    def run(self):
        if self.src_google_drive:
            return self.import_screens_from_crowdin()
        if self.src_local:
            return self.process_local_screenshots()


def main():
    init_logging()

    logger.info('')
    logger.info('--- Update source files on Crowdin script start ---')
    logger.info('')

    task = ImportScreenshots()

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
