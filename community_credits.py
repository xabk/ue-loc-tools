import re
import csv
import crowdin
import json

# TODO: Use loguru for logging

# TODO: Add config file support
# TODO: Move parameters to config file

# ----------------------------------------------------------------------------------------------------
# Parameters - These can be edited

CSV_FILENAME = 'FactoryGame/Interface/UI/DT_Credits_Community.csv'  # Relative to Content the project directory
CSV_ENCODING = 'utf-16-le'


# List of people to exclude: pros, employees... and cheaters, if any
EXCLUSION_LIST = [
    '418ivan',
    'Aemiliali',
    'anyatuntiya',
    'ASondrio',
    'BeatrizLuque',
    'ceiss',
    'CSS_Stefan',
    'darkwingbollin',
    'deryad',
    'EdmeeS',
    'Fede__',
    'frenchLQA',
    'gameatnew',
    'grammmych',
    'h_jung',
    'iamcomingagain',
    'Inlingo',
    'Inlingo_PL2',
    'jembawls',
    'LiNeu',
    'm.s.esteban',
    'michprus',
    'Mohshiro',
    'NarumiT',
    'nunomiranda',
    'rlarjsdn122',
    'star_pan9292',
    'Taipeivienna',
    'thaisc',
    'ting.h',
    'xabk',
]

# List of languages to exclude ()
EXCLUDE_LANGUAGES = ['']


# How many words people should translate or approve to get into the credits
# It's better to keep the values once set, otherwise some older translators might be
# excluded from credits later on and it's not something we want
TRANSLATION_LIM = 12345
REVIEW_LIM = 12345

# ----------------------------------------------------------------------------------------------------


def update_community_credits(filename=CSV_FILENAME, encoding=CSV_ENCODING):

    reports = {}

    # with open('rep_json.txt', mode='r', encoding='utf-8') as f:
    #    reports = json.loads(f.readline())

    reports = crowdin.get_top_translators(crowdin.init_crowdin())

    print('Got the reports from Crowdin. Processing...')

    fields = []
    rows = []

    with open(filename, mode='r', encoding=encoding, newline='') as csv_file:
        csv_reader = csv.reader(csv_file)
        fields = next(csv_reader)

    for report in reports:
        if reports[report]['data'] == None or report in EXCLUDE_LANGUAGES:
            continue

        users = [
            {
                'name': u['user']['fullName'],
                'translated': u['translated'],
                'approved': u['approved'],
            }
            for u in reports[report]['data']
            if u['user']['username'] not in EXCLUSION_LIST
            and (u['translated'] > TRANSLATION_LIM or u['approved'] > REVIEW_LIM)
        ]

        if len(users) == 0:
            continue

        users.sort(
            reverse=True,
            key=lambda x: x['approved'] * 100000
            if x['approved'] > 0
            else x['translated'],
        )

        users_string = ''
        num_users = 0

        for u in users:

            # TODO: Move to config file
            # TODO: Extract into a function
            # ----- ----- ----- ----- -----
            # Special treatment to avoid some oddities due to mistakes and to add some people
            if report != 'locale' and u['name'] == 'user_name':
                continue
            # ----- ----- ----- ----- -----

            if num_users % 4 != 0:
                users_string += ', '
            elif num_users > 0 and num_users % 4 == 0 and num_users < len(users):
                users_string += ',\r\n'
            users_string += re.sub(
                r'[^\w/\\[]{}<>;:\?\+!@#$%^&\(\)=,_\.]', '', u['name']
            )
            num_users += 1

        if not users_string:
            continue

        # TODO: Move to config file somehow?..
        if report == 'en-shax':
            users_string += ', and greeny for the initial script :)'

        print(
            [
                reports[report]['language_id'],
                reports[report]['language_name'],
                users_string,
            ]
        )

        rows.append(
            [
                reports[report]['language_id'],
                reports[report]['language_name'],
                users_string,
            ]
        )

    rows.sort(key=lambda x: x[0])

    print('Saving the reports to: ' + filename)

    with open(filename, 'w', encoding=encoding, newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(fields)
        csv_writer.writerows(rows)

    with open('rep_json.txt', mode='w', encoding='utf-8') as f:
        f.write(json.dumps(reports))


def main():

    filename = '../' + CSV_FILENAME  # Assume we're in /Game/Content/Python directory

    update_community_credits(filename, CSV_ENCODING)


if __name__ == "__main__":
    main()
