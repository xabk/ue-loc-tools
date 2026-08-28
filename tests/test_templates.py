"""The shipped templates must load and drive every task, on a bare clone.

No project config is read here: everything comes from templates/, so these
tests pass in a fresh checkout with no base.config.yaml at the root.
"""

import re
from dataclasses import fields

import pytest
import yaml

from conftest import NON_TASK_SECTIONS, write_config
from libraries.task_runner import TaskRunner
from libraries.utilities import LocTask


def test_templates_register_tasks(runner):
    assert runner.list_task_metadata(), 'no tasks registered from the template'


def test_registered_tasks_are_loctasks(runner, config):
    for name in config['tasks']:
        task_class = runner._task_registry.get(name)
        assert task_class is not None, f'{name} in tasks: but not registered'
        assert issubclass(task_class, LocTask), f'{name} is not a LocTask'


def test_script_parameters_keys_are_real_fields(runner, config):
    unknown = {}
    for name, params in (config.get('script-parameters') or {}).items():
        if name in NON_TASK_SECTIONS:
            continue
        task_class = runner._task_registry[name]
        known = {f.name for f in fields(task_class())}
        extra = sorted(k for k in (params or {}) if k not in known)
        if extra:
            unknown[name] = extra
    assert not unknown, f'config keys matching no dataclass field: {unknown}'


def test_task_list_scripts_are_registered(runner, task_lists):
    for list_name, tasks in task_lists.items():
        for task in tasks:
            script = task.get('script')
            assert script in runner._task_registry, (
                f'"{list_name}" refers to unregistered task "{script}"'
            )


def test_every_task_instance_builds(runner, task_lists):
    for list_name, tasks in task_lists.items():
        for task in tasks:
            runner.create_task_instance(task['script'], task)


def test_task_list_overrides_reach_the_task(runner, task_lists):
    checked = 0
    for tasks in task_lists.values():
        for task in tasks:
            for key, value in (task.get('script-parameters') or {}).items():
                instance = runner.create_task_instance(task['script'], task)
                if hasattr(instance, key):
                    assert getattr(instance, key) == value
                    checked += 1
    assert checked, 'no task-list overrides were exercised'


def test_tasks_build_from_a_minimal_project_config(config, tmp_path):
    """A project config that sets only loc_targets must not crash a task.

    Fields defaulting to None used to be unpacked or iterated directly, which
    only showed up in projects whose config was narrower than this repo's.
    """
    base = write_config(
        tmp_path / 'base.config.yaml',
        {'tasks': config['tasks'], 'parameters': {'loc_targets': ['Game']}},
    )
    secret = write_config(
        tmp_path / 'crowdin.config.yaml',
        {'crowdin': {'organization': '', 'token': 'x', 'project_id': 1}},
    )

    runner = TaskRunner()
    runner.unattended = True
    runner.load_config(str(base), str(secret))

    for name in config['tasks']:
        runner.create_task_instance(name, {'script': name, 'script-parameters': None})


def test_reimport_assets_section_parses(repo_root):
    """Mirrors the parser in scripts/ue-reimport-assets.py, which reads the
    config line by line and needs `assets_to_reimport: [` on a single line."""
    lines = (repo_root / 'templates' / 'base.config.yaml').read_text(
        encoding='utf-8'
    ).splitlines()

    assets, i, in_section = [], 0, False
    while i < len(lines):
        if not in_section and re.match(r'\s*ue-reimport-assets:.*', lines[i]):
            i += 1
            if i < len(lines) and re.match(
                r'\s*assets_to_reimport: \[.*', lines[i]
            ):
                in_section = True
                i += 1
                continue
        if not in_section:
            i += 1
            continue
        if re.match(r'\s*].*', lines[i]):
            break
        asset = re.search(r'(?<=")[^"]*(?=",?$)', lines[i].strip())
        assert asset, f'unparsable line in the section: {lines[i]!r}'
        assets.append(asset.group())
        i += 1

    assert in_section, 'parser never entered the ue-reimport-assets section'
    assert assets, 'section parsed but yielded no assets'


def test_section_lookup_accepts_the_module_name(monkeypatch, repo_root):
    """read_config is called with the module filename (test_lang.py) while the
    config section is hyphenated (test-lang)."""
    from tasks.test_lang import ProcessTestAndHashLocales

    monkeypatch.setattr('sys.argv', ['test_lang.py'])
    template = repo_root / 'templates' / 'base.config.yaml'
    expected = yaml.safe_load(template.read_text(encoding='utf-8'))
    expected = expected['script-parameters']['test-lang']

    task = ProcessTestAndHashLocales()
    task.read_config('test_lang.py', str(template))

    assert task.id_length == expected['id_length']
    assert task.hash_locale == expected['hash_locale']


@pytest.mark.parametrize('name', ['base.config.yaml', 'crowdin.config.yaml'])
def test_templates_are_valid_yaml(repo_root, name):
    loaded = yaml.safe_load((repo_root / 'templates' / name).read_text(encoding='utf-8'))
    assert isinstance(loaded, dict) and loaded
