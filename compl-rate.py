import csv
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

    csv_encoding: str = 'utf-16-le'

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    _csv_path: Path = None
    _content_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir)
        self._csv_path = self._content_path / self.csv_name

    def get_completion_rates_for_all_targets(self) -> dict:
        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        completion_rates = {}

        logger.info(
            f'Targets to query on Crowdin: ({len(self.loc_targets)}): {self.loc_targets}.'
        )

        targets_processed = []

        for target in self.loc_targets:
            if not completion_rates:
                completion_rates = crowdin.get_completion_rates(filename=target + '.po')

                if not completion_rates:
                    logger.warning(
                        f'No completion rates from Crowdin for target: {target}'
                    )
                    continue

                logger.info(
                    f'Initialized completion rates with data for target: {target}'
                )
            else:
                new_rates = crowdin.get_completion_rates(filename=target + '.po')

                if not new_rates:
                    logger.warning(
                        f'No completion rates from Crowdin for target: {target}'
                    )
                    continue

                for lang, data in completion_rates.items():
                    for key in data:
                        completion_rates[lang][key] += new_rates[lang][key]

            targets_processed += [target]

        # All good, received completion rates for all targets
        if targets_processed and len(targets_processed) == len(self.loc_targets):
            logger.info(
                f'Got completion rates for targets ({len(targets_processed)} / {len(self.loc_targets)}): '
                f'{targets_processed}.'
            )
            if len(targets_processed) > 1:
                for lang, data in completion_rates.items():
                    completion_rates[lang]['translationProgress'] = round(
                        completion_rates[lang]['translated']
                        / completion_rates[lang]['total']
                    )
                    completion_rates[lang]['approvalProgress'] = round(
                        completion_rates[lang]['approved']
                        / completion_rates[lang]['total']
                    )

            return completion_rates

        # Only received completion rates for some targets
        # Data incomplete, better not use it
        if targets_processed and len(targets_processed) != len(self.loc_targets):
            logger.error(
                'Incomplete data from Crowdin. Can\'t use it as it may lead to wrong completion rates!'
            )
            logger.error(
                f'Only recieved data for targets ({len(targets_processed)} / {len(self.loc_targets)}): '
                f'{targets_processed}. Full list of targets configured: {self.loc_targets}.'
            )

            return None

        # No data received
        logger.warning(
            f'No data recieved from Crowdin for targets: {self.loc_targets}.'
        )

        return None

    def update_completion_rates(self):
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

        completion_rates = self.get_completion_rates_for_all_targets()

        if completion_rates:
            logger.info(f'Got completion rates for from Crowdin:')
            logger.info(completion_rates)
        else:
            # No data to process
            logger.error(f'No completion rates recieved from Crowdin. Aborting!')
            return False

        for row in rows:
            # Skip the native and test cultures (100% anyway)
            if row[0] in self.cultures_to_skip:
                logger.info(
                    f'{row[0]} skipped because it\'s in the locales to skip list.'
                )
                locales_skipped += 1
                continue

            if row[0] in completion_rates:
                logger.info(
                    f'{row[0]} updated from {row[4]} to {completion_rates[row[0]]["translationProgress"]} '
                    '(Crowdin data).'
                )
                row[4] = completion_rates[row[0]]['translationProgress']
                locales_processed += 1
            else:
                if completion_rates:
                    logger.warning(
                        f'{row[0]} missing from language mappings. Not updated.'
                    )

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
