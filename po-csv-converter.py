import re
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

    skipped_locales: list = None  # Locales to skip

    # If true, exports all languages into one multilingual CSV
    # and expects one multilingual CSV on import
    # If false, exports every language into its own bilingual CSV
    # and expects separate bilingual CSVs on import
    # ----
    # Warning: Expects the same structure on import
    multilingual_CSV: bool = True

    # TODO: Implement rules and splitting
    # Will split CSV file(s) based on the rules provided
    # Intended to bring some organization into projects with a single loc target
    # ----
    # Warning: Expects the same structure on import
    split_CSV_using_script_rules: bool = False
    splitting_rules = None

    # TODO: Implement conversion
    # ----
    # Warning: If True, expects ICU plurals on import, to be converted back to UE plurals
    convert_UE_plurals: bool = True
    stop_if_conversion_fails: bool = True

    po_encoding: str = 'utf-8-sig'  # PO file encoding
    csv_encoding: str = 'utf-8'  # CSV file encoding
    csv_delimiter: str = 'tab'  # tab (default), colon, semicolon

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

    csv_dir: str = 'Localization/CSV/'

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    # Internal
    _loc_targets: list[UELocTarget] = None
    _locale_file: str = 'Localization/{target}/{locale}/{target}.po'

    _csv_name: str = '{target}'
    _split_csv_name: str = '{target}.{split_name}'
    _bilingual_csv_name: str = '{name}.{locale}.{ext}'
    _multilingual_csv_name: str = '{name}.{ext}'

    _csv_extension: str = 'tsv'
    _content_path: Path = None
    _csv_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir)
        self._loc_targets = [
            UELocTarget(self._content_path.parent, target)
            for target in self.loc_targets
        ]

        if self.csv_delimiter != 'tab':
            self._csv_extension = 'csv'

        self._bilingual_csv_name.format(
            name='{name}', locale='{locale}', ext=self._csv_extension
        )
        self._multilingual_csv_name.format(name='{name}', ext=self._csv_extension)

    @staticmethod
    def parse_po_id(po_id: str):
        '''
        Takes a text ID from CSV and returns (target, namespace, key) for PO
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

    def source_PO_to_list(self, target: str) -> list:
        '''
        Load a PO file for the specified target
        and return a list of dicts containing all the data
        '''
        po_path = (
            self._content_path
            / f'Localization/{target}/{self.native_locale}/{target}.po'
        )

        logger.info(f'Processing {po_path}')

        po = polib.pofile(po_path, wrapwidth=0, encoding=self.po_encoding)

        if self.debug_ID_locale:
            debug_po = polib.pofile(
                self._content_path
                / f'Localization/{target}/{self.debug_ID_locale}/{target}.po',
                wrapwidth=0,
                encoding=self.po_encoding,
            )

        entries = []
        for e in po:
            key = e.msgctxt

            char_limit = re.search(r'InfoMetaData:\t"Char Limit" : "(\d+)"', e.comment)
            char_limit = char_limit[1] if char_limit is not None else ''

            context = [
                line.replace('InfoMetaData:\t', '').replace('\t', '    ')
                for line in e.comment.splitlines()
                if not line.startswith(self.comments_to_delete)
            ]

            add_context_line = ''

            if self.debug_ID_locale:
                debug_entry = debug_po.find(e.msgctxt, 'msgctxt')
                if debug_entry:
                    if debug_entry.msgstr != '':
                        add_context_line += f'Debug ID: {debug_entry.msgstr}'
                    else:
                        logger.warning(
                            'Debug ID empty for entry. '
                            'Debug ID locale might need to be reprocessed.'
                            f'\n{e.msgctxt}\n{e.msgstr}'
                        )
                        add_context_line += (
                            'Debug ID: #−−−−'  # Using minus to align with numbers
                        )
                else:
                    logger.warning(
                        'Debug ID entry not found for entry. '
                        'Debug ID locale might need to be '
                        'reexported from UE and then reprocessed.'
                        f'\n{e.msgctxt}\n{e.msgstr}'
                    )

            # TODO: Implement asset names extraction
            if self.extract_asset_names_to_context:
                pass

            # TODO: Implement repetition markers
            if self.add_repetition_markers:
                pass

            context += [add_context_line]

            # TODO: Implement comments
            if self.add_comments:
                pass

            context = '\n'.join(context)

            occurrences = '\n'.join(
                [(f'{e[0]}:{e[1]}' if e[1] != '' else f'{e[0]}') for e in e.occurrences]
            )

            d = {
                'id': e.msgctxt,
                'target': target,
                'key': key,
                'source_references': occurrences,
                'char_limit': char_limit,
                'context': context,
                'source': e.msgstr,
            }

            entries.append(d)

        for line in (
            [list(entries[0].keys())] + [list(entry.values()) for entry in entries]
        )[:20]:
            print(line)

    def x(self):
        pass

    def process_debug_ID_locale(self, po_file: str, starting_id: int) -> int:
        '''
        Process the PO file to insert #12345 IDs as 'translations'
        and add them to context
        '''

        logger.info(f'Processing {po_file}')

        current_id = starting_id

        po = polib.pofile(po_file, wrapwidth=0, encoding=self.encoding)

        logger.info(
            'Source file translation rate: {rate:.0%}'.format(
                rate=po.percent_translated() / 100
            )
        )

        #
        # Make indices in source reference zero-padded to fix the sorting
        #
        # And sort the PO by source reference to overcome the 'randomness' of the default
        # Unreal Engine GUIDs and get at least some logical grouping
        #
        if self.sort_po:
            for entry in po:
                ctxt = re.sub(
                    r'\d+', lambda match: match.group().zfill(3), entry.msgctxt
                )
                occurrences = []
                for oc in entry.occurrences:
                    # Zero-pad array indices and add keys with zero-padded numbers to occurences
                    oc0 = ''
                    if '### Key: ' not in oc[0]:
                        oc0 = (
                            re.sub(self.ind_regex, self.ind_repl, oc[0])
                            + f' ### Key: {ctxt}'
                        )
                    else:
                        oc0 = re.sub(self.ind_regex, self.ind_repl, oc[0])
                    occurrences.append((oc0, oc[1]))
                entry.occurrences = occurrences
                entry.comment = '\n'.join(
                    [
                        re.sub(self.ind_regex, self.ind_repl, c)
                        for c in entry.comment.splitlines(False)
                    ]
                )

            po.sort()

        if not self.clear_translations:
            # Check existing translations and log strings
            # that are translated but do not contain a debug ID
            odd_strings = [
                entry
                for entry in po.translated_entries()
                if not re.search(self._id_regex, entry.msgstr)
            ]

            if odd_strings:
                logger.warning(
                    f'Translated lines with no IDs in them ({len(odd_strings)}):'
                )
                for entry in odd_strings:
                    logger.warning(
                        "\n".join([entry.msgctxt, entry.msgid, entry.msgstr])
                    )

        logger.info(f'Starting ID: {current_id}')

        strings = [entry.msgid for entry in po]

        # Iterate over all entries to generate debug IDs, patch and add comments
        for entry in po:
            variables = []

            # If we want to retranslate all entries or if entry is not translated
            if self.clear_translations or not entry.translated():
                variables = [
                    str(var) for var in re.findall(self.var_regex, entry.msgid)
                ]

                # Generate and save the ID
                entry.msgstr = self.id_gen(current_id, self.id_length)

                # Add the variables back
                if len(variables) > 0:
                    entry.msgstr += " " + " ".join('<{0}>'.format(v) for v in variables)

                current_id += 1

            comments = entry.comment.splitlines(False)

            debug_ID = 'Debug ID:\t' + entry.msgstr

            asset_name = re.search(
                r'[^.]*(\.cpp|\.h)?', entry.occurrences[0][0].rpartition('/')[2]
            )

            if asset_name:
                asset_name = asset_name[0]
            debug_ID += f'\t\tAsset: {asset_name}'

            if strings.count(entry.msgid) > 1:
                debug_ID += '\t\t// ###Repetition###'

            for i in range(len(comments)):
                if comments[i].startswith('Debug ID:\t'):
                    comments[i] = debug_ID
                    break
            else:
                comments.append(debug_ID)

            comments += self.get_additional_comments(entry, self.comments_criteria)

            entry.comment = '\n'.join(comments)

        # TODO: Check for duplicate IDs across all targets
        ids = [entry.msgstr for entry in po.translated_entries()]
        if len(set(ids)) != len(ids):
            logger.error(
                'Duplicate #IDs spotted, please recompile the debug IDs from scratch (use CLEAR_TRANSLATIONS = True)'
            )

        logger.info(
            'Target file translation rate: {rate:.0%}'.format(
                rate=po.percent_translated() / 100
            )
        )
        logger.info(f'Last used ID: {current_id-1}')

        #
        # Save the file
        #
        po.save(po_file)
        logger.info(f'Saved target file: {po_file}')

        return current_id

    def process_locales(self):

        logger.info(f'Content path: {Path(self._content_path).absolute()}')

        starting_id = 1
        if not self.clear_translations and self.debug_ID_locale:
            starting_id = self.find_max_ID() + 1

        if not (self.debug_ID_locale or self.hash_locale):
            logger.error(
                'At least one of the locales must be specified (debug id or hash)'
            )
            return False

        hash_locales_processed = []
        debug_locales_processed = []
        errors = False

        for target in self.loc_targets:
            logger.info(f'Processing target: {target}')
            if self.debug_ID_locale:
                debug_id_PO = self._content_path / self._debug_id_file.format(
                    target=target
                )
                logger.info(f'Debug IDs PO file: {debug_id_PO}')
                if not debug_id_PO.exists():
                    logger.error(
                        f'Debug locale {self.debug_ID_locale} file not found: '
                        f'{debug_id_PO}'
                    )
                else:
                    starting_id = self.process_debug_ID_locale(debug_id_PO, starting_id)
                    debug_locales_processed.append(target)

        if self.debug_ID_locale and not len(debug_locales_processed) == len(
            self.loc_targets
        ):
            logger.error(
                'Not all debug locales have been processed: '
                f'{len(debug_locales_processed)} out of {len(self.loc_targets)}. '
                f'Loc targets: {self.loc_targets}. Debug locale: {self.debug_ID_locale}. '
                f'Processed debug locale targets: {hash_locales_processed}'
            )
            errors = True

        return errors


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

    task = UE_PO_CSV_Converter()

    task.read_config(Path(__file__).name, logger)

    result = task.source_PO_to_list('Goat2UIStringTables')

    logger.info('')
    logger.info('--- Process debug id/test/source, and hash locales script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Process the files if the file isn't imported
if __name__ == "__main__":
    main()
