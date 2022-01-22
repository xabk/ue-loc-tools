import re
import argparse
from libraries import (
    polib,  # Modified polib: _POFileParser.handle_oc only splits references by ', '
    ueutilities,
)
from loguru import logger

# TODO: Add config file support
# TODO: Move parameters to config file

# TODO: Process all loc targets if none are specified

# -------------------------------------------------------------------------------------
# Parameters - These can be edited

LOC_TARGETS = ['Game', 'Game2']  # Localization targets, empty = process all targets

# Relative to Content directory
DEBUG_ID_LOCALE_FILE = 'Localization/{target}/io/{target}.po'
HASH_LOCALE_FILE = 'Localization/{target}/ia-001/{target}.po'

# Hash locale parameters
HASH_PREFIX = '# '  # Prefix added at the beginning of each string in hash locale
HASH_SUFFIX = ' ~'  # Suffix added at the end of each string in hash locale

CLEAR_TRANSLATIONS = True  # Start over? E.g., if ID length changed
ID_LENGTH = 4  # Num of digits in ID (#0001)

ENCODING = 'utf-8-sig'  # PO file encoding
SORT_PO = True  # Sort the file by source reference?

# Regex to match variables that we want to keep in 'translation'
# TODO: Add support for UE/ICU syntax (plural, genders, etc.)
VAR_REGEX = re.compile(
    r'''
    {[^}\[<]+}|     # Looking for {text}, without nesting tags
    <[^/>]+/>       # Looking for empty tags <smth ... />
                    # We don't need other formatting tags so we skip them
    ''',
    re.X,
)

# Regex to match indices and make them zero-padded to fix the sorting
IND_REGEX = re.compile(
    r'''
    ([\[\(])([^\]\)]+)([\]\)]) # Anything in [] or ()
    ''',
    re.X,
)

# Regex to match IDs (based on the id_length, start over if you change that)
ID_REGEX = re.compile(r'#(\d{' + str(ID_LENGTH) + r'})')

COMMENTS = [  # property and regex to match, comment to add
    [
        'msgctxt',
        r'AbbreviatedDisplayName,',  # comment for item abbreviation strings
        "Abbreviation slot fits 10 i's: iiiiIiiiiI. E.g.,:\niiiiIiiiiI\nSilica (fits)\nСталь (doesn't fit)",
    ],
    [
        'msgid',
        r'}\|plural\(',  # hints for strings with plurals
        "Please adapt to your language plural rules. We only support keywords: zero, one, two, few, many, other.\n"
        "Use Alt + C on Crowdin to create a skeleton adapted to your language grammar.\n"
        "Translate only white text in curly braces. Test using the form below the Preview box.\n"
        "Check what keywords stand for here: http://www.unicode.org/cldr/charts/29/supplemental/language_plural_rules.html.",
    ],
    [
        'msgid',
        r'\b[Zz]oop',  # comment to keep Zoop
        "Please keep this one as is or transliterate/change spelling only. Don't come up with funny names: it brings more harm than good.",
    ],
]

# ----------------------------------------------------------------------------------------------------


def parse_arguments():
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


def get_config(task_list=None):
    pass


def id_gen(number: int, id_length: int = 5) -> str:
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


def get_additional_comments(entry: polib.POEntry, criteria: list = COMMENTS) -> list:
    '''
    Get additional comments based on criteria
    '''
    comments = []
    for [prop, crit, comment] in criteria:
        if re.search(crit, getattr(entry, prop)):
            comments += [comment]
    return comments


def find_max_ID(targets: list, id_regex=ID_REGEX, encoding=ENCODING) -> int:
    '''
    Find max used debug ID in `targets` localization targets.
    Returns 0 if no debug IDs are used.
    '''
    max_id = 0

    for target in targets:
        print(DEBUG_ID_LOCALE_FILE.format(target=target))
        po = polib.pofile(
            DEBUG_ID_LOCALE_FILE.format(target=target), wrapwidth=0, encoding=encoding
        )
        local_max_id = max(
            [
                int(re.search(id_regex, entry.msgstr).group(1))
                for entry in po
                if re.search(id_regex, entry.msgstr)
            ]
        )

        print(local_max_id)

        max_id = max(local_max_id, max_id)

    return max_id


