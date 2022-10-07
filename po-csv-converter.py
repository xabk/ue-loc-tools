import re
import csv
import copy
from loguru import logger
from pathlib import Path
from dataclasses import dataclass, field

from libraries import (
    polib,  # Modified polib: _POFileParser.handle_oc only splits references by ', '
)
from libraries.utilities import LocTask
from libraries.uetools import UELocTarget

# -------------------------------------------------------------------------------------
# Defaults - These can be edited, only used if not overridden in configs
# (needed to make the script work standalone)
#
# Priority:
# 1. Script parameters in task list section of base.config.yaml (if task list provided)
# 2. Global params from base.config.yaml (if config file found and parameters found)
# 3. Defaults below (if no parameters found in config or no config found)
@dataclass
class UE_PO_CSV_Converter(LocTask):
    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Goat2StringTables', 'Goat2UIStringTables']
    )  # Localization targets, empty = process all targets

    # Source locale
    # Will be used to get source text
    native_locale: str = 'en'

    # Debug ID locale
    # Will be skipped as a language but used to add Debug IDs to context
    debug_ID_locale: str = 'io'

    skipped_locales: list = field(
        default_factory=lambda: ['io', 'ia-001']
    )  # Locales to skip

    # Order of locales if you want
    # Locales not listed here will go after the ones in the list,
    # in the order they appear in DefaultGame config
    locales_order: list = field(
        default_factory=lambda: [
            'fr',
            'it',
            'de',
            'es',
            'zh-Hans',
            'zh-Hant',
            'ja',
            'ko',
        ]
    )

    sort_strings: bool = True

    CSV_fields: list = field(
        default_factory=lambda: [
            'id',
            'char_limit',
            'crowdin_context',
        ]
    )  # Fields to export to CSV, translations added automatically

    # If true, exports all languages into one multilingual CSV
    # and expects one multilingual CSV on import
    # If false, exports every language into its own bilingual CSV
    # and expects separate bilingual CSVs on import
    # ----
    # Warning: Expects the same structure on import
    multilingual_CSV: bool = False

    # TODO: Implement rules and splitting
    # Will split CSV file(s) based on the rules provided
    # Intended to bring some organization into projects with a single loc target
    # ----
    # Warning: Expects the same structure on import
    split_CSV_using_script_rules: bool = False
    splitting_rules: list = None

    # TODO: Implement conversion
    # ----
    # Warning: If True, expects ICU plurals on import, to be converted back to UE plurals
    convert_UE_plurals: bool = True
    stop_if_conversion_fails: bool = True

    po_encoding: str = 'utf-8-sig'  # PO file encoding
    csv_encoding: str = 'utf-8'  # CSV file encoding
    csv_delimiter: str = '\t'  # \t by default, can be , or ;

    # Remove comments that start with these strings
    # Default list removes what's already extracted into separate columns
    comments_to_delete: list = field(
        default_factory=lambda: (
            'Key:\t',
            'SourceLocation:\t',
            'InfoMetaData:\t"Char Limit"',
        )
    )

    # Should we add repetition markers?
    add_repetition_markers: bool = True

    # Should we extract asset names from source references?
    extract_asset_names_to_context: bool = True

    # Should we add comments?
    add_comments: bool = True
    comments_criteria: list = field(
        # list of rules, each rule is a list: [property to check, regex, comment to add]
        #  - property to check: msgid, msgctx, etc. See libraries/polib
        default_factory=lambda: [
            [  # Adding hints for strings with plurals
                'source',
                r'}\|plural\(',
                "Please adapt to your language plural rules. We only support "
                "keywords: zero, one, two, few, many, other.\n"
                "Use Alt + C on Crowdin to create a skeleton adapted "
                "to your language grammar.\n"
                "Translate only white text in curly braces. Test using the form "
                "below the Preview box.\n"
                "Check what keywords stand for here: "
                "http://www.unicode.org/cldr/charts/29/supplemental/language_plural_rules.html.",
            ]
        ]
    )

    multilingual_csv_name: str = 'Localization/{name}.{ext}'
    bilingual_csv_name: str = 'Localization/{target}/{locale}/{target}.{locale}.{ext}'

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    # Internal
    # { 'target' -> { 'ID' : {...string data...} } }
    _strings: dict[str:dict] = None

    _loc_targets: list[UELocTarget] = None
    _locale_file: str = 'Localization/{target}/{locale}/{target}.po'

    _multilingual_csv_name: str = None
    _bilingual_csv_name: str = None

    _csv_extension: str = 'tsv'
    _content_path: Path = None
    _csv_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir)

        self._loc_targets = [
            UELocTarget(self._content_path, target)  # .parent, target)
            for target in self.loc_targets
        ]

        self._strings = {}

        if self.csv_delimiter != '\t':
            self._csv_extension = 'csv'

        self._multilingual_csv_name = self.multilingual_csv_name.format(
            name='{target}', ext=self._csv_extension
        )

        self._bilingual_csv_name = self.bilingual_csv_name.format(
            target='{target}', locale='{locale}', ext=self._csv_extension
        )

    @staticmethod
    def parse_po_id(po_id: str):
        '''
        Takes a text ID from CSV and returns (namespace, key) for PO
        '''

        comma_index = None
        is_escaped = False

        for i in range(len(po_id)):
            if is_escaped:
                is_escaped = False
                continue

            if po_id[i] == ',':
                comma_index = i
                break

            if po_id[i] == '\\':
                is_escaped = True
                continue

        if comma_index is None:
            namespace = po_id
            key = ''
        else:
            namespace = po_id[:i]
            key = po_id[i + 1 :]

        return (namespace, key)

    def _create_string_entry(
        self,
        e: polib.POEntry,
        target: str,
        debug_id: str,
        reps: int,
    ) -> dict:
        (namespace, key) = self.parse_po_id(e.msgctxt)

        char_limit = re.search(r'InfoMetaData:\t"Char Limit" : "(\d+)"', e.comment)
        char_limit = char_limit[1] if char_limit is not None else ''

        context = [
            re.sub(
                r'^InfoMetaData:\t"(.*?)" : "(.*?)"$',
                r'\1: \2',
                line,
            ).replace('\t', '    ')
            for line in e.comment.splitlines()
            if not line.startswith(self.comments_to_delete)
            and not re.match(r'^InfoMetaData:\t"(.*?)" : ""$', line)
        ]

        asset_name = re.search(
            r'[^.]*(\.cpp|\.h)?', e.occurrences[0][0].rpartition('/')[2]
        )
        if asset_name:
            asset_name = asset_name[0]

        # TODO: Implement comments
        if self.add_comments:
            pass

        context = '\n'.join(context)

        occurrences = '\n'.join(
            [(f'{e[0]}:{e[1]}' if e[1] != '' else f'{e[0]}') for e in e.occurrences]
        )

        string = {
            'id': f'{target}/{e.msgctxt}',
            'msgctxt': e.msgctxt,
            'target': target,
            'namespace': namespace,
            'key': key,
            'debug_id': debug_id,
            'asset_name': asset_name,
            'repetition': reps,
            'source_references': occurrences,
            'char_limit': char_limit,
            'context': context,
            'crowdin_context': '\n'.join(
                filter(
                    None,
                    [
                        context,
                        ' / '.join(
                            filter(
                                None,
                                [
                                    f'Debug ID: {debug_id}',
                                    f'Asset: {asset_name}',
                                    reps,
                                ],
                            )
                        ),
                        occurrences,
                    ],
                )
            ),
            self.native_locale: e.msgstr,
        }

        return string

    def load_source_PO(self, target: str) -> int:
        '''
        Load a PO file for the specified target
        and return a list of dicts containing all the data
        '''
        po_path = self._content_path / self._locale_file.format(
            target=target, locale=self.native_locale
        )

        logger.info(f'Processing {po_path}')

        src_po = polib.pofile(po_path, wrapwidth=0, encoding=self.po_encoding)

        # TODO: Patch occurences and/or sorting: PO or list?

        if self.debug_ID_locale:
            debug_po = polib.pofile(
                self._content_path
                / self._locale_file.format(target=target, locale=self.debug_ID_locale),
                wrapwidth=0,
                encoding=self.po_encoding,
            )

        entries = {}

        strings = [e.msgstr for e in src_po]

        for entry in src_po:
            debug_id = ''
            if self.debug_ID_locale:
                debug_entry = debug_po.find(entry.msgctxt, 'msgctxt')
                if debug_entry:
                    if debug_entry.msgstr != '':
                        debug_id = debug_entry.msgstr
                    else:
                        logger.warning(
                            'Debug ID empty for entry. '
                            'Debug ID locale might need to be reprocessed.'
                            f'\n{entry.msgctxt}\n{entry.msgstr}'
                        )
                        debug_id = 'Warning: Entry found but debug ID empty'
                else:
                    logger.warning(
                        'Debug ID entry not found for entry. '
                        'Debug ID locale might need to be '
                        'reexported from UE and then reprocessed.'
                        f'\n{entry.msgctxt}\n{entry.msgstr}'
                    )
                    debug_id = 'Warning: Entry not found in debug ID locale'

            repetitions = ''
            if (count := strings.count(entry.msgstr)) > 1:
                repetitions = f'Repetition: {count}'

            string = self._create_string_entry(entry, target, debug_id, repetitions)
            entries[string['msgctxt']] = string

        # TODO: Implement repetition markers within the target or all targets?

        self._strings[target] = entries

        return 0

    def _load_translated_PO(self, target: str, locale: str) -> int:
        entries = {}

        po_path = self._content_path / self._locale_file.format(
            target=target, locale=locale
        )

        logger.info(f'Processing {po_path}')

        po = polib.pofile(po_path, wrapwidth=0, encoding=self.po_encoding)

        for entry in self._strings[target].values():
            translation = ''
            msgctxt = entry['msgctxt']
            translated_entry = po.find(msgctxt, 'msgctxt')
            if translated_entry:
                if translated_entry.msgstr != '':
                    translation = translated_entry.msgstr
                else:
                    logger.warning(
                        f'{target} -> {locale}: No translation for entry: '
                        f'\n{msgctxt}\n{entry[self.native_locale]}'
                    )
            else:
                logger.warning(
                    f'{target} -> {locale}: Entry not found in translated PO: '
                    f'\n{msgctxt}\n{entry[self.native_locale]}'
                )

            entries[msgctxt] = copy.copy(entry)
            entries[msgctxt][locale] = translation

        self._strings[target] = copy.deepcopy(entries)

        return 0

    def load_POs_for_all_targets(self) -> int:
        for target in self._loc_targets:
            locales = target.get_current_locales()
            self.load_source_PO(target.name)
            for locale in locales:
                if locale in self.skipped_locales or locale == self.native_locale:
                    continue
                self._load_translated_PO(target.name, locale)

    def _load_translated_CSV(self, target: str, locale: str) -> int:
        csv_name = self._bilingual_csv_name.format(target=target, locale=locale)
        csv_name = self._content_path / csv_name
        logger.info(f'Loading CSV for {target}/{locale} from:\n{csv_name}')
        translations = {}
        with open(csv_name, 'r', encoding=self.csv_encoding, newline='') as f:
            csv_file = csv.DictReader(f, delimiter=self.csv_delimiter)
            for row in csv_file:
                translations[row['id']] = row[locale]
        entries = {}
        for key in self._strings[target]:
            string = copy.copy(self._strings[target][key])
            string[locale] = translations.pop(string['id'], None)
            if string[locale] is None:
                logger.warning(f'No {locale} translations found for {string["id"]}')
                string[locale] = ''

            entries[key] = string

        self._strings[target] = entries

        if len(translations) > 0:
            logger.warning(
                f'Extra translations found in {locale} CSV ({len(translations)}:\n'
                f'{translations}'
            )

        return 0

    def load_all_translated_CSVs(self):
        for target in self._loc_targets:
            for locale in target.get_current_locales():
                if locale in self.skipped_locales or locale == self.native_locale:
                    continue
                self._load_translated_CSV(target.name, locale)

    def _save_translated_PO(self, target: str, locale: str):
        po_path = self._content_path / self._locale_file.format(
            target=target, locale=locale
        )

        logger.info(f'Processing {target}/{locale}. PO:\n{po_path}')

        po = polib.pofile(po_path, wrapwidth=0, encoding=self.po_encoding)

        translations = copy.deepcopy(self._strings[target])

        translations_updated = 0

        for entry in po:
            translation = translations.pop(entry.msgctxt, None)

            if translation is None:
                logger.warning(
                    f'No {locale} translations found for {entry.msgctxt}:\n'
                    f'{entry.msgid}'
                )
                entry.msgstr = ''
                continue

            if entry.msgstr == translation[locale]:
                continue

            # TODO: Check for changed source / stale translations?
            entry.msgstr = translation[locale]
            translations_updated += 1

        if len(translations) > 0:
            logger.warning(
                f'Extra translations found for {locale} ({len(translations)}:\n'
                f'{translations}'
            )

        po.save(po_path)

        logger.info(
            f'Updated {target}/{locale} translations: {translations_updated}/{len(po)}. '
            'PO saved.'
        )

        return 0

    def save_all_translated_POs(self):
        for target in self._loc_targets:
            for locale in target.get_current_locales():
                if locale in self.skipped_locales or locale == self.native_locale:
                    continue
                self._save_translated_PO(target.name, locale)

    def _save_to_CSV(
        self,
        filename: str,
        strings: dict[str:dict],
        fields: list,
    ):
        with open(filename, 'w', newline='', encoding=self.csv_encoding) as f:
            csv_file = csv.writer(
                f, delimiter=self.csv_delimiter, quoting=csv.QUOTE_MINIMAL
            )

            if len(strings) < 1:
                logger.warning(f'No strings supplied to CSV: {filename}')
                return 0

            missing_fields = [
                f for f in fields if f not in next(iter(strings.values())).keys()
            ]
            if missing_fields:
                logger.error(f'Fields not found among strings fields: {missing_fields}')
                return 1

            csv_file.writerow(fields)  # Field names
            for string in strings.values():
                csv_file.writerow([string[f] for f in fields])

    def save_bilingual_CSVs_per_target(self):
        logger.info(
            f'Saving CSVs for targets ({len(self._loc_targets)}): '
            f'{[target.name for target in self._loc_targets]}.'
        )
        for target in self._loc_targets:
            locales = sorted(target.get_current_locales())
            locales = [
                locale
                for locale in locales
                if locale not in self.skipped_locales and locale != self.native_locale
            ]
            if self.locales_order:
                locales = [
                    locale for locale in self.locales_order if locale in locales
                ] + sorted(
                    [locale for locale in locales if locale not in self.locales_order]
                )
            logger.info(
                f'Saving CSVs for target: {target.name}. '
                f'Locales ({len(locales)}): {locales}.'
            )
            for locale in locales:
                csv_name = self._bilingual_csv_name.format(
                    target=target.name, locale=locale
                )
                csv_name = self._content_path / csv_name
                logger.info(f'Saving CSV for {target.name}/{locale} to:\n{csv_name}')
                self._save_to_CSV(
                    csv_name,
                    self._strings[target.name],
                    self.CSV_fields + [self.native_locale, locale],
                )
                logger.info(f'{target.name}/{locale} saved!')


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

    logger.info('')
    logger.info('--- Converting PO files into CSV file(s) ---')
    logger.info('')

    # --- Load source and translated POs and save to CSVs ---

    # task_PO_to_CSVs = UE_PO_CSV_Converter()

    # task_PO_to_CSVs.read_config(Path(__file__).name, logger)

    # result = task_PO_to_CSVs.load_POs_for_all_targets()

    # for key, value in list(
    #     task_PO_to_CSVs._strings[task_PO_to_CSVs._loc_targets[1].name].items()
    # )[:5]:
    #     print(f'{key} -> {value}')
    # result = task_PO_to_CSVs.save_bilingual_CSVs_per_target()

    # --- Load source POs and load translations from CSVs ---

    task2 = UE_PO_CSV_Converter()

    task2.read_config(Path(__file__).name, logger)

    result = task2.load_source_PO(task2._loc_targets[1].name)
    result = task2.load_source_PO(task2._loc_targets[0].name)
    for line in list(task2._strings[task2._loc_targets[1].name])[:2]:
        print(line, '->', task2._strings[task2._loc_targets[1].name][line])

    result = task2.load_all_translated_CSVs()
    for line in list(task2._strings[task2._loc_targets[1].name])[:2]:
        print(line, '->', task2._strings[task2._loc_targets[1].name][line])

    # --- Save to translated POs ---

    result = task2._save_translated_PO(task2._loc_targets[1].name, 'de')

    logger.info('')
    logger.info('--- Process debug id/test/source, and hash locales script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Process the files if the file isn't imported
if __name__ == "__main__":
    main()
