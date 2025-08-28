import os
import csv
import json
import argparse
from pathlib import Path

# Your project name = project directory
PROJECT_NAME = 'YourProjectName'

# Path to the localization root directory, relative to this script
# By default, we assume we're in the plugin directory
# and the project folder structure is like:
# <root>/Engine/Plugins/CSLocTools/<We're here>
# <root>/YourProjectName/Content/Localization
# Adjust this path as necessary
LOC_ROOT_PATTERN = '../../Content/Localization'

# Path to the resulting draft CSV file for the patch table
CSV_NAME = 'PatchTableDraft.csv'

# Targets to process, affects both manifests and debug IDs
# ['Your', 'Localization', 'Targets']
TARGETS = ['Game']

# Header for the CSV file
# All fields are required except for DebugID and Context
# `Context` added as a metadata column to encourage devs to add context
HEADER = [
    'Namespace',
    'Key',
    'SourceString',
    'DebugID',
    'Path',
    'StringTable',
    'NewKey',
    'Context',
]

# Locale for debug IDs, usually 'io', see loc tools
# This requires `polib` to be installed (`pip install polib`)
# - Set to '' if you don't want to add debug IDs
# - Set to a valid locale if you want to add debug IDs
DEBUG_LOCALE = ''

# ====================================================================================

# Location root path, based on the pattern
LOC_ROOT = Path(LOC_ROOT_PATTERN.format(project_name=PROJECT_NAME)).resolve().absolute()
CSV_PATH = (LOC_ROOT / CSV_NAME).resolve().absolute()
DEBUG_ID_PATH = f'{{target}}/{DEBUG_LOCALE}/{{target}}.po'


