"""Checking the top-level `parameters:` section.

Anything there that the runner does not read itself is a default handed to the
tasks, so it has to name a field on one of them. A key that names nothing is
inert, and inert settings are the expensive kind: the config says one thing and
the run does another, silently. Four turned up in one week -- a renamed field, a
misspelled one, a filter that never matched, and p4-checkout, which every
project sets and nothing reads.
"""

import importlib.util
from dataclasses import dataclass, field

import pytest
from loguru import logger


def load_module(repo_root):
    path = repo_root / 'loc-project.py'
    spec = importlib.util.spec_from_file_location('loc_project', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='session')
def gc(repo_root):
    return load_module(repo_root)


@pytest.fixture
def logged():
    captured = []
    sink_id = logger.add(lambda m: captured.append(m.record), level='DEBUG')
    yield captured
    logger.remove(sink_id)


def messages(records) -> str:
    return chr(10).join(r['message'] for r in records)


@dataclass
class FakeTask:
    loc_targets: list = field(default_factory=list)
    content_dir: str = '../'
    encoding: str = 'utf-8-sig'


class FakeRunner:
    def __init__(self):
        self._task_registry = {'fake-task': FakeTask}


def check(gc, parameters):
    return gc.check_parameters(FakeRunner(), {'parameters': parameters})


# --- keys that are fine


def test_a_key_that_names_a_task_field_is_accepted(gc):
    assert check(gc, {'loc_targets': ['Game'], 'content_dir': '../../'}) == 0


def test_the_keys_the_runner_reads_itself_are_accepted(gc):
    assert check(gc, {'stop-on-errors': True, 'use-unreal': True}) == 0


def test_an_underscore_key_is_left_alone(gc):
    """Projects declare a target list once under an underscore key and refer to
    it from several task lists with a YAML anchor. It is not a setting."""
    assert check(gc, {'_base_targets': ['A', 'B']}) == 0


def test_an_empty_section_is_fine(gc):
    assert check(gc, {}) == 0


# --- keys that are not


def test_a_key_that_names_nothing_is_a_problem(gc):
    assert check(gc, {'not_a_field': 1}) == 1


def test_every_unknown_key_is_counted(gc):
    assert check(gc, {'nope': 1, 'also_nope': 2}) == 2


def test_a_near_miss_is_named_in_the_message(gc, logged):
    """cli_sources_dir vs cli_source_dir cost a real project a setting that
    had never once taken effect."""
    check(gc, {'loc_target': ['Game']})

    assert 'did you mean "loc_targets"' in messages(logged)


# --- accepted but not implemented


def test_the_unimplemented_keys_do_not_fail_the_check(gc):
    """They are in every project's config and in the template, two of them
    carrying a TODO. Failing on them would fail every project."""
    assert check(gc, {'p4-checkout': True, 'p4-checkin': False}) == 0


def test_the_unimplemented_keys_are_still_reported(gc, logged):
    check(gc, {'p4-checkout': True})

    reported = messages(logged)
    assert 'not implemented' in reported and 'p4-checkout' in reported


def test_a_real_problem_is_still_found_alongside_them(gc):
    assert check(gc, {'p4-checkout': True, 'not_a_field': 1}) == 1
