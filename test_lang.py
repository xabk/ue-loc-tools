import re
from lib import (
    polib,
)  # Modified polib: _POFileParser.handle_oc only splits references by ','
import sys
from loguru import logger

# TODO: Add config file support
# TODO: Move parameters to config file
# TODO: Support several localization targets

# ----------------------------------------------------------------------------------------------------
# Parameters - These can be edited

HASH_STRING = '# '  # Prefix that is added to the string in hash locale

TARGET = 'Game'  # Localization target
DIR = 'Localization/{target}/io/'  # Default working directory for test locale
# Relative to Content directory, expects the script to be in in Content/Python
DIR2 = 'Localization/{target}/ia-001/'  # Working directory for "# + Source" locale
# Relative to Content directory, expects the script to be in in Content/Python

ENCODING = 'utf-8-sig'  # PO file encoding
CLEAR_TRANSLATIONS = False  # Start over? E.g., if ID length changed
SORT_PO = True  # Sort the file by source reference?
ID_LENGTH = 4  # Num of digits in ID (#0001)

# Regex to match variables that we want to keep in 'translation'
VAR_REGEX = re.compile(
    r"""
        {[^}\[<]+}|     # Looking for {text}, without nesting tags
        <[^/>]+/>       # Looking for empty tags <smth ... /> (which are images)
                        # We don't really need other formatting tags
        """,
    re.X,
)

# Regex to match indices and make them zero-padded to fix the sorting
IND_REGEX = re.compile(
    r"""
        ([\[\(])([^\]\)]+)([\]\)]) # Anything in [] or ()
        """,
    re.X,
)

# Regex to match IDs (based on the id_length, start over if you change that)
ID_REGEX = re.compile(r'#(\d{' + str(ID_LENGTH) + r'})')

DRY_RUN = False

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


def id_gen(number: int, id_length: int = 5):
    """
    Generate fixed-width #12345 IDs (number to use, and ID width)
    """
    return '#' + str(number).zfill(id_length)


def ind_repl(match: re.Match) -> str:
    """
    Generate a zero-padded (num) or [num] index
    """
    index = re.sub(r'\d+', lambda match: match.group().zfill(5), match.group(2))
    return match.group(1) + index + match.group(3)


def get_additional_comments(entry: polib.POEntry):
    comments = []
    for [prop, crit, comment] in COMMENTS:
        if re.search(crit, getattr(entry, prop)):
            comments += [comment]
    return comments


