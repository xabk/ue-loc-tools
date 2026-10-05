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
    STEP_FAILED,
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


def test_a_failed_step_is_recognised():
    line = (
        'LogGatherTextCommandlet: Error: '
        'GatherTextStep2-GenerateGatherManifestCommandlet reported an error.'
    )
    match = re.search(STEP_FAILED, line)
    assert match.group(1) == 'GatherTextStep2-GenerateGatherManifestCommandlet'


def test_a_failed_step_fails_even_when_the_counts_look_complete(task):
    assert (
        task.task_succeeded(0, [0], 0, **FULL_RUN, failed_step='GatherTextStep2-Foo')
        is False
    )


def captured(fn, *args, **kwargs):
    import loguru

    seen = []
    handle = loguru.logger.add(lambda m: seen.append(m), level='INFO')
    result = fn(*args, **kwargs)
    loguru.logger.remove(handle)
    return result, ''.join(seen)


def test_a_failed_step_names_itself_and_its_errors(task):
    _, said = captured(
        task.task_succeeded,
        -1,
        [],
        0,
        configs_started=1,
        steps_started=3,
        steps_completed=2,
        failed_step='GatherTextStep2-GenerateGatherManifestCommandlet',
        failed_step_errors=["Error: Failed to save manifest 'Game.manifest'."],
    )
    assert 'GatherTextStep2-GenerateGatherManifestCommandlet' in said
    assert "Failed to save manifest 'Game.manifest'" in said
    assert 'crash' not in said


# Lines from a real run that could not write a read-only manifest.
READ_ONLY_MANIFEST_RUN = [
    "[2026.10.05-13.07.42:000][  0]LogGatherTextCommandlet: Display: Beginning "
    "GatherText Commandlet for '../../../FactoryGame/Config/Localization/Game_Gather.ini'",
    '[  0]LogGatherTextCommandlet: Display: Executing GatherTextStep0: '
    'GatherTextFromSourceCommandlet',
    '[  0]LogGatherTextFromSourceCommandlet: Error: Unrelated error in step 0',
    '[  0]LogGatherTextCommandlet: Display: Completed GatherTextStep0: '
    'GatherTextFromSourceCommandlet in 18.86 seconds',
    '[  0]LogGatherTextCommandlet: Display: Executing GatherTextStep2: '
    'GenerateGatherManifestCommandlet',
    "[  0]LogInternationalizationManifestSerializer: Error: Failed to save "
    "manifest 'F:/sat-main/FactoryGame/Content/Localization/Game/Game.manifest'.",
    "[  0]LogGenerateManifestCommandlet: Error: Save error: Failed to serialize "
    "manifest 'F:/sat-main/FactoryGame/Content/Localization/Game/Game.manifest'.",
    '[  0]LogGatherTextCommandlet: Error: '
    'GatherTextStep2-GenerateGatherManifestCommandlet reported an error.',
    '[  0]LogInit: Display: Warning/Error Summary (Unique only)',
    '[  0]LogInit: Display: LogGatherTextCommandlet: Error: '
    'GatherTextStep9-SomethingElse reported an error.',
]


class FakeUnreal:
    def __init__(self, lines, returncode):
        self.stdout = iter(line + '\n' for line in lines)
        self.returncode = returncode

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def poll(self):
        return self.returncode


def test_a_run_that_could_not_save_says_so(task, monkeypatch):
    import tasks.ue_loc_gather_cmd as module

    monkeypatch.setattr(
        module.subp,
        'Popen',
        lambda *a, **k: FakeUnreal(READ_ONLY_MANIFEST_RUN, 4294967295),
    )
    task.loc_targets = ['Game']
    task.try_patch_dependencies = False
    task._unreal_binary_path = 'UnrealEditor-Cmd.exe'
    task._uproject_path = 'FactoryGame.uproject'

    succeeded, said = captured(task.run_tasks)

    assert succeeded is False
    # Up to the closing line: the findings report after it lists every error.
    verdict = said[
        said.index('GatherText failed at') : said.index('--- Unreal loc gather')
    ]
    assert 'GatherTextStep2-GenerateGatherManifestCommandlet' in verdict
    assert 'Failed to save manifest' in verdict
    assert 'Failed to serialize manifest' in verdict
    # Errors from an earlier step, and the recap, are not the reason.
    assert 'Unrelated error in step 0' not in verdict
    assert 'GatherTextStep9' not in verdict
    assert 'Check the log for a crash' not in said
