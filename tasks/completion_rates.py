import csv
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger
import subprocess
import re
from math import ceil

from libraries.utilities import LocTask, init_logging
from libraries.crowdin import UECrowdinClient

# TODO: Support several localization targets

# ----------------------------------------------------------------------------------------------------
# Parameters - These can be edited


# The section of `crowdin status` output carrying the word counts.
WORDS_SECTION = 'Translated words:'


@dataclass
class UpdateLanguageCompletionRates(LocTask):
    # Declare Crowdin parameters to load them from config
    token: str | None = None
    organization: str | None = None
    project_id: int | None = None

    use_cli: bool = True
    cli_branch: str | None = None
    cli_folders: list[str] | None = None
    cli_files: list[str] | None = None

    override_progress: dict[str, int] | None = None  # lang: progress

    language_mappings: dict[str, str] = field(
        default_factory=lambda: {
            'zh-CN': 'zh-Hans',
            'zh-TW': 'zh-Hant',
            'es-MX': 'es-419',
        }
    )

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

    _csv_path: Path | None = None
    _content_path: Path | None = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir)
        self._csv_path = self._content_path / self.csv_name

    def cli_get_completion_rates(self) -> dict[str, dict[str, int]]:
        def add_stats(
            result: list[str], stats: dict[str, dict[str, int]]
        ) -> dict[str, dict[str, int]]:
            """Read the `Translated words` section of `crowdin status`.

            The output is one section per metric, each a flat list of
            `<language> <translated>/<total>`:

                Translated:
                de 100
                Translated words:
                de 37163/37163
                Translated phrases:
                de 6415/6415

            Only the word counts are summed, because folders differ in size and
            averaging their percentages would weight a small one like a large
            one.
            """
            in_words_section = False
            for line in result:
                line = line.strip()
                if not line:
                    continue

                if line.endswith(':'):
                    in_words_section = line == WORDS_SECTION
                    continue

                if not in_words_section:
                    continue

                match = re.match(r'^(\S+)\s+(\d+)/(\d+)$', line)
                if not match:
                    continue

                lang, translated, total = (
                    match.group(1),
                    int(match.group(2)),
                    int(match.group(3)),
                )
                if lang in stats:
                    stats[lang]['translated'] += translated
                    stats[lang]['total'] += total
                else:
                    stats[lang] = {'translated': translated, 'total': total}
            return stats

        stats = {}

        if self.organization:
            base_url = f'https://{self.organization}.api.crowdin.com'
        else:
            base_url = 'https://api.crowdin.com'

        command = [
            'crowdin',
            'status',
            'translation',
            f'--base-url={base_url}',
            f'--project-id={self.project_id}',
            '-v',
            '--no-progress',
            '--output',
            'plain',
        ]

        if self.cli_branch:
            command += ['--branch', self.cli_branch]

        for folder in self.cli_folders:
            logger.info(
                f'Getting completion rates for {folder}:\n'
                f'{" ".join(command)} -d {folder}'
            )

            result = subprocess.run(
                [*command, '-d', folder, '--token', self.token],
                capture_output=True,
                text=True,
                shell=True,
            )
            if result.returncode != 0:
                logger.error(
                    f'Failed to get completion rates for {folder}. CLI output:'
                )
                logger.error(result.stdout)
                logger.error(result.stderr)
                continue

            stats = add_stats(result.stdout.splitlines(), stats)

        for file in self.cli_files:
            result = subprocess.run(
                [*command, '-f', file, '--token', self.token],
                capture_output=True,
                text=True,
                shell=True,
            )
            if result.returncode != 0:
                logger.error(f'Failed to get completion rates for {folder}')
                continue

            stats = add_stats(result.stdout.splitlines(), stats)

        for lang in stats:
            stats[lang]['translationProgress'] = ceil(
                stats[lang]['translated'] / stats[lang]['total'] * 100
            )

        for lang in self.language_mappings:
            if lang in stats:
                stats[self.language_mappings[lang]] = stats.pop(lang)

        return stats

    def get_completion_rates_for_all_targets(self) -> dict | None:
        ### TODO: DEPRECATED
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
                "Incomplete data from Crowdin. Can't use it as it may lead to wrong completion rates!"
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

        completion_rates = {}

        if self.use_cli:
            completion_rates = self.cli_get_completion_rates()
        else:
            completion_rates = self.get_completion_rates_for_all_targets()

        if not completion_rates:
            logger.error('No completion rates received. Exiting.')
            return False

        logger.info('Completion rates received:')
        for lang, data in completion_rates.items():
            logger.info(f'{lang}: {data["translationProgress"]}%')

        for row in rows:
            # Skip the native and test cultures (100% anyway)
            if row[0] in self.cultures_to_skip:
                logger.info(
                    f"{row[0]} skipped because it's in the locales to skip list."
                )
                locales_skipped += 1
                continue

            if self.override_progress and row[0] in self.override_progress:
                logger.info(
                    f'{row[0]} updated from {row[4]} to {self.override_progress[row[0]]} (Override).'
                )
                row[4] = self.override_progress[row[0]]
                locales_processed += 1
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

    def run(self):
        return self.update_completion_rates()


def main():
    init_logging()

    logger.info('')
    logger.info(
        '--- Pull completion rates from Crowdin and update language list CSV ---'
    )
    logger.info('')

    task = UpdateLanguageCompletionRates()

    task.read_config(Path(__file__).name)

    result = task.update_completion_rates()

    logger.info('')
    logger.info('--- Completion rates script end ---')
    logger.info('')

    if result:
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == '__main__':
    main()