def process_file(
    source_file,
    target_file,
    encoding=ENCODING,
    clear_translatons=CLEAR_TRANSLATIONS,
    sort_po_file=SORT_PO,
    id_length=ID_LENGTH,
    dry_run=DRY_RUN,
    var_regex=VAR_REGEX,
    id_regex=ID_REGEX,
):
    """
    Process the PO file to insert #12345 IDs as 'translations'
    and add them to context
    """
    logger.info(f'Source: {source_file}')
    logger.info(f'Target: {target_file}')
    # Init current_id
    current_id = 1

    # Read the PO
    po = polib.pofile(source_file, wrapwidth=0, encoding=encoding)

    # Quick check to see how many strings are translated
    logger.info(
        'Source file translation rate: {rate:.0%}'.format(
            rate=po.percent_translated() / 100
        )
    )

    #
    # Make indices in source reference and comments zero-padded to fix the sorting
    #
    # And sort the PO by source reference to overcome the 'randomness'
    # of the default Unreal Engine export algorythm
    # and get at least some logical grouping
    #
    if sort_po_file:
        for entry in po:
            ctxt = re.sub(r'\d+', lambda match: match.group().zfill(3), entry.msgctxt)
            occurrences = []
            for oc in entry.occurrences:
                # Zero-pad array indices and add keys with zero-padded numbers to occurences to sort properly
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

    #
    # We get a list of msgstr's of our PO entries
    # that contain the ID pattern (#12345),
    # sort them (desc), pick the topmost,
    # extract the ID, convert it to a number,
    # and increment it by one to get our starting ID.
    #
    # [Get the 1st group of the match, convert it to int.]
    #
    # If no IDs found in msgstr's in our PO,
    # the starting ID stays at 1.
    #

    if not clear_translatons:
        all_ids = sorted(
            [
                int(re.search(id_regex, entry.msgstr).group(1))
                for entry in po
                if re.search(id_regex, entry.msgstr)
            ],
            reverse=True,
        )

        if len(all_ids) > 0:
            current_id = all_ids[0] + 1

    # print a bit of info on the file
    logger.info(f'Starting ID: {current_id}')

    # Get all the 'odd strings': strings that are translated
    # but do not contain any ID in their translation
    # and print those strings
    odd_strings = [
        entry
        for entry in po.translated_entries()
        if not re.search(id_regex, entry.msgstr)
    ]

    if len(odd_strings) > 0:
        logger.warning(
            f'Translated lines with no IDs in them: {str(len(po.translated_entries()) - len(all_ids))}'
        )
        logger.warning('Odd strings:')
        for entry in odd_strings:
            logger.warning(
                "> " + " /// ".join([entry.msgctxt, entry.msgid, entry.msgstr])
            )

    strings = [entry.msgid for entry in po]

    # Iterate over all entries to clear, translate, and add comments
    for entry in po:
        variables = []
        # If we want to retranslate all entries or if entry is not translated
        if clear_translatons or not entry.translated():
            variables = [str(var) for var in re.findall(var_regex, entry.msgid)]

            # Generate and save the ID
            entry.msgstr = id_gen(current_id, id_length)

            # Add the variables back
            if len(variables) > 0:
                # Python 2 can not into space :( - unicode breaks it
                # entry.msgstr += " " + " ".join('〈{0}〉'.format(v) for v in variables)
                entry.msgstr += " " + " ".join('<{0}>'.format(v) for v in variables)

            # Increase the ID for the next entry we want to translate
            current_id += 1

        # Get comments, split by newline
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
            # If we have found the Debug ID line, update the ID, and set the flag
            if comments[i].startswith('Debug ID:\t'):
                comments[i] = debug_ID
                debug_ID_done = True
                break  # No need to check other lines

        # If we haven't found the Debug ID line, add it
        if not debug_ID_done:
            comments.append(debug_ID)

        comments += get_additional_comments(entry)

        # Join the lines back and save them as a new comment
        entry.comment = '\n'.join(comments)

    # TODO Check for duplicate IDs
    ids = [entry.msgstr for entry in po.translated_entries()]
    if len(set(ids)) != len(ids):
        logger.error(
            'Duplicate #IDs spotted, please recompile the debug IDs from scratch (use CLEAR_TRANSLATIONS = True)'
        )

    # Quick check to see how many strings are translated
    # after the script is complete.
    logger.info(
        'Target file translation rate: {rate:.0%}'.format(
            rate=po.percent_translated() / 100
        )
    )
    logger.info(f'Last used ID: {current_id-1}')

    #
    # Save the file
    #
    po.save(target_file)
    logger.info(f'Saved target file: {target_file}')


def process_hash_locale(
    source_file, target_file, encoding=ENCODING, sort_po_file=SORT_PO, dry_run=DRY_RUN
):

    po = polib.pofile(source_file, wrapwidth=0, encoding=encoding)
    logger.info(f'Opened hash locale file: {source_file}')

    if sort_po_file:
        po.sort()

    for entry in po:
        entry.msgstr = HASH_STRING + entry.msgid

    if not dry_run:
        po.save(target_file)
        logger.info(f'Saved target hash locale file: {target_file}')


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

    logger.info('Resolved directory using /Game/Content/Python/ as base:')

    directory = '../' + DIR.format(target=TARGET)
    directory2 = '../' + DIR2.format(target=TARGET)

    logger.info(f'Test locale directory: {directory}')
    logger.info(f'Hash locale directory: {directory2}')
    logger.info(f'Hash symbols added: {len(HASH_STRING) - 1}')

    # Process the PO files
    fname = directory + TARGET + '.po'
    process_file(fname, fname)

    fname = directory2 + TARGET + '.po'
    process_hash_locale(fname, fname)

    logger.info('--- Debug IDs script end ---')

    return 0


# Process the file if the file isn't imported
if __name__ == "__main__":
    main()
