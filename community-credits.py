import re
import csv
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

from libraries.utilities import LocTask
from libraries.crowdin import UECrowdinClient


@dataclass
class UpdateCommunityCredits(LocTask):

    # Declare Crowdin parameters to load them from config
    token: str = None
    organization: str = None
    project_id: int = None

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    # Relative to Game/Content directory
    csv_name: str = 'Path/To/CSV_Source_For_Datatable.csv'
    csv_encoding: str = 'utf-16-le'

    # How many words people should translate or approve to get into the credits
    # It's better to keep the values once set, otherwise some older translators might be
    # excluded from credits later on and it's not something we want
    translation_threshold: int = 2000
    review_threshold: int = 2000

    # List of people to exclude: pros, employees... and cheaters, if any
    users_to_exclude: list = None

    # List of languages to exclude ()
    languages_to_exclude: list = None

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'

    _csv_path: Path = None
    _content_path: Path = None

    def post_update(self):
        super().post_update()
        self._content_path = Path(self.content_dir)
        self._csv_path = self._content_path / self.csv_name

    def update_community_credits(self):

        reports = {}

        # with open('rep_json.txt', mode='r', encoding='utf-8') as f:
        #    reports = json.loads(f.readline())

        crowdin = UECrowdinClient(
            self.token, logger, self.organization, self.project_id
        )

        reports = crowdin.get_top_translators()

        logger.info('Got the reports from Crowdin. Processing...')

        fields = []
        rows = []

        with open(
            self._csv_path, mode='r', encoding=self.csv_encoding, newline=''
        ) as csv_file:
            csv_reader = csv.reader(csv_file)
            fields = next(csv_reader)

        for lang, report in reports.items():
            if not report['data'] or (
                self.languages_to_exclude and lang in self.languages_to_exclude
            ):
                continue

            users = [
                {
                    'name': user['user']['fullName'],
                    'translated': user['translated'],
                    'approved': user['approved'],
                }
                for user in report['data']
                if (
                    self.users_to_exclude
                    and user['user']['username'] not in self.users_to_exclude
                )
                and (
                    user['translated'] > self.translation_threshold
                    or user['approved'] > self.review_threshold
                )
            ]

            if not users:
                continue

            users.sort(
                reverse=True,
                key=lambda user: user['approved'] * 10 + user['translated']
                if user['approved'] > 0
                else user['translated'],
            )

            users_string = ''
            num_users = 0

            for u in users:

                # TODO: Move to config file
                # TODO: Extract into a function
                # ----- ----- ----- ----- -----
                # Special treatment to avoid some oddities due to mistakes and to add some people
                if lang != 'locale' and u['name'] == 'user_name':
                    continue
                # ----- ----- ----- ----- -----

                if num_users % 4 != 0:
                    users_string += ', '
                elif num_users > 0 and num_users % 4 == 0 and num_users < len(users):
                    users_string += ',\r\n'
                users_string += re.sub(r'[^\w\d\(\)\-]', '', u['name'])
                num_users += 1

            if not users_string:
                continue

            # TODO: Move to config file somehow?..
            if lang == 'en-shax':
                users_string += ', and greeny for the initial script :)'

            logger.info(
                f'{report["language_name"]} ({report["language_id"]}): {users_string}'
            )

            rows.append(
                [
                    report['language_id'],
                    report['language_name'],
                    users_string,
                ]
            )

        rows.sort(key=lambda x: x[0])

        logger.info(f'Saving the reports to: {self._csv_path}')

        with open(
            self._csv_path, 'w', encoding=self.csv_encoding, newline=''
        ) as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(fields)
            csv_writer.writerows(rows)

        return True


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

    logger.info(
        '--- Create and process reports on Crowdin, create CSV for in-game credits ---'
    )

    task = UpdateCommunityCredits()

    task.read_config(Path(__file__).name, logger)

    result = task.update_community_credits()

    logger.info('--- Update community credits script end ---')

    if result:
        return 0

    return 1


if __name__ == "__main__":
    main()
