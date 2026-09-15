"""The reference commandlet reports its own failure count, so the verdict
leans on that rather than inferring success from an absence of errors.

Marker shapes here are taken from a real Rabbithole run: 22967 packages,
2 passes that matched no assets, 0 failures.
"""

import pytest

from tasks.ue_gather_references import (
    NO_ASSETS,
    PACKAGES_LOADED,
    PACKAGES_TO_LOAD,
    PROGRESS,
    GatherStringTableReferences,
)

import re


@pytest.fixture
def task():
    return GatherStringTableReferences()


# --------------------------- marker parsing --------------------------- #


def test_it_reads_the_package_count():
    line = 'LogGatherStringTableReferencesCommandlet: Display: Preparing to load 22967 packages...'

    assert re.search(PACKAGES_TO_LOAD, line).group(1) == '22967'


def test_it_reads_the_closing_line_with_its_failure_count():
    line = (
        'LogGatherStringTableReferencesCommandlet: Display: '
        'Loaded 22967 packages in 164.83 seconds. 0 failed.'
    )
    match = re.search(PACKAGES_LOADED, line)

    assert match.group(1) == '22967'
    assert match.group(2) == '164.83'
    assert match.group(3) == '0'


def test_it_reads_progress_percentages():
    line = "Display: [ 43.15%] Loading package: '/Game/RH_Interactables/Foo'..."

    assert re.search(PROGRESS, line).group(1) == '43.15'


def test_it_recognises_a_pass_that_matched_nothing():
    line = 'LogGatherStringTableReferencesCommandlet: Warning: No assets matched the specified criteria.'

    assert re.search(NO_ASSETS, line)


def test_gathertext_markers_are_not_mistaken_for_these():
    """The two commandlets share no marker vocabulary; nothing from GatherText
    should trip these patterns."""
    for line in (
        "LogGatherTextCommandlet: Display: Beginning GatherText Commandlet for 'Game'",
        'LogGatherTextCommandlet: Display: Executing GatherTextStep0: GatherTextFromAssetsCommandlet',
        'LogInit: Display: GatherText completed with exit code 0',
    ):
        assert not re.search(PACKAGES_TO_LOAD, line)
        assert not re.search(PACKAGES_LOADED, line)
        assert not re.search(PROGRESS, line)


# --------------------------- the verdict --------------------------- #


def test_a_clean_run_succeeds(task):
    assert task.verdict(0, 22967, 22967, 0, no_assets=2, duration=204.0) is True


def test_a_nonzero_exit_code_fails(task):
    assert task.verdict(1, 22967, 22967, 0, no_assets=0, duration=1.0) is False


def test_failed_packages_warn_but_do_not_fail_the_task(task):
    """A big project always has a few packages that will not load. The
    gather still produced references for every other package, so the run is
    usable."""
    assert task.verdict(0, 22967, 22967, 12, no_assets=0, duration=1.0) is True


def test_never_reaching_the_closing_line_fails(task):
    """Exit code 0 alone is not enough: the commandlet can stop before it
    starts gathering."""
    assert task.verdict(0, 22967, None, None, no_assets=0, duration=1.0) is False


def test_loading_fewer_packages_than_planned_warns_but_passes(task):
    assert task.verdict(0, 22967, 22000, 0, no_assets=0, duration=1.0) is True


def test_passes_matching_no_assets_are_not_a_failure(task):
    """Rabbithole keeps its strings in assets, so the source pass finds
    nothing on every run."""
    assert task.verdict(0, 100, 100, 0, no_assets=2, duration=1.0) is True


# --------------------------- log filtering --------------------------- #


def test_live_coding_chatter_is_skipped_by_default(task):
    line = (
        'LogLiveCodingServer: Warning: No PDB file found for module '
        'IntoTheUnwellEditor-Core.dll.'
    )

    assert any(skip in line for skip in task.log_to_skip)


def test_commandlet_output_is_not_skipped(task):
    line = 'LogGatherStringTableReferencesCommandlet: Display: Discovering assets to gather...'

    assert not any(skip in line for skip in task.log_to_skip)


def test_building_the_task_survives_a_missing_project(tmp_path):
    """--check builds every task just to validate config, so this has to
    work on a machine where the project is not checked out."""
    task = GatherStringTableReferences()
    task.project_dir = str(tmp_path / 'nowhere')
    task.engine_dir = str(tmp_path / 'nowhere')

    task.post_update()  # must not raise

    assert task.run() is False