def parse_arguments():
    """Parse command-line arguments for the script."""
    parser = argparse.ArgumentParser(
        description='Generate a patch table CSV from Unreal Engine localization manifests.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ManifestsToPatchTable.py
  python ManifestsToPatchTable.py --project-name "MyProject"
  python ManifestsToPatchTable.py --loc-root "C:/MyProject/Content/Localization"
  python ManifestsToPatchTable.py --targets Game UI Menu --debug-locale io
  python ManifestsToPatchTable.py --csv-path "MyPatchTable.csv"
        """,
    )

    # Create mutually exclusive group for project-name and loc-root
    location_group = parser.add_mutually_exclusive_group()

    location_group.add_argument(
        '--project-name',
        default=None,
        help=f'Project name used to calculate default loc-root path (default: "{PROJECT_NAME}")',
    )

    location_group.add_argument(
        '--loc-root',
        type=Path,
        default=None,
        help=f'Path to the localization root directory (default: {str(LOC_ROOT)})',
    )

    parser.add_argument(
        '--csv-path',
        type=Path,
        help='Relative to <loc_root>: Path to the resulting patch table CSV file (default: <loc-root>/PatchTableDraft.csv)',
    )

    parser.add_argument(
        '--targets',
        nargs='+',
        default=TARGETS,
        help=f'Localization targets to process (default: {TARGETS})',
    )

    parser.add_argument(
        '--debug-locale',
        default=DEBUG_LOCALE,
        help=f'Locale for debug IDs (default: "{DEBUG_LOCALE}" - empty means no debug IDs)',
    )

    args = parser.parse_args()

    # Handle mutually exclusive location arguments
    if args.project_name is not None:
        # Calculate loc_root based on project name
        print(f'Using supplied project name: {args.project_name}')
        args.loc_root = (
            Path(LOC_ROOT_PATTERN.format(project_name=args.project_name))
            .resolve()
            .absolute()
        )
    elif args.loc_root is not None:
        # Use provided loc_root, ensure it's absolute
        print(f'Using supplied loc root: {args.loc_root}')
        args.loc_root = args.loc_root.resolve().absolute()
    else:
        # Use default loc_root
        print(f'Using default loc root: {LOC_ROOT}')
        args.loc_root = LOC_ROOT

    # Ensure loc_root is absolute
    args.loc_root = args.loc_root.resolve().absolute()

    # Set csv_path default based on loc_root if not provided
    if args.csv_path is None:
        args.csv_path = (args.loc_root / CSV_NAME).resolve().absolute()
    else:
        args.csv_path = args.csv_path.resolve().absolute()

    return args


def write_each_child_as_row(children, namespaces, writer):
    num_entries = 0
    print(f'Writing {len(children)} children for namespace {namespaces}...')
    for child in children:
        # Key, SourceString, Description, FileName

        source_string = child['Source']['Text']

        for child_key in child['Keys']:
            namespace = ','.join(namespaces)
            key = child_key['Key']
            description = child_key['Path']
            data = [namespace, key, source_string, '', description, '', '', '']
            writer.writerow(data)
            num_entries += 1

    return num_entries


def process_manifest_data(manifest_data, namespaces, writer):
    num_entries = 0
    namespaces_ = namespaces.copy()

    if manifest_data['Namespace'] != '':
        namespaces_.append(manifest_data['Namespace'])

    print(f'Processing namespace: {namespaces_}')

    if 'Children' in manifest_data:
        num_entries += write_each_child_as_row(
            manifest_data['Children'], namespaces_, writer
        )

    print('Processed children. Checking for Subnamespaces...')

    if 'Subnamespaces' in manifest_data:
        for namespace in manifest_data['Subnamespaces']:
            num_entries += process_manifest_data(namespace, namespaces_, writer)

    return num_entries


def manifests_to_csv(manifests, csv_path):
    with open(csv_path, 'w', encoding='utf-8', newline='') as csv_file:
        writer = csv.writer(csv_file)

        writer.writerow(HEADER)

        for path in manifests:
            print(f'Loading manifest: {path}')

            num_entries = 0

            with open(path, encoding='utf-16') as manifest_file:
                manifest_data = json.load(manifest_file)

                num_entries += process_manifest_data(manifest_data, [], writer)

            print(f'Wrote {num_entries} entries to CSV from this manifest')
        print('Saved CSV: ' + str(csv_path.resolve().absolute()))


def add_debug_ids_to_patch_table(patch_table_path, debug_po_files):
    print(f'Reading patch table from `{patch_table_path}`...')

    # Read the CSV file into a list of dictionaries
    rows = []
    with open(patch_table_path, 'r', encoding='utf-8-sig', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            rows.append(row)

    # Create a lookup dictionary for faster searching
    header = HEADER.copy()
    debug_id_lookup = {}
    processed_any_debug_POs = False

    loaded_polib = False
    if any(po_path.exists() for po_path in debug_po_files):
        try:
            import polib

            loaded_polib = True
        except ImportError:
            print(
                'Error: polib library is not installed. Please install it with `pip install polib`.'
            )
            loaded_polib = False

    if loaded_polib:
        for debug_po_path in debug_po_files:
            debug_po_path = debug_po_path.resolve().absolute()
            print(f'Checking debug PO file: {debug_po_path}')
            if not debug_po_path.exists():
                print(
                    f'Warning: Debug PO file not found at `{debug_po_path}`. Skipping.'
                )
                continue

            try:
                print(f'Loading debug PO file from `{debug_po_path}`...')
                po = polib.pofile(debug_po_path, encoding='utf-8-sig')
            except Exception as e:
                print(
                    f'Error loading PO file `{debug_po_path}`: {e}. Skipping debug ID addition.'
                )
                continue

            for entry in po:
                namespace, _, key = str(entry.msgctxt).partition(',')

                # Extract debug ID from comment line that starts with "Debug ID:\t"
                debug_id = ''
                if entry.comment:
                    for line in entry.comment.split('\n'):
                        if line.startswith('Debug ID:\t'):
                            debug_id_line = line[len('Debug ID:\t') :]
                            debug_id = debug_id_line.split('\t', 1)[0].strip()
                            break

                if debug_id:  # Only add to lookup if we found a debug ID
                    processed_any_debug_POs = True
                    if namespace:
                        debug_id_lookup[(namespace, key)] = debug_id
                    else:
                        debug_id_lookup[('', key)] = debug_id

    if not processed_any_debug_POs:
        print('No debug IDs found in any debug PO files. Skipping debug ID addition.')
        # Remove the DebugID column from all rows if it exists
        for row in rows:
            if 'DebugID' in row:
                del row['DebugID']
        # Remove DebugID from the headers if present
        header = [h for h in HEADER if h != 'DebugID']
    else:
        for row in rows:
            namespace = row['Namespace']
            key = row['Key']

            # Try to find debug ID with namespace first, then without
            if (namespace, key) in debug_id_lookup:
                row['DebugID'] = debug_id_lookup[(namespace, key)]
            elif ('', key) in debug_id_lookup:
                row['DebugID'] = debug_id_lookup[('', key)]

    # Write the updated data back to the CSV file
    with open(patch_table_path, 'w', encoding='utf-8-sig', newline='') as csvfile:
        writer = csv.DictWriter(
            csvfile, fieldnames=header, lineterminator='\r\n', quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f'Added debug IDs to `{patch_table_path}`...')


if __name__ == '__main__':
    args = parse_arguments()

    print(f'Localization root: {args.loc_root}')
    print(f'Patch table draft CSV: {args.csv_path}')
    print(f'Targets: {args.targets}')
    print(f'Debug locale: "{args.debug_locale}"')

    manifests = [
        f for f in args.loc_root.rglob('**/*.manifest') if f.stem in args.targets
    ]
    print(f'Manifests found: {[str(m) for m in manifests]}')

    manifests_to_csv(manifests, args.csv_path)

    debug_id_files = []
    if args.debug_locale:
        debug_id_files = [
            args.loc_root / f'{target}/{args.debug_locale}/{target}.po'
            for target in args.targets
        ]
    add_debug_ids_to_patch_table(args.csv_path, debug_id_files)

    print('Opening patch table draft location...')
    os.startfile(args.csv_path.parent)
