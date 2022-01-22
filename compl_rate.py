import csv
import polib
import os
import argparse
import crowdin

# TODO: Use loguru for logging

# TODO: Add config file support
# TODO: Move parameters to config file

# TODO: Add parameter to control fall back to PO file stats (line 73)

# TODO: Support several localization targets

# ----------------------------------------------------------------------------------------------------
# Parameters - These can be edited

CSV_FILENAME = 'Localization/DT_OptionsMenuLanguages.csv'  # Relative to Content the project directory
TARGET = 'Game'  # Game localization target
POFILE = 'Localization/{target}/{locale}/Game.po'  # Relative to Content the project directory
CSV_ENCODING = 'utf-16-le'
PO_ENCODING = 'utf-8-sig'
PO_COMPL_MOD = (
    100 / 88
)  # TODO Use this to scale completion (X*MOD) to account for hidden/debug lines

# ----------------------------------------------------------------------------------------------------


def update_completion_rates(
    filename=CSV_FILENAME,
    target=TARGET,
    popath=POFILE,
    csv_encoding=CSV_ENCODING,
    po_encoding=PO_ENCODING,
):
    """
    Updates completion rates for all languages listed in the languages CSV
    by getting translated percetanges from POs it respective locale folders
    """

    fields = []
    rows = []
    with open(filename, mode='r', encoding=csv_encoding, newline='') as csv_file:
        csv_reader = csv.reader(csv_file)
        fields = next(csv_reader)
        for row in csv_reader:
            rows.append(row)

    processed = 0

    completion_rates = crowdin.get_completion_rates(crowdin.init_crowdin())

    if len(completion_rates) > 0:
        print('Got completion rates from Crowdin!')

    for row in rows:
        # TODO: Extract native culture to parameters
        # Skip the native and test cultures (100% anyway)
        if row[0] in ['en-US-POSIX', 'io']:
            continue

        if len(completion_rates) > 0:
            if row[0] not in completion_rates:
                print(row[0] + 'missing from language mappings')
            print(
                row[0]
                + ' updated from '
                + row[4]
                + ' to '
                + str(completion_rates[row[0]]['translationProgress'])
            )
            row[4] = completion_rates[row[0]]['translationProgress']
        else:
            # Check if the file exists, open it and get completion rate
            curr_path = popath.format(target=target, locale=row[0])
            if os.path.isfile(curr_path):
                po = polib.pofile(curr_path)
                if po.percent_translated() > 1 / PO_COMPL_MOD:
                    print(
                        curr_path
                        + ' updated from '
                        + row[4]
                        + ' to 100 (rounded up from 95+)'
                    )
                    row[4] = '100'
                else:
                    print(
                        curr_path
                        + ' updated from '
                        + row[4]
                        + ' to '
                        + str(po.percent_translated())
                    )
                    row[4] = str(po.percent_translated())
                processed += 1
            else:
                print(curr_path + ' skipped: no PO file found.')

    with open(filename, 'w', encoding=csv_encoding, newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(fields)
        csv_writer.writerows(rows)


def main():

    filename = '../' + CSV_FILENAME  # Assume we're in /Game/Content/Python directory
    popath = '../' + POFILE  # Assume we're in /Game/Content/Python directory

    update_completion_rates(filename=filename, popath=popath)

    return 0


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
