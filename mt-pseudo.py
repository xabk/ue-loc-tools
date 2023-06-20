from pathlib import Path
from dataclasses import dataclass, field
from time import sleep
from loguru import logger
from timeit import default_timer as timer
import re
import shutil

from libraries import polib
from libraries.crowdin import UECrowdinClient
from libraries.utilities import LocTask, init_logging

import importlib

dl_task = importlib.import_module("build-and-download")


@dataclass
class MTPseudo(LocTask):
    # TODO: Function to set up MT project on Crowdin or a separate script for this?

    # Declare Crowdin parameters to load them from config
    token: str = None
    organization: str = None
    project_id: int = None

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented

    loc_targets: list = field(
        default_factory=lambda: ['MTTest']
    )  # Localization targets, empty = process all targets

    # TODO: Empty = all languages for project on Crowdin
    # { Crowdin locale : Unreal culture }
    # E.g., { zh-CN : zh-Hans }
    languages: dict = field(
        default_factory=lambda: {
            # convert this to a dict with empty values
            'fr': 'fr',
            'it': 'it',
            'de': 'de',
            'es': 'es',
            'zh-CN': 'zh-Hans',
            'zh-TW': 'zh-Hant',
            'ja': 'ja',
            'ko': 'ko',
            'pl': 'pl',
            'pt-BR': 'pt-BR',
            'ru': 'ru',
            'tr': 'tr',
        }
    )

    locales_to_skip: list = field(
        default_factory=lambda: [
            'io',
            'ia-001',
            'en-SG',
            'en-ZA',
        ]
    )

    engine_id: int or None = 1

    file_format: str = (
        'gettext_unreal'  # gettext_unreal to use the Unreal PO parser on Crowdin
    )

    src_locale: str = 'en-ZA'
    longest_locale: str = 'en-AE'

    export_pattern: str = '/{target}/%locale%/{target}.po'

    po_encoding: str = 'utf-8-sig'

    prefix: str = '‹'
    suffix: str = '›'

    filler: str = '~'

    var_regex: str = r'{[^}]*}'
    tags_regex: str = r'<[^>]*>'

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    temp_dir: str = 'Localization/~Temp/MT+Pseudo/'

    _fname: str = 'Localization/{target}/{locale}/{target}.po'
    _temp_fname: str = '{target}/{locale}/{target}.po'

    _languages: dict[str, str] = None

    _content_path: Path = None
    _temp_path: Path = None

    _crowdin = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir).resolve()
        self._temp_path = (self._content_path / self.temp_dir).resolve()
        self._languages = {}
        for crowd_l, ue_l in self.languages.items():
            self._languages[crowd_l] = ue_l if ue_l else crowd_l
        self._crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

    def add_source_file(self, target: str) -> int or dict:
        fpath = self._content_path / self._fname.format(
            target=target, locale=self.src_locale
        )
        logger.info(f'Uploading file: {fpath}. Format: {self.file_format}')
        r = self._crowdin.add_file(
            fpath,
            type=self.file_format,
            export_pattern=self.export_pattern.format(target=target),
        )
        return r

    def add_source_files(self) -> dict[str, int]:
        # TODO: Check the files on Crowdin, update existing files?
        logger.info(f'Content path: {self._content_path}')

        targets_processed = {}

        for target in self.loc_targets:
            r = self.add_source_file(target)

            if isinstance(r, int):
                targets_processed[target] = r
                logger.info(f'File for {target} added.')
            else:
                logger.error(
                    f'Something went wrong. Here\'s the last response from Crowdin: {r}'
                )

        if len(targets_processed) == len(self.loc_targets):
            logger.info(
                f'SUCCESS: Targets processed ({len(targets_processed)}): {targets_processed}'
            )
            return targets_processed

        return targets_processed

    def update_source_file(self, target: str) -> int or dict:
        fpath = self._content_path / self._fname.format(
            target=target, locale=self.src_locale
        )
        logger.info(f'Updating file: {fpath}.')
        r = self._crowdin.update_file(fpath)
        return r

    def update_source_files(self) -> dict[str, int]:
        # TODO: Check the files on Crowdin, update existing files?
        logger.info(f'Content path: {self._content_path}')

        targets_processed = {}

        for target in self.loc_targets:
            r = self.update_source_file(target)

            if isinstance(r, int):
                targets_processed[target] = r
                logger.info(f'File for {target} updated.')
            else:
                logger.error(
                    f'Something went wrong. Here\'s the last response from Crowdin: {r}'
                )

        if len(targets_processed) == len(self.loc_targets):
            logger.info(
                f'SUCCESS: Targets processed ({len(targets_processed)}): {targets_processed}'
            )
            return targets_processed

        return targets_processed

    def pretranslate_file(self, file_id: int):
        response = self._crowdin.translations.apply_pre_translation(
            projectId=self.project_id,
            languageIds=list(self._languages.keys()),
            fileIds=[file_id],
            autoApproveOption='all',
        )

        if not 'data' in response:
            return response

        pre_id = response['data']['identifier']

        response = self._crowdin.translations.pre_translation_status(
            self.project_id, pre_id
        )

        while response['data']['status'] != 'finished':
            logger.info(
                f"Progress: {response['data']['progress']}. "
                f"ETA: {response['data']['eta']}"
            )
            sleep(10)
            response = self._crowdin.translations.pre_translation_status(
                self.project_id, pre_id
            )

        return 0

    def pretranslate_files(self, files: dict[str, int]):
        logger.info(f'Pretranslating {len(files)} files...')
        files_processed = {}

        for target, id in files.items():
            logger.info(f'Pretranslating {target} / {id}')
            r = self.pretranslate_file(id)
            if r == 0:
                files_processed[target] = id
                logger.info(f'File for {target} pretranslated.')
            else:
                logger.error(
                    f'Something went wrong with {target}. '
                    f'Here\'s the last response from Crowdin: {r}'
                )

        if len(files_processed) == len(files):
            logger.info(
                f'SUCCESS: Targets pretranslated ({len(files_processed)}): {files_processed}'
            )
            return files_processed

        return files_processed

    def mt_file(self, file_id: int):
        # logger.info(crowdin.machine_translations.list_mts())
        supported_languages = [
            mt['data']['supportedLanguageIds']
            for mt in self._crowdin.machine_translations.list_mts()['data']
            if mt['data']['id'] == self.engine_id
        ][0]

        languageIds = [id for id in self._languages.keys() if id in supported_languages]

        if len(languageIds) < len(self._languages):
            logger.warning(
                f'Not all configured languages are supported by the MT engine. '
                f'Supported: {languageIds}'
            )

        response = self._crowdin.translations.apply_pre_translation(
            projectId=self.project_id,
            languageIds=languageIds,
            fileIds=[file_id],
            method='mt',
            engineId=self.engine_id,
        )

        if not 'data' in response:
            return response

        pre_id = response['data']['identifier']

        response = self._crowdin.translations.pre_translation_status(
            self.project_id, pre_id
        )

        while response['data']['status'] != 'finished':
            logger.info(
                f"Progress: {response['data']['progress']}. "
                f"ETA: {response['data']['eta']}"
            )
            sleep(10)
            response = self._crowdin.translations.pre_translation_status(
                self.project_id, pre_id
            )

        return 0

    def mt_files(self, files: dict[str, int]):
        logger.info(f'MT {len(files)} files...')
        files_processed = {}

        for target, id in files.items():
            logger.info(f'Applying MT for {target} / {id}...')
            r = self.mt_file(id)
            if r == 0:
                files_processed[target] = id
                logger.info(f'File for {target} machine translated.')
            else:
                logger.error(
                    f'Something went wrong with {target}. '
                    f'Here\'s the last response from Crowdin: {r}'
                )

        if len(files_processed) == len(files):
            logger.info(
                f'SUCCESS: Targets pretranslated ({len(files_processed)}): {files_processed}'
            )
            return files_processed

        return files_processed

    def approve_language(self, lang_id: str):
        r = self._crowdin.string_translations.with_fetch_all().list_language_translations(
            self.project_id,
            lang_id,
            croql='count of approvals = 0 and provider is mt',
        )

        if not 'data' in r:
            return r

        translations = [s['data']['translationId'] for s in r['data']]

        logger.info(f'Approving {len(translations)} translations...')

        for i, id in enumerate(translations):
            self._crowdin.string_translations.add_approval(self.project_id, id)
            if (i + 1) % 50 == 0:
                logger.info('Approved 50 translations...')

    def approve_languages(self):
        languages = self._languages.keys()
        logger.info(f'Approving {len(languages)} languages...')
        langs_processed = {}

        for lang in languages:
            logger.info(f'Approving {lang}...')
            r = self.approve_language(lang)
            if r == 0:
                langs_processed[lang] = id
                logger.info(f'Language {lang} approved.')
            else:
                logger.error(
                    f'Something went wrong with {lang}. '
                    f'Here\'s the last response from Crowdin: {r}'
                )

        if len(langs_processed) == len(languages):
            logger.success(
                f'Languages approved ({len(langs_processed)}): {langs_processed}'
            )
            return langs_processed

        return langs_processed

    def download_transalted_files(self):
        task = dl_task.BuildAndDownloadTranslations(
            token=self.token,
            organization=self.organization,
            project_id=self.project_id,
            loc_targets=self.loc_targets,
            content_dir=self.content_dir,
            temp_dir=self.temp_dir,
        )
        task.post_update()
        task.culture_mappings.update(self.languages)
        print(task)

        task.build_and_download()

        task.unzip_file()

        return task._temp_path

    def copy_downloaded_files_to_content(self):
        task = dl_task.BuildAndDownloadTranslations(
            token=self.token,
            organization=self.organization,
            project_id=self.project_id,
            loc_targets=self.loc_targets,
            content_dir=self.content_dir,
        )
        task.post_update()
        task.culture_mappings.update(self.languages)
        print(task)

        return task.process_loc_targets()

    def pseudo_mark_file(self, file_path: Path):
        po = polib.pofile(file_path, encoding=self.po_encoding, wrapwidth=0)
        for entry in po:
            if not entry.msgstr.startswith(self.prefix):
                entry.msgstr = self.prefix + entry.msgstr
            if not entry.msgstr.endswith(self.suffix):
                entry.msgstr = entry.msgstr + self.suffix
        po.save()

    def pseudo_mark_target(self, target: str, cultures: list[str] = None):
        logger.info(f'Adding pseudo markers to target: {target}')
        if not cultures:
            # Find all eligible locales in the target folder
            cultures = [
                f.name
                for f in (self._temp_path / target).glob('*')
                if f.is_dir()
                and f.name != self.src_locale
                and f.name != self.longest_locale
                and f.name not in self.locales_to_skip
            ]

        logger.info(f'Cultures to process: {cultures}')

        cultures_processed = []

        for culture in cultures:
            file_path = self._temp_path / self._temp_fname.format(
                target=target, locale=culture
            )

            if not file_path.exists():
                logger.error(f'Missing PO files for {target}/{culture}: {file_path}')
                continue

            self.pseudo_mark_file(file_path=file_path)

            cultures_processed.append(culture)

        if len(cultures_processed) == len(cultures):
            logger.success('Processed all cultures.')
            return True

        if len(cultures_processed) != 0:
            logger.info(
                f'Processed {len(cultures_processed)}/{len(cultures)} cultures:\n'
                f'{cultures_processed}'
            )
        else:
            logger.error('No cultures were processed.')

        return False

    def pseudo_mark_targets(
        self, targets: list[str] = None, cultures: list[str] = None
    ):
        if not targets:
            targets = self.loc_targets

        logger.info(f'Adding pseudo markers to targets: {targets}')

        targets_processed = []

        for target in targets:
            if not cultures:
                # Find all eligible locales in the target folder
                cultures = [
                    f.name
                    for f in (self._temp_path / target).glob('*')
                    if f.is_dir()
                    and f.name != self.src_locale
                    and f.name != self.longest_locale
                    and f.name not in self.locales_to_skip
                ]

            if self.pseudo_mark_target(target, cultures):
                targets_processed.append(target)

        if len(targets_processed) == len(targets):
            logger.success('Processed all targets.')
            return True

        if len(targets_processed) != 0:
            logger.info(
                f'Processed {len(targets_processed)}/{len(targets)} targets:\n'
                f'{targets_processed}'
            )
        else:
            logger.error('No targets were processed.')

        return False

    def create_longest(self, base: str, target: str):
        if len(base) >= len(target):
            result = base
            if not result.startswith(self.prefix):
                result = self.prefix + result
            if not result.endswith(self.suffix):
                result = result + self.suffix
            return result

        length = len(target)

        result, _ = re.subn(self.var_regex, '*', target)
        result, _ = re.subn(self.tags_regex, '=', result)

        length = length - len(result) - 2

        result = base + '| ' + result[len(base) - length :].strip()
        if not result.startswith(self.prefix):
            result = self.prefix + result
        if not result.endswith(self.suffix):
            result = result + self.suffix

        return result

    def create_longest_locale_for_target(self, target: str, cultures: list[str] = None):
        #
        # en-SA by default
        #
        # Load longest locale PO in `Content/Localization/Target/`
        # Populate translations and lengths dicts
        # Go over the other locale PO files in `Temp/Target`
        # If translation longer than current, add to the translations dict, update length
        # Load debug ID locale PO
        # Extend English text with something to match the length of the longest translation
        #  - filler, various locale symbols, debug IDs, etc.?
        #  - take into account spaces in longest translation (to avoid single-word filler)
        # Save as new 'longest' locale
        logger.info(f'Creating longest locale: {target}')

        if not cultures:
            # Find all eligible locales in the target folder
            cultures = [
                f.name
                for f in (self._temp_path / target).glob('*')
                if f.is_dir()
                and f.name != self.src_locale
                and f.name != self.longest_locale
                and f.name not in self.locales_to_skip
            ]

        logger.info(f'Cultures to process: {cultures}')

        longest_path = self._temp_path / self._temp_fname.format(
            target=target, locale=self.longest_locale
        )

        longest_po = None
        longest_dict = {}

        cultures_processed = []

        for culture in cultures:
            logger.info(f'Processing {culture}...')
            file_path = self._temp_path / self._temp_fname.format(
                target=target, locale=culture
            )

            if not file_path.exists():
                logger.error(f'Missing PO files for {target}/{culture}: {file_path}')
                continue

            po = polib.pofile(file_path, encoding=self.po_encoding, wrapwidth=0)

            if not longest_dict:
                longest_po = polib.pofile(
                    file_path, encoding=self.po_encoding, wrapwidth=0
                )
                longest_dict = {e.msgctxt: e for e in longest_po}
                continue

            po_dict = {e.msgctxt: e for e in po}

            for key, entry in longest_dict.items():
                if key in po_dict:
                    if len(po_dict[key].msgstr) > len(entry.msgstr):
                        entry.msgstr = po_dict[key].msgstr

            # self.pseudo_mark_file(file_path=file_path)

            cultures_processed.append(culture)

        if len(cultures_processed) == len(cultures):
            logger.success('Processed all cultures.')
        elif len(cultures_processed) != 0:
            logger.info(
                f'Processed {len(cultures_processed)}/{len(cultures)} cultures:\n'
                f'{cultures_processed}'
            )
        else:
            logger.error('No cultures were processed.')

        for entry in longest_dict.values():
            entry.msgstr = self.create_longest(entry.msgid, entry.msgstr)

        if not longest_path.parent.exists():
            longest_path.parent.mkdir(parents=True)

        longest_po.save(longest_path)

        return True

    def create_longest_locale_for_targets(
        self, targets: list[str] = None, cultures: list[str] = None
    ):
        if not targets:
            targets = self.loc_targets

        logger.info(f'Adding pseudo markers to targets: {targets}')

        targets_processed = []

        for target in targets:
            if not cultures:
                # Find all eligible locales in the target folder
                cultures = [
                    f.name
                    for f in (self._temp_path / target).glob('*')
                    if f.is_dir()
                    and f.name != self.src_locale
                    and f.name != self.longest_locale
                    and f.name not in self.locales_to_skip
                ]

            if self.create_longest_locale_for_target(target, cultures):
                targets_processed.append(target)

        if len(targets_processed) == len(targets):
            logger.success('Processed all targets.')
            return True

        if len(targets_processed) != 0:
            logger.info(
                f'Processed {len(targets_processed)}/{len(targets)} targets:\n'
                f'{targets_processed}'
            )
        else:
            logger.error('No targets were processed.')

        return False

    def create_longest_locale_pack(self, targets: list[str] = None):
        if not targets:
            targets = self.loc_targets

        path = self._temp_path / 'Longest_Pack'
        if not path.exists():
            path.mkdir(parents=True)

        for target in targets:
            src = self._temp_path / self._temp_fname.format(
                target=target, locale=self.longest_locale
            )
            dst = path / self._temp_fname.format(
                target=target, locale=self.longest_locale
            )
            if not dst.parent.exists():
                dst.parent.mkdir(parents=True)

            shutil.copy(src, dst.parent)

        return path

    def create_monster_target(self):
        pass


def main():

    all_tasks_start = timer()

    init_logging(logger)

    logger.info('')
    logger.info('--- Add source files on Crowdin script start ---')
    logger.info('')

    task = MTPseudo()

    task.read_config(Path(__file__).name, logger)

    files = task.add_source_files()

    # files = task.update_source_files()

    print(files)

    # files = {'MTTest': 1318}

    task.pretranslate_files(files)

    task.mt_files(files)

    # task.approve_languages()

    task.download_transalted_files()

    # task.pseudo_mark_targets()

    # task.copy_downloaded_files_to_content()

    task.create_longest_locale_for_targets()

    task.create_longest_locale_pack()

    elapsed = timer() - all_tasks_start

    logger.info(f'Time elapsed: {elapsed:.2f} seconds')

    logger.info('')
    logger.info('--- Add source files on Crowdin script end ---')
    logger.info('')

    if 0:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
