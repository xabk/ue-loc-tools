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
        'update-loc-tools.bat',
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
def test_tasks_in_use_collects_scripts_from_every_task_list(gc):
    config = {
        'parameters': {'not': 'a list'},
        'list-one': [{'script': 'ue-loc-gather-cmd'}, {'script': 'p4-checkout'}],
        'list-two': [{'script': 'test-lang'}],
    }

    assert gc.tasks_in_use(config) == {
        'ue-loc-gather-cmd',
        'p4-checkout',
        'test-lang',
    }


def test_tasks_in_use_ignores_entries_without_a_script(gc):
    config = {'list': [{'no-script': 1}, 'a string', {'script': 'test-lang'}]}

    assert gc.tasks_in_use(config) == {'test-lang'}


def test_missing_unreal_binary_is_fatal(gc, tmp_path):
    assert gc.check_unreal_binary(tmp_path / 'UE4Editor-Cmd.exe') == 1


def test_unresolvable_unreal_binary_is_fatal(gc):
    assert gc.check_unreal_binary(None) == 1


def test_present_unreal_binary_passes(gc, tmp_path):
    binary = tmp_path / 'UE4Editor-Cmd.exe'
    binary.touch()

    assert gc.check_unreal_binary(binary) == 0


def test_missing_p4_settings_only_warns(gc, tmp_path):
    """The editor writes this file on first Perforce login, so a fresh machine
    not having it yet is expected rather than broken: no exit code."""
    assert gc.check_p4_settings(tmp_path / 'nope.ini') is None


def test_check_env_skips_tasks_the_project_never_runs(gc, tmp_path, monkeypatch):
    """A project with no UE gather in any task list must not be failed for
    lacking an editor binary."""
    called = []
    monkeypatch.setattr(gc, 'check_unreal_binary', lambda p: called.append(p) or 1)
    monkeypatch.setattr(
        gc,
        'load_for_checking',
        lambda b, s: (None, {'list': [{'script': 'test-lang'}]}),
    )

    assert gc.do_check_env(tmp_path / 'base.yaml', tmp_path / 'secret.yaml') == 0
    assert called == []


def test_every_template_reaches_the_project(gc, tmp_path):
    """A template nobody copies is a template nobody gets: update-loc-tools.bat
    sat in templates/ unscaffolded, so new projects had no install script.
    p4ignore-snippet.txt is the one exception: it is pasted into the
    p4ignore at the workspace root, which is outside the project."""
    templates = {p.name for p in gc.TEMPLATE_DIR.iterdir() if p.is_file()}
    scaffolded = set(
        gc.scaffold_map(
            tmp_path / 'base.config.yaml', tmp_path / 'crowdin.config.yaml'
        )
    )

    assert templates - scaffolded == {'p4ignore-snippet.txt'}
