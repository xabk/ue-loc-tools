"""Upload a CSV source file to the test project, read it back, clean up.

Everything happens inside a branch that is deleted afterwards, so a failed run
leaves at most one stale branch and never touches the project's real content.

The CSV shape mirrors what update-source-files uploads today:
    identifier,source_phrase,translation,max_length,labels,context
with the header row skipped, as in the generated Crowdin CLI config.

Keep these small. A handful of rows is enough to pin how Crowdin parses a
scheme; uploading real project files to prove the same thing would spam a
service we do not own. Anything heavier than this belongs in a deliberate
one-off run, not in a suite people run on a whim.

Run with:  uv run --extra test python -m pytest -m crowdin
"""

import csv
import urllib.request

import pytest

from conftest import TEST_PROJECT_ID

pytestmark = pytest.mark.crowdin

BRANCH = 'loctools-selftest'
SCHEME = {
    'identifier': 0,
    'sourcePhrase': 1,
    'translation': 2,
    'maxLength': 3,
    'labels': 4,
    'context': 5,
}
ROWS = [
    ('Key', 'SourceString', 'TargetString', 'MaxLength', 'Labels', 'Context'),
    ('UI,Continue', 'Continue', '', '', '', 'Button on the pause menu'),
    ('UI,Quit', 'Quit to desktop', '', '20', 'ui', 'Confirmation dialog'),
    ('Dialogue,Greeting', 'Hello, {PlayerName}!', '', '', '', 'Has a variable'),
]


def delete_branch_if_present(crowdin):
    branches = crowdin.source_files.list_project_branches(projectId=TEST_PROJECT_ID)['data']
    for item in branches:
        if item['data']['name'] == BRANCH:
            crowdin.source_files.delete_branch(
                projectId=TEST_PROJECT_ID, branchId=item['data']['id']
            )


@pytest.fixture
def branch(crowdin):
    delete_branch_if_present(crowdin)
    created = crowdin.source_files.add_branch(projectId=TEST_PROJECT_ID, name=BRANCH)
    yield created['data']
    delete_branch_if_present(crowdin)


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / 'SelfTest.csv'
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f, quoting=csv.QUOTE_ALL).writerows(ROWS)
    return path


def upload(crowdin, csv_file, branch_id):
    with open(csv_file, mode='rb') as f:
        storage = crowdin.storages.add_storage(f)

    return crowdin.source_files.add_file(
        projectId=TEST_PROJECT_ID,
        storageId=storage['data']['id'],
        branchId=branch_id,
        name=csv_file.name,
        type='csv',
        importOptions={'firstLineContainsHeader': True, 'scheme': SCHEME},
        exportOptions={'exportPattern': '/%file_name%/%locale%/%original_file_name%'},
    )['data']


def test_a_csv_uploads_and_comes_back(crowdin, csv_file, branch):
    uploaded = upload(crowdin, csv_file, branch['id'])

    assert uploaded['name'] == 'SelfTest.csv'
    assert uploaded['branchId'] == branch['id']

    listed = crowdin.source_files.list_files(
        projectId=TEST_PROJECT_ID, branchId=branch['id']
    )['data']
    assert [item['data']['name'] for item in listed] == ['SelfTest.csv']

    url = crowdin.source_files.download_file(
        projectId=TEST_PROJECT_ID, fileId=uploaded['id']
    )['data']['url']
    with urllib.request.urlopen(url) as response:
        downloaded = response.read().decode('utf-8-sig')

    assert 'Hello, {PlayerName}!' in downloaded
    assert downloaded.splitlines()[0].startswith('"Key"')


def test_the_scheme_turns_rows_into_strings(crowdin, csv_file, branch):
    """The scheme is what makes column 0 the key and column 1 the source: get
    it wrong and Crowdin silently imports the wrong column as the string."""
    upload(crowdin, csv_file, branch['id'])

    strings = crowdin.source_strings.list_strings(
        projectId=TEST_PROJECT_ID, branchId=branch['id']
    )['data']
    by_identifier = {s['data']['identifier']: s['data'] for s in strings}

    assert len(strings) == len(ROWS) - 1, 'header row should not become a string'
    assert by_identifier['UI,Continue']['text'] == 'Continue'
    assert by_identifier['UI,Quit']['maxLength'] == 20
    # Crowdin composes context for a CSV import as three lines: the
    # identifier, the context column, and the source cell's position
    context = by_identifier['Dialogue,Greeting']['context'].splitlines()
    assert context[0] == 'Dialogue,Greeting'
    assert context[1] == 'Has a variable'
    assert context[2] == 'row_4:col_b'


def test_the_export_pattern_is_kept(crowdin, csv_file, branch):
    uploaded = upload(crowdin, csv_file, branch['id'])

    stored = crowdin.source_files.get_file(
        projectId=TEST_PROJECT_ID, fileId=uploaded['id']
    )['data']

    assert stored['exportOptions']['exportPattern'] == (
        '/%file_name%/%locale%/%original_file_name%'
    )
