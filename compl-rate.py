import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger

from libraries import utilities, polib
from libraries.crowdin import UECrowdinClient

# TODO: Add parameter to control fall back to PO file stats (line 73)

# TODO: Support several localization targets

# ----------------------------------------------------------------------------------------------------
# Parameters - These can be edited


@dataclass
class CommunityCreditsUpdater(utilities.Parameters):

    # Declare Crowdin parameters to load them from config
    token: str = None
    organization: str = None
    project_id: int = None

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    cultures_to_skip: list = field(
        default_factory=lambda: ['en-US-POSIX', 'io']
    )  # Locales to skip (native, debug, etc.)

    csv_name: str = 'Localization/DT_OptionsMenuLanguages.csv'  # Relative to Content the project directory
    po_name: str = 'Localization/{target}/{locale}/{target}.po'  # Relative to Content the project directory

    csv_encoding: str = 'utf-16-le'
    po_encoding: str = 'utf-8-sig'

    po_completion_threshold: int = 100  # PO-based completion percent to use as 100%

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    _csv_path: Path = None
    _content_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir)
        self._csv_path = self._content_path / self.csv_name

    def update_completion_rates_for_target(self, target: str):
        """
        Updates completion rates for all languages listed in the languages CSV
        by getting translated percetanges from POs it respective locale folders
        """

        fields = []
        rows = []
        with open(
            self._csv_path, mode='r', encoding=self.csv_encoding, newline=''
        ) as csv_file:
            csv_reader = csv.reader(csv_file)
            fields = next(csv_reader)
            for row in csv_reader:
                rows.append(row)

        locales_processed = 0
        locales_skipped = 0

        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        completion_rates = crowdin.get_completion_rates(filename=target + '.po')

        if completion_rates:
            logger.info(f'Got completion rates for {target}.po from Crowdin:')
            logger.info(completion_rates)
        else:
            logger.warning(
                f'No completion rates for {target}.po recieved from Crowdin! '
                f'Using PO file completion rates with multiplier: {self.po_completion_threshold}.'
            )

        for row in rows:
            # Skip the native and test cultures (100% anyway)
            if row[0] in self.cultures_to_skip:
                logger.info(
                    f'{row[0]} skipped because it\'s in the locales to skip list.'
                )
                locales_skipped += 1
                continue

            if completion_rates and row[0] in completion_rates:
                logger.info(
                    f'{row[0]} updated from {row[4]} to {completion_rates[row[0]]["translationProgress"]} '
                    '(Crowdin data).'
                )
                row[4] = completion_rates[row[0]]['translationProgress']
                locales_processed += 1
            else:
                if completion_rates:
                    logger.warning(
                        f'{row[0]} missing from language mappings. Updating using the PO file.'
                    )
                else:
                    logger.warning(
                        f'No completion rates from Crowdin. Updating {row[0]} using the PO file.'
                    )
                # Check if the file exists, open it and get completion rate
                curr_path = Path(self.po_name.format(target=target, locale=row[0]))
                if curr_path.exists() and curr_path.is_file():
                    po = polib.pofile(curr_path, encoding=self.po_encoding)
                    new_completion_rate = 0
                    if po.percent_translated() >= self.po_completion_threshold:
                        new_completion_rate = 100
                    else:
                        new_completion_rate = round(
                            self.po_completion_threshold / po.percent_translated()
                        )

                    logger.info(
                        f'{curr_path} updated from {row[4]} to {str(po.percent_translated())} '
                        '(PO-based completion rate).'
                    )
                    row[4] = new_completion_rate
                    locales_processed += 1
                else:
                    logger.error(
                        f'{row[0]} skipped: no info from Crowdin and no PO file found at {curr_path}.'
                    )
                    locales_skipped += 1

        with open(
            self._csv_path, 'w', encoding=self.csv_encoding, newline=''
        ) as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(fields)
            csv_writer.writerows(rows)

        if locales_processed:
            logger.info(
                f'Processed locales: {locales_processed} / {len(rows)}. Locales skipped: {locales_skipped}.'
            )
            return True
        else:
            logger.warning(f'No locales processed for target: {target}.')

        return False

    def update_completion_rates(self):
        logger.info(
            f'Targets to process ({len(self.loc_targets)}): {self.loc_targets}.'
        )

        targets_processed = []
        for t in self.loc_targets:
            if self.update_completion_rates_for_target(t):
                targets_processed += [t]

        if targets_processed:
            logger.info(
                f'Targets processed ({len(targets_processed)} / {len(self.loc_targets)}): {targets_processed}.'
            )
            return True

        logger.warning('No targets processed.')

        return False


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
    logger.info(
        '--- Pull completion rates from Crowdin and update language list CSV ---'
    )
    logger.info('')

    cfg = CommunityCreditsUpdater()

    cfg.read_config(Path(__file__).name, logger)

    result = cfg.update_completion_rates()

    logger.info('')
    logger.info('--- Completion rates script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
