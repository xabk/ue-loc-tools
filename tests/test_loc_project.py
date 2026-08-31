"""loc-project is the first step of any upgrade, so its exit codes matter."""

import importlib.util
import shutil

import pytest
import yaml

from conftest import TEMPLATE_BASE, TEMPLATE_SECRET


def load_module(repo_root):
    path = repo_root / 'loc-project.py'
    spec = importlib.util.spec_from_file_location('loc_project', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='session')
def gc(repo_root):
    return load_module(repo_root)


def test_init_scaffolds_the_project(gc, tmp_path):
    base = tmp_path / 'base.config.yaml'
    secret = tmp_path / 'crowdin.config.yaml'

    assert gc.do_init(base, secret) == 0

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == [
        '!loc-sync.bat',
        '.gitignore',
        'base.config.yaml',
        'crowdin.config.yaml',
        'sync-guide.md',
    ]


def test_the_scaffolded_bat_targets_the_submodule_layout(gc, tmp_path):
    gc.do_init(tmp_path / 'base.config.yaml', tmp_path / 'crowdin.config.yaml')

    bat = (tmp_path / '!loc-sync.bat').read_text(encoding='utf-8')
    assert 'cd /d "%~dp0"' in bat
    assert 'uv run --project loctools loctools/loc-sync.py' in bat


def test_the_scaffolded_gitignore_keeps_python_version(gc, tmp_path):
    """Ignoring .python-version makes uv resolve the wrong interpreter."""
    gc.do_init(tmp_path / 'base.config.yaml', tmp_path / 'crowdin.config.yaml')

    ignored = (tmp_path / '.gitignore').read_text(encoding='utf-8')
    assert 'crowdin.config.yaml' in ignored
    assert '.pytest_cache/' in ignored
    assert '\n.python-version' not in ignored


def test_init_refuses_to_overwrite(gc, tmp_path):
    base = tmp_path / 'base.config.yaml'
    secret = tmp_path / 'crowdin.config.yaml'
    base.write_text('mine: keep me', encoding='utf-8')

    assert gc.do_init(base, secret) == 1
    assert base.read_text(encoding='utf-8') == 'mine: keep me'
    assert not secret.exists()


def test_check_accepts_a_freshly_initialised_config(gc, tmp_path):
    base = tmp_path / 'base.config.yaml'
    secret = tmp_path / 'crowdin.config.yaml'
    gc.do_init(base, secret)

    assert gc.do_check(base, secret) == 0


def test_check_rejects_an_unknown_key(gc, tmp_path):
    base = tmp_path / 'base.config.yaml'
    secret = tmp_path / 'crowdin.config.yaml'
    shutil.copyfile(TEMPLATE_SECRET, secret)

    config = yaml.safe_load(TEMPLATE_BASE.read_text(encoding='utf-8'))
    config['script-parameters']['test-lang']['id_lenght'] = 5
    base.write_text(yaml.safe_dump(config), encoding='utf-8')

    assert gc.do_check(base, secret) == 1


def test_check_rejects_an_unknown_task_in_a_task_list(gc, tmp_path):
    base = tmp_path / 'base.config.yaml'
    secret = tmp_path / 'crowdin.config.yaml'
    shutil.copyfile(TEMPLATE_BASE, base)
    shutil.copyfile(TEMPLATE_SECRET, secret)
    base.write_text(
        base.read_text(encoding='utf-8')
        + "\n'[TEST] made up':\n  - description: 'x'\n    script: no-such-task\n",
        encoding='utf-8',
    )

    assert gc.do_check(base, secret) == 1


def test_upgrade_reports_no_differences_against_the_template(gc, tmp_path):
    base = tmp_path / 'base.config.yaml'
    shutil.copyfile(TEMPLATE_BASE, base)

    assert gc.do_upgrade(base) == 0


def test_upgrade_never_modifies_the_config(gc, tmp_path):
    base = tmp_path / 'base.config.yaml'
    shutil.copyfile(TEMPLATE_BASE, base)
    before = base.read_text(encoding='utf-8').replace('id_length: 5', 'id_length: 4')
    base.write_text(before, encoding='utf-8')

    gc.do_upgrade(base)

    assert base.read_text(encoding='utf-8') == before