def process_debug_ID_locale(
    po_file,
    starting_id=1,
    encoding=ENCODING,
    clear_translatons=CLEAR_TRANSLATIONS,
    sort_po_file=SORT_PO,
    id_length=ID_LENGTH,
    var_regex=VAR_REGEX,
    id_regex=ID_REGEX,
) -> int:
    '''
    Process the PO file to insert #12345 IDs as 'translations'
    and add them to context
    '''
    logger.info(f'Processing {po_file}')

    current_id = starting_id

    po = polib.pofile(po_file, wrapwidth=0, encoding=encoding)

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
    if sort_po_file:
        for entry in po:
            ctxt = re.sub(r'\d+', lambda match: match.group().zfill(3), entry.msgctxt)
            occurrences = []
            for oc in entry.occurrences:
                # Zero-pad array indices and add keys with zero-padded numbers to occurences
                oc0 = ''
                if '### Key: ' not in oc[0]:
                    oc0 = re.sub(IND_REGEX, ind_repl, oc[0]) + f' ### Key: {ctxt}'
                else:
                    oc0 = re.sub(IND_REGEX, ind_repl, oc[0])
                occurrences.append((oc0, oc[1]))
            entry.occurrences = occurrences
            entry.comment = '\n'.join(
                [
                    re.sub(IND_REGEX, ind_repl, c)
                    for c in entry.comment.splitlines(False)
                ]
            )

        po.sort()

    if not clear_translatons:
        # Check existing translations and log strings
        # that are translated but do not contain a debug ID
        odd_strings = [
            entry
            for entry in po.translated_entries()
            if not re.search(id_regex, entry.msgstr)
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
        if clear_translatons or not entry.translated():
            variables = [str(var) for var in re.findall(var_regex, entry.msgid)]

            # Generate and save the ID
            entry.msgstr = id_gen(current_id, id_length)

            # Add the variables back
            if len(variables) > 0:
                entry.msgstr += " " + " ".join('<{0}>'.format(v) for v in variables)

            current_id += 1

        comments = entry.comment.splitlines(False)
        debug_ID_done = False
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

        comments += get_additional_comments(entry)

        entry.comment = '\n'.join(comments)

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


def process_hash_locale(po_file, encoding=ENCODING):
    '''
    Open the PO, wrap every string in hash prefix and suffix, save the PO
    '''
    po = polib.pofile(po_file, wrapwidth=0, encoding=encoding)
    logger.info(f'Opened hash locale file: {po_file}')

    for entry in po:
        entry.msgstr = HASH_PREFIX + entry.msgid + HASH_SUFFIX

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
    )

    logger.info('--- Debug IDs script start ---')

    task_list = parse_arguments()

    starting_id = 1
    if not CLEAR_TRANSLATIONS:
        starting_id = find_max_ID(LOC_TARGETS) + 1

    logger.info('Resolved directory using /Game/Content/Python/ as base:')

    if not LOC_TARGETS:
        # TODO: Get all localization targets (use ueutilities lib)
        logger.error(
            'Implicit processing of all loc targets not supported yet. '
            'Specify them exlicitely.'
        )
        return

    for target in LOC_TARGETS:

        debug_id_PO = '../' + DEBUG_ID_LOCALE_FILE.format(target=target)
        hash_loc_PO = '../' + HASH_LOCALE_FILE.format(target=target)

        logger.info(f'Processing target: {target}')
        logger.info(f'Debug IDs PO file: {debug_id_PO}')
        logger.info(f'Hash locale PO file: {hash_loc_PO}')
        logger.info(f'Hash symbols added: {len(HASH_PREFIX) + len(HASH_SUFFIX)}')

        # Process the PO files
        starting_id = process_debug_ID_locale(debug_id_PO, starting_id=starting_id)

        process_hash_locale(hash_loc_PO)

    logger.info('--- Debug IDs script end ---')

    return 0


# Process the files if the file isn't imported
if __name__ == "__main__":
    main()
