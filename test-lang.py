import yaml
import re
import argparse
from loguru import logger
from pathlib import Path
from dataclasses import dataclass, field, fields

from libraries import (
    polib,  # Modified polib: _POFileParser.handle_oc only splits references by ', '
    uetools,
    utilities,
)

from pprint import pprint as pp

# -------------------------------------------------------------------------------------
# Defaults - These can be edited, only used if not overridden in configs
# (needed to make the script work standalone)
#
# Priority:
# 1. Script parameters in task list section of base.config.yaml (if task list provided)
# 2. Global params from base.config.yaml (if config file found and parameters found)
# 3. Defaults below (if no parameters found in config or no config found)
@dataclass
class TestLangParameters(utilities.Parameters):
    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

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
        default_factory=lambda: [  # property and regex to match, comment to add
            [
                'msgid',
                r'}\|plural\(',  # hints for strings with plurals
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

    # Actual regex based on id_length
    id_regex: str = None

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_path = '../'

    def post_update(self):
        super().post_update()
        self.id_regex = self.id_regex_pattern.format(id_length=self.id_length)


# ---------------------------------------------------------------------------------

# PO files, relative to Content directory
DEBUG_ID_LOCALE_FILE = 'Localization/{target}/{locale}/{target}.po'
HASH_LOCALE_FILE = 'Localization/{target}/{locale}/{target}.po'


def get_task_list_from_arguments():
    parser = argparse.ArgumentParser(
        description='''
        Create a debug ID locale using settings in base.config.yaml
        For defaults: test_lang.py
        For task-specific settings: test_lang.py task_list_name
        '''
    )

    parser.add_argument(
        'tasklist',
        type=str,
        nargs='?',
        help='Task list to run from base.config.yaml',
    )

    return parser.parse_args().tasklist


def id_gen(number: int, id_length: int) -> str:
    '''
    Generate fixed-width #12345 IDs (number to use, and ID width).
    '''
    return '#' + str(number).zfill(id_length)


def ind_repl(match: re.Match, width: int = 5) -> str:
    '''
    Generate a zero-padded (num) or [num] index.
    '''
    index = re.sub(r'\d+', lambda match: match.group().zfill(width), match.group(2))
    return match.group(1) + index + match.group(3)


def get_additional_comments(entry: polib.POEntry, criteria: list) -> list:
    '''
    Get additional comments based on criteria
    '''
    comments = []
    for [prop, crit, comment] in criteria:
        if re.search(crit, getattr(entry, prop)):
            comments += [comment]
    return comments


def find_max_ID(cfg: TestLangParameters) -> int:
    '''
    Find max used debug ID in `targets` localization targets.
    Returns 0 if no debug IDs are used.
    '''
    max_id = 0

    for target in cfg.loc_targets:
        po = polib.pofile(
            cfg.content_path
            + DEBUG_ID_LOCALE_FILE.format(target=target, locale=cfg.debug_ID_locale),
            wrapwidth=0,
            encoding=cfg.encoding,
        )
        local_max_id = max(
            [
                int(re.search(cfg.id_regex, entry.msgstr).group(1))
                for entry in po
                if re.search(cfg.id_regex, entry.msgstr)
            ]
        )

        max_id = max(local_max_id, max_id)

    return max_id


def process_debug_ID_locale(
    po_file: str, starting_id: int, cfg: TestLangParameters
) -> int:
    '''
    Process the PO file to insert #12345 IDs as 'translations'
    and add them to context
    '''
    logger.info(f'Processing {po_file}')

    current_id = starting_id

    po = polib.pofile(po_file, wrapwidth=0, encoding=cfg.encoding)

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
    if cfg.sort_po:
        for entry in po:
            ctxt = re.sub(r'\d+', lambda match: match.group().zfill(3), entry.msgctxt)
            occurrences = []
            for oc in entry.occurrences:
                # Zero-pad array indices and add keys with zero-padded numbers to occurences
                oc0 = ''
                if '### Key: ' not in oc[0]:
                    oc0 = re.sub(cfg.ind_regex, ind_repl, oc[0]) + f' ### Key: {ctxt}'
                else:
                    oc0 = re.sub(cfg.ind_regex, ind_repl, oc[0])
                occurrences.append((oc0, oc[1]))
            entry.occurrences = occurrences
            entry.comment = '\n'.join(
                [
                    re.sub(cfg.ind_regex, ind_repl, c)
                    for c in entry.comment.splitlines(False)
                ]
            )

        po.sort()

    if not cfg.clear_translations:
        # Check existing translations and log strings
        # that are translated but do not contain a debug ID
        odd_strings = [
            entry
            for entry in po.translated_entries()
            if not re.search(cfg.id_regex, entry.msgstr)
        ]

        if odd_strings:
            logger.warning(
                f'Translated lines with no IDs in them ({len(odd_strings)}):'
            )
            for entry in odd_strings:
                logger.warning("\n".join([entry.msgctxt, entry.msgid, entry.msgstr]))

    logger.info(f'Starting ID: {current_id}')

    strings = [entry.msgid for entry in po]

    # Iterate over all entries to generate debug IDs, patch and add comments
    for entry in po:
        variables = []

        # If we want to retranslate all entries or if entry is not translated
        if cfg.clear_translations or not entry.translated():
            variables = [str(var) for var in re.findall(cfg.var_regex, entry.msgid)]

            # Generate and save the ID
            entry.msgstr = id_gen(current_id, cfg.id_length)

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

        comments += get_additional_comments(entry, cfg.comments_criteria)

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


def process_hash_locale(po_file: str, cfg: TestLangParameters):
    '''
    Open the PO, wrap every string in hash prefix and suffix, save the PO
    '''
    po = polib.pofile(po_file, wrapwidth=0, encoding=cfg.encoding)
    logger.info(f'Opened hash locale file: {po_file}')

    for entry in po:
        entry.msgstr = cfg.hash_prefix + entry.msgid + cfg.hash_suffix

    po.save(po_file)
    logger.info(f'Saved target hash locale file: {po_file}')


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

    logger.info('--- Debug IDs script start ---')

    task_list = get_task_list_from_arguments()

    cfg = TestLangParameters()

    cfg.read_config(Path(__file__).name, logger, task_list=task_list)

    logger.info(f'Content path: {Path(cfg.content_path).absolute()}')

    starting_id = 1
    if not cfg.clear_translations and cfg.debug_ID_locale:
        starting_id = find_max_ID(cfg) + 1

    if not cfg.loc_targets:
        # TODO: Get all localization targets (use ueutilities lib)
        logger.error(
            'Implicit processing of all loc targets not supported yet. '
            'Specify them exlicitely for now.'
        )
        return

    for target in cfg.loc_targets:
        if cfg.debug_ID_locale:
            debug_id_PO = cfg.content_path + DEBUG_ID_LOCALE_FILE.format(
                target=target, locale=cfg.debug_ID_locale
            )
            logger.info(f'Processing target: {target}')
            logger.info(f'Debug IDs PO file: {debug_id_PO}')
            starting_id = process_debug_ID_locale(debug_id_PO, starting_id, cfg)

        if cfg.hash_locale:
            hash_loc_PO = cfg.content_path + HASH_LOCALE_FILE.format(
                target=target, locale=cfg.hash_locale
            )
            logger.info(f'Hash locale PO file: {hash_loc_PO}')
            logger.info(
                f'Hash symbols added: {len(cfg.hash_prefix) + len(cfg.hash_suffix)}'
            )
            process_hash_locale(hash_loc_PO, cfg)

    logger.info('--- Debug IDs script end ---')

    return 0


# Process the files if the file isn't imported
if __name__ == "__main__":
    main()
