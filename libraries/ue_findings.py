"""What is worth collecting out of an Unreal localization commandlet's log.

Shared by both gathers, so a category added for one is reported by the
other and findings from the two can be merged.
"""

import re

from libraries.findings import Findings

# An entry referenced but not in the string table. Two tools report this.
# The engine names neither the asset nor the reference:
MISSING_ST_ENTRY = re.compile(
    r"Failed to find string table entry for '([^']*)' '([^']*)'"
)
# ...while the reference gather says exactly where the reference lives:
MISSING_REFERENCE = re.compile(
    r'<MissingStringTableReference> StringTable: \[([^]]+)\], '
    r'Key: \[([^]]+)\] Context: (.*)'
)
# Two assets carrying the same localization ID: their text can collide.
ID_COLLISION = re.compile(
    r"Package '([^']*)' and '([^']*)' have the same localization ID \(([0-9A-F]+)\)"
)
# Heads the lines under it, and is the only place the text gather ties a
# missing entry to an asset.
PACKAGE_PROBLEMS = re.compile(
    r"Package '([^']*)' produced \d+ error\(s\) and \d+ warning\(s\)"
)

# Unreal re-prints every warning at the end. Collecting from the recap
# double counts, and it carries no context.
UE_RECAP = re.compile(r'Warning/Error Summary \(Unique only\)')

MISSING_ENTRIES = 'string table entr(ies) referenced but missing'
COLLISIONS = 'pair(s) of assets sharing a localization ID'
GATHER_PROBLEMS = 'other warning(s) from the localization pipeline'

# Unreal logs under fifty categories during a gather; the rest are the
# editor starting itself up, and not this tool's business.
GATHER_LOG_CATEGORIES = (
    'LogGatherTextCommandlet',
    'LogGatherTextFromAssetsCommandlet',
    'LogGatherTextFromSourceCommandlet',
    'LogGatherStringTableReferencesCommandlet',
    'LogGenerateManifestCommandlet',
    'LogGenerateArchiveCommandlet',
    'LogGenerateTextLocalizationReportCommandlet',
    'LogInternationalizationExportCommandlet',
    'LogStringTable',
)


def _one_place(context: str) -> str:
    """Collapse Unreal's three names for one reference: the asset, the _C
    class it compiles to, and the bytecode of the same function."""
    context = re.sub(r'_C(?=[:.]|$)', '', context)
    return re.sub(r'\s*\[Script Bytecode\]$', '', context).strip()


def collect(findings: Findings, line: str, asset: str | None = None) -> bool:
    """Take out of one line anything worth repeating at the end, and say
    whether this was one of them.

    Keyed by what is wrong, never by the line that reported it.
    """
    named = MISSING_REFERENCE.search(line)
    if named:
        table, key, context = named.groups()
        findings.add(MISSING_ENTRIES, f'{table},{key}', _one_place(context))
        return True

    missing = MISSING_ST_ENTRY.search(line)
    if missing:
        findings.add(
            MISSING_ENTRIES,
            f'{missing.group(1)},{missing.group(2)}',
            f'in {asset}' if asset else '',
        )
        return True

    collision = ID_COLLISION.search(line)
    if collision:
        first, second, loc_id = collision.groups()
        findings.add(COLLISIONS, ' and '.join(sorted((first, second))), f'id {loc_id}')
        return True

    if ('Warning: ' in line or 'Error: ' in line) and any(
        category in line for category in GATHER_LOG_CATEGORIES
    ):
        findings.add(GATHER_PROBLEMS, line.strip())
        return True

    return False
