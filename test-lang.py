import re
from loguru import logger
from pathlib import Path
from dataclasses import dataclass, field

from libraries import (
    polib,  # Modified polib: _POFileParser.handle_oc only splits references by ', '
)
from libraries.utilities import LocTask

# -------------------------------------------------------------------------------------
# Defaults - These can be edited, only used if not overridden in configs
# (needed to make the script work standalone)
#
# Priority:
# 1. Script parameters in task list section of base.config.yaml (if task list provided)
# 2. Global params from base.config.yaml (if config file found and parameters found)
# 3. Defaults below (if no parameters found in config or no config found)
@dataclass
class ProcessTestAndHashLocales(LocTask):
    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    # Debug ID/test locale is also a good source locale:
    # it's sorted, with debug IDs, repetition markers, asset names, and comments
    debug_ID_locale: str = 'io'
    hash_locale: str = 'ia-001'

    # Hash locale parameters
    hash_prefix: str = '# '  # Prefix for each string in hash locale
    hash_suffix: str = ' ~'  # Suffix for each string in hash locale

    clear_translations: bool = False  # Start over? E.g., if ID length changed
    id_length: int = 4  # Num of digits in ID (#0001), start over if changed

    encoding: str = 'utf-8-sig'  # PO file encoding
    sort_po: bool = True  # Sort the file by source reference?

    # Regex to match variables that we want to keep in 'translation'
    # TODO: Add support for UE/ICU syntax (plural, genders, etc.)
    var_regex: str = (
        r'{[^}\[<]+}|<[^/>]+/>'  # Looking for {variables} and <empty tags ... />
    )

    comments_criteria: list = field(
        # list of rules, each rule is a list: [property to check, regex, comment to add]
        #  - property to check: msgid, msgctx, etc. See libraries/polib
        default_factory=lambda: [
            [  # Adding hints for strings with plurals
                'msgid',
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

    # Regex to match indices and make them zero-padded to fix the sorting
    ind_regex: str = r'([\[\(])([^\]\)]+)([\]\)])'  # Anything in () or []

    # Regex pattern to match IDs
    id_regex_pattern: str = r'#(\d{{{id_length}}})'

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    # Actual regex based on id_length
    _id_regex: str = None
    _content_path: Path = None
    # PO files, relative to Content directory
    _debug_id_file = 'Localization/{target}/{locale}/{target}.po'
    _hash_file = 'Localization/{target}/{locale}/{target}.po'

    def post_update(self):
        super().post_update()
        self._id_regex = self.id_regex_pattern.format(id_length=self.id_length)
        self._content_path = Path(self.content_dir)
        if self.debug_ID_locale:
            self._debug_id_file = self._debug_id_file.format(
                target='{target}', locale=self.debug_ID_locale
            )
        if self.hash_locale:
            self._hash_file = self._hash_file.format(
                target='{target}', locale=self.hash_locale
            )

    @staticmethod
    def id_gen(number: int, id_length: int) -> str:
        '''
        Generate fixed-width #12345 IDs (number to use, and ID width).
        '''
        return '#' + str(number).zfill(id_length)

    @staticmethod
    def ind_repl(match: re.Match, width: int = 5) -> str:
        '''
        Generate a zero-padded (num) or [num] index.
        '''
        index = re.sub(r'\d+', lambda match: match.group().zfill(width), match.group(2))
        return match.group(1) + index + match.group(3)

    @staticmethod
    def get_additional_comments(entry: polib.POEntry, criteria: list) -> list:
        '''
        Get additional comments based on criteria
        '''
        comments = []
        for [prop, crit, comment] in criteria:
            if re.search(crit, getattr(entry, prop)):
                comments += [comment]
        return comments

    def find_max_ID(self) -> int:
        '''
        Find max used debug ID in `targets` localization targets.
        Returns 0 if no debug IDs are used.
        '''
        max_id = 0

        for target in self.loc_targets:
            po = polib.pofile(
                self._content_path / self._debug_id_file.format(target=target),
                wrapwidth=0,
                encoding=self.encoding,
            )
            local_max_id = max(
                [
                    int(re.search(self._id_regex, entry.msgstr).group(1))
                    for entry in po
                    if re.search(self._id_regex, entry.msgstr)
                ]
            )

            max_id = max(local_max_id, max_id)

        return max_id

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

    def process_hash_locale(self, po_file: str):
        '''
        Open the PO, wrap every string in hash prefix and suffix, save the PO
        '''
        po = polib.pofile(po_file, wrapwidth=0, encoding=self.encoding)
        logger.info(f'Opened hash locale file: {po_file}')

        for entry in po:
            entry.msgstr = self.hash_prefix + entry.msgid + self.hash_suffix

        po.save(po_file)
        logger.info(f'Saved target hash locale file: {po_file}')

        return True

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

            if self.hash_locale:
                hash_loc_PO = self._content_path / self._hash_file.format(target=target)
                logger.info(f'Hash locale PO file: {hash_loc_PO}')
                logger.info(
                    'Hash symbols added '
                    f'({len(self.hash_prefix) + len(self.hash_suffix)}): '
                    f'`{self.hash_prefix}` and `{self.hash_suffix}`'
                )
                if not hash_loc_PO.exists():
                    logger.error(f'Hash locale file not found: {hash_loc_PO}')
                else:
                    self.process_hash_locale(hash_loc_PO)
                    hash_locales_processed.append(target)

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

        if self.hash_locale and not len(hash_locales_processed) == len(
            self.loc_targets
        ):
            logger.error(
                'Not all hash locales have been processed: '
                f'{len(hash_locales_processed)} out of {len(self.loc_targets)}. '
                f'Loc targets: {self.loc_targets}. Hash locale: {self.hash_locale}. '
                f'Processed hash locale targets: {hash_locales_processed}'
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
    logger.info('--- Process debug id/test/source, and hash locales script start ---')
    logger.info('')

    task = ProcessTestAndHashLocales()

    task.read_config(Path(__file__).name, logger)

    result = task.process_locales()

    logger.info('')
    logger.info('--- Process debug id/test/source, and hash locales script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Process the files if the file isn't imported
if __name__ == "__main__":
    main()
