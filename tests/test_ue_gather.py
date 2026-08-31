"""How a UE run is judged.

Unreal exits 1 whenever anything logged an error, so a gather that wrote every
file correctly is reported as failed if an unrelated asset misbehaved. The
commandlet prints its own verdict, and that is the signal worth trusting.

A run has two nesting levels. Per config (one per target x task):
    Beginning GatherText Commandlet for '.../RH_MainRelease_Gather.ini'
and per step inside it:
    Executing  GatherTextStep0: GatherTextFromAssetsCommandlet
    Completed  GatherTextStep0: GatherTextFromAssetsCommandlet in 264.87 seconds
with a single verdict for the whole engine run at the end. A crash leaves the
counts unbalanced, which is what catches a run that stopped part way through
and still claimed success.
"""

import re

import pytest

from tasks.ue_loc_gather_cmd import (
    COMMANDLET_VERDICT,
    CONFIG_STARTED,
    STEP_COMPLETED,
    STEP_STARTED,
    UnrealLocGatherCommandlet,
)

# 2 targets x 2 tasks = 4 configs, as in the captured gather run
FULL_RUN = {'configs_started': 4, 'steps_started': 10, 'steps_completed': 10}


@pytest.fixture
def task():
    task = UnrealLocGatherCommandlet()
    task.loc_targets = ['RH_MainRelease', 'RH_StringTables']
    task.tasks = ['Gather', 'Export']
    return task


def test_real_log_lines_are_recognised():
    assert re.search(
        COMMANDLET_VERDICT,
        'LogGatherTextCommandlet: Display: GatherText completed with exit code 0',
    )
    assert re.search(
        CONFIG_STARTED,
        "LogGatherTextCommandlet: Display: Beginning GatherText Commandlet for "
        "'../../Config/Localization/RH_MainRelease_Gather.ini'",
    )
    assert re.search(
        STEP_STARTED,
        'LogGatherTextCommandlet: Display: Executing GatherTextStep0: '
        'GatherTextFromAssetsCommandlet',
    )
    assert re.search(
        STEP_COMPLETED,
        'LogGatherTextCommandlet: Display: Completed GatherTextStep0: '
        'GatherTextFromAssetsCommandlet in 264.87 seconds',
    )


def test_negative_exit_codes_are_recognised():
    line = 'GatherText completed with exit code -1'
    assert int(re.search(COMMANDLET_VERDICT, line).group(1)) == -1


def test_the_ue4_error_count_line_is_not_treated_as_a_verdict():
    """`Success - 0 error(s)` is LogInit counting logged errors, which is the
    weak signal this logic exists to stop trusting."""
    line = 'LogInit: Display: Success - 0 error(s), 0 warning(s)'
    assert re.search(COMMANDLET_VERDICT, line) is None


def test_a_complete_run_passes(task):
    assert task.task_succeeded(0, [0], 0, **FULL_RUN) is True


def test_unrelated_errors_do_not_fail_a_complete_run(task):
    assert task.task_succeeded(1, [0], 11, **FULL_RUN) is True


def test_a_failing_verdict_fails(task):
    assert task.task_succeeded(0, [2], 0, **FULL_RUN) is False


def test_one_failing_verdict_among_many_fails(task):
    assert task.task_succeeded(0, [0, 0, 2, 0], 0, **FULL_RUN) is False


def test_no_verdict_passes_on_a_complete_run(task):
    """UE 4.27 prints no verdict line, so its absence cannot mean failure.
    A complete run with a clean exit is accepted on its own accounting."""
    assert task.task_succeeded(0, [], 0, **FULL_RUN) is True


def test_no_verdict_fails_when_unreal_exits_nonzero(task):
    assert task.task_succeeded(1, [], 0, **FULL_RUN) is False


def test_no_verdict_fails_on_an_incomplete_run(task):
    assert (
        task.task_succeeded(
            0, [], 0, configs_started=3, steps_started=8, steps_completed=8
        )
        is False
    )
    assert (
        task.task_succeeded(
            0, [], 0, configs_started=4, steps_started=10, steps_completed=9
        )
        is False
    )


def test_no_verdict_and_nothing_ran_fails(task):
    """Unreal failing to start leaves a clean exit and no accounting at all."""
    assert task.task_succeeded(0, [], 0) is False


def test_a_config_that_never_started_fails(task):
    """Crashed after finishing three of the four configs, then reported 0."""
    assert (
        task.task_succeeded(
            0, [0], 0, configs_started=3, steps_started=8, steps_completed=8
        )
        is False
    )


def test_a_step_that_never_finished_fails(task):
    """Crashed inside the fourth config: it began, but a step never returned."""
    assert (
        task.task_succeeded(
            0, [0], 0, configs_started=4, steps_started=10, steps_completed=9
        )
        is False
    )


def test_more_configs_than_expected_is_not_a_failure(task):
    task.loc_targets = ['RH_MainRelease']
    assert task.task_succeeded(0, [0], 0, **FULL_RUN) is True


def test_opting_out_trusts_the_process_code_again(task):
    task.trust_commandlet_exit_code = False
    assert task.task_succeeded(0, [], 0) is True
    assert task.task_succeeded(1, [0], 11, **FULL_RUN) is False
