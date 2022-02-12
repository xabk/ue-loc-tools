from crowdin_api import CrowdinClient
from time import sleep
import urllib.request
import json
import re
from pathlib import Path


class UECrowdinClient(CrowdinClient):
    def __init__(
        self,
        token: str,
        logger=None,
        organization: str = None,
        project_id: int = None,
        silent: bool = False,
    ):
        super().__init__()
        if not token:
            raise Exception(
                'No API token specified for Crowdin. '
                'Please check your config files and/or scripts to specify one.'
            )
        self.TOKEN = token

        if logger:
            self.info = logger.info
            self.warning = logger.warning
            self.error = logger.error
            self.info('Crowdin module: Logger initialized')

        if organization:
            self.ORGANIZATION = organization
        if project_id:
            self.project_id = project_id
        self.silent = silent

        self.file_list = None
        self.data = dict()

    def info(self, message: str, *args, **kwargs):
        if self.silent:
            return
        print('INFO     | ', message, args, kwargs)

    def warning(self, message: str, *args, **kwargs):
        if self.silent:
            return
        print('WARNING  | ', message, args, kwargs)

    def error(self, message: str, *args, **kwargs):
        if self.silent:
            return
        print('ERROR    | ', message, *args, kwargs)

    def get_file_ID(self, file_name='Game.po') -> int:
        if not self.file_list:
            self.error('File list not initialized.')
            return None

        for entry in self.file_list:
            if entry['data']['name'] == file_name:
                return entry['data']['id']

        self.warning(
            f'Couldn\'t find the file: {file_name}. File list: {self.file_list}'
        )
        return None

    def update_file_list_and_project_data(self):

        self.file_list = self.source_files.list_files(self.project_id).get('data', None)

        self.data['project_data'] = self.projects.get_project(self.project_id).get(
            'data', None
        )

        # TODO: make sure we get all languages via pagination
        self.data['supported_languages'] = self.languages.list_supported_languages(
            limit=500
        ).get('data', None)

        if (
            self.file_list
            and self.data['project_data']
            and self.data['supported_languages']
        ):
            self.info('Crowdin module: fetched file list and project data')
        else:
            self.warning(
                f'Crowdin module: somethings wrong with file list and project data\n'
                f'File list: {self.file_list}\n'
                f'Project data: {self.data["project_data"]}\n'
            )

        return None

    def check_or_build(self, build_data: dict = None):
        if not build_data:
            return self.translations.build_crowdin_project_translation(self.project_id)[
                'data'
            ]
        if not 'id' in build_data:
            self.error(f'No build ID in build data. Build data:\n{build_data}')
            return None

        return self.translations.download_project_translations(
            self.project_id, build_data['id']
        )['data']

    def add_file(self, filepath: Path, type='auto'):
        with open(filepath, mode='rb') as file:
            storage = self.storages.add_storage(file)

        if 'data' not in storage or 'id' not in storage['data']:
            self.error(f'Error, no storage ID recieved. Response:\n{storage}')
            return storage

        self.info(f'{filepath.name} uploaded to storage. Updating file...')

        response = self.source_files.add_file(
            self.project_id, storage['data']['id'], filepath.name, type=type
        )

        if not 'data' in response:
            self.error(f'No data in response. Response:\n{response}')
            return response

        return None

    def update_file(self, filepath: Path, fname: str = None, fID: int = None):
        if fname:
            file_name = fname
        else:
            file_name = filepath.name

        if not fID:
            file_id = self.get_file_ID(file_name=file_name)
        else:
            file_id = fID

        file_data = self.source_files.get_file(self.project_id, file_id)

        if not 'revisionId' in file_data['data']:
            self.error(
                f'No revision ID for {file_name} ({file_id}) found. File data:\n',
                file_data,
            )
            return file_data

        self.info(
            f'Current revision: {file_data["data"]["revisionId"]}. Uploading file...'
        )

        with open(filepath, mode='rb') as file:
            storage = self.storages.add_storage(file)

        if 'data' not in storage or 'id' not in storage['data']:
            self.error(f'Error, no storage ID recieved. Response:\n{storage}')
            return storage

        self.info('Uploaded to storage. Updating file...')

        response = self.source_files.update_file(
            self.project_id, file_id, storage['data']['id']
        )

        if not 'data' in response or not 'revisionId' in response['data']:
            self.error(
                f'No data or revision ID in updated file data. Response:\n{response}'
            )
            return response

        if response['data']['revisionId'] > file_data['data']['revisionId']:
            self.info(
                f'{file_name} ({file_id}) updated. '
                f'Revision: {file_data["data"]["revisionId"]} → '
                f'{response["data"]["revisionId"]}'
            )
            return True

        self.warning(
            f'{file_name} ({file_id}) updated but revision number hasn\'t changed. '
            f'Revision: {file_data["data"]["revisionId"]} → '
            f'{response["data"]["revisionId"]}'
        )

        return True

    def get_top_translators(self):

        self.update_file_list_and_project_data()

        language_ids = self.data['project_data']['targetLanguageIds']

        reports = dict.fromkeys(sorted(language_ids))
        # TODO: make this a parameter instead of hardcoded EN locale
        reports.pop('en', None)

        reports_count = 0

        self.info('Creating per-language reports on Crowdin...')

        for report in reports:

            reports[report] = {}

            reports[report]['report_id'] = self.reports.generate_top_members_report(
                self.project_id, languageId=report, format='json'
            )['data']['identifier']
            reports_count += 1

        self.info(
            f'Reports created: {str(reports_count)}. Pulling statuses and downloading...'
        )

        reports_count = 0

        while reports_count < len(reports):
            for report in reports:
                if 'data' in reports[report]:
                    continue

                report_status = self.reports.check_report_generation_status(
                    self.project_id, reports[report]['report_id']
                )['data']

                if report_status['status'] != 'finished':
                    continue

                reports_count += 1

                self.info(f'Report ready. Downloading... Language: {report}')

                with urllib.request.urlopen(
                    self.reports.download_report(
                        self.project_id, reports[report]['report_id']
                    )['data']['url']
                ) as data:
                    rep = json.loads(data.read().decode())
                    self.info(
                        f'Downloaded report for culture: {rep["language"]["name"]}'
                    )
                    reports[report]['language_id'] = 'CreditsLang' + re.sub(
                        r'[^\w]', '', rep['language']['name']
                    )
                    reports[report]['language_name'] = re.sub(
                        r',', '', re.sub(r', (.*)$', r' (\1)', rep['language']['name'])
                    )
                    if 'data' in rep:
                        reports[report]['data'] = rep['data']
                    else:
                        reports[report]['data'] = None
                        self.warning(
                            f'*** No data for culture: {rep["language"]["name"]}'
                        )

            if reports_count < len(reports):
                self.info(
                    f'Waiting for more reports to be ready... {len(reports) - reports_count}'
                )
                sleep(5)

        return reports

    def get_completion_rates(self, filename='Game.po'):

        if not self.data:
            self.update_file_list_and_project_data()

        project_data = self.data['project_data']
        language_ids = project_data['targetLanguageIds']
        supported_languages = self.data['supported_languages']

        language_locales = {
            e['data']['id']: e['data']['locale']
            for e in supported_languages
            if e['data']['id'] in language_ids
        }
        language_mappings = dict(zip(language_ids, language_ids))
        for m in language_mappings:
            if m in project_data['languageMapping']:
                language_mappings[m] = project_data['languageMapping'][m]['locale']
            elif m in language_locales:
                language_mappings[m] = language_locales[m]

        self.info(f'Language IDs ({len(language_ids)}): {language_ids}')
        self.info(f'Language mappings ({len(language_mappings)}): {language_mappings}')

        game_po_id = self.get_file_ID(filename)

        if not game_po_id:
            self.error(f'Couldn\'t find {filename}, aborting. Response: {game_po_id}')
            return None

        game_po_progress = self.translation_status.get_file_progress(
            projectId=self.project_id, fileId=game_po_id, offset=0, limit=100
        )['data']

        completion_rates = {}

        for lang in game_po_progress:
            data = lang['data']['words']
            data.update(
                {
                    'translationProgress': lang['data']['translationProgress'],
                    'approvalProgress': lang['data']['approvalProgress'],
                }
            )
            completion_rates[language_mappings[lang['data']['languageId']]] = data

        return completion_rates


def main():
    print('Import me!')


# Run the script if the isn't imported
if __name__ == "__main__":
    main()
