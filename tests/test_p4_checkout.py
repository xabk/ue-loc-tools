"""p4-checkout with a fake P4, to cover the code past the connection.

A project config that names only loc_targets is normal, and the None-valued
fields it leaves behind are only reached inside checkout_assets, so building
the task is not enough to catch them.
"""

import pytest

from conftest import write_config
from libraries.task_runner import TaskRunner


class FakeP4:
    def __init__(self):
        self.port = self.user = self.client = None
        self.commands = []

    def connect(self):
        return self

    def disconnect(self):
        return None

    def run(self, *args):
        self.commands.append(args)
        return []


@pytest.fixture
def checkout_task(config, tmp_path, monkeypatch):
    content = tmp_path / 'Content'
    (content / 'Localization' / 'Game' / 'io').mkdir(parents=True)
    (content / 'Localization' / 'Game' / 'io' / 'Game.po').write_text('#', encoding='utf-8')

    saved = tmp_path / 'Saved'
    saved.mkdir()
    (saved / 'p4.ini').write_text(
        '[PerforceSourceControl.PerforceSourceControlSettings]\n'
        'Port=example:1666\nUserName=tester\nWorkspace=test_client\n',
        encoding='utf-8',
    )

    base = write_config(
        tmp_path / 'base.config.yaml',
        {
            'tasks': config['tasks'],
            'parameters': {'loc_targets': ['Game'], 'content_dir': str(content)},
            'script-parameters': {
                'p4-checkout': {'config_name': '../Saved/p4.ini'},
            },
        },
    )
    secret = write_config(
        tmp_path / 'crowdin.config.yaml',
        {'crowdin': {'organization': '', 'token': 'x', 'project_id': 1}},
    )

    runner = TaskRunner()
    runner.unattended = True
    runner.load_config(str(base), str(secret))

    fake = FakeP4()
    monkeypatch.setattr('tasks.p4_checkout.P4', lambda: fake)

    task = runner.create_task_instance('p4-checkout', {'script': 'p4-checkout'})
    return task, fake


def test_checkout_runs_without_csv_loc_targets(checkout_task):
    task, fake = checkout_task
    assert task.csv_loc_targets is None

    assert task.checkout_assets() is not False
    assert fake.commands, 'no p4 command was issued'


def test_checkout_opens_the_target_files(checkout_task):
    task, fake = checkout_task
    task.checkout_assets()

    opened = [str(path) for command in fake.commands for path in command[1]]
    assert any(name.endswith('Game.po') for name in opened), opened
