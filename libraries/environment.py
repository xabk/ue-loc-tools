"""What the project needs from the machine it runs on.

Both entry points use this: loc-project.py for its --check-env mode, and
loc-sync.py to warn at launch and to stop a task list before it starts work it
cannot finish. Keeping the resolution here means both agree on what counts as
"the Crowdin CLI is wrong" or "there is no editor binary".
"""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from loguru import logger

PYPROJECT = Path(__file__).resolve().parent.parent / 'pyproject.toml'

# winget is the only distribution channel we automate. The CLI ships as a
# portable exe, so winget puts it on PATH without an installer.
CROWDIN_WINGET_ID = 'Crowdin.CrowdinCLI'

UPDATE_SCRIPT = 'update-loc-tools.bat'

# Tasks that shell out to the editor. An entry flagged `unreal: True` runs
# through the editor's Python instead, and needs the same binary.
UE_TASKS = {'ue-loc-gather-cmd'}
P4_TASKS = {'p4-checkout'}
CLI_TASKS = {'update-source-files'}


# --------------------------- Crowdin CLI --------------------------- #


def pinned_crowdin_cli_version() -> str | None:
    """The version this release of the tools is tested against."""
    try:
        with open(PYPROJECT, 'rb') as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return (data.get('tool') or {}).get('loctools', {}).get('crowdin_cli_version')


def installed_crowdin_cli_version() -> str | None:
    if not shutil.which('crowdin'):
        return None
    try:
        result = subprocess.run(
            ['crowdin', '--version'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,
            stdin=subprocess.DEVNULL,
            shell=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().splitlines()[0].strip() if result.stdout else None


def _major_minor(version: str) -> tuple[int, int] | None:
    """Crowdin uses semver, and their previews look like 5.0.0-next.6, which
    packaging.version rejects. Only the leading numbers matter here."""
    match = re.match(r'(\d+)(?:\.(\d+))?', version.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def crowdin_cli_state(installed: str | None, pinned: str | None) -> str:
    """One of: no_pin, missing, match, patch, minor, major, unknown.

    A major difference is treated as breaking, a minor one as worth knowing
    about: that is the line between stopping a task list and warning about it.
    """
    if not pinned:
        return 'no_pin'
    if installed is None:
        return 'missing'
    if installed == pinned:
        return 'match'

    got, want = _major_minor(installed), _major_minor(pinned)
    if got is None or want is None:
        return 'unknown'
    if got[0] != want[0]:
        return 'major'
    if got[1] != want[1]:
        return 'minor'
    return 'patch'


# --------------------------- what a task list needs --------------------------- #


def task_list_needs(runner, tasks: list[dict]) -> set[str]:
    """Which of 'ue', 'p4', 'cli' the given task list actually exercises.

    The CLI answer depends on the effective config, so the task is built the
    way the runner would build it rather than reading the raw entry.
    """
    needs = set()
    for entry in tasks:
        if not isinstance(entry, dict):
            continue
        script = entry.get('script')

        if entry.get('unreal') or script in UE_TASKS:
            needs.add('ue')
        if script in P4_TASKS:
            needs.add('p4')
        if script in CLI_TASKS:
            try:
                task = runner.create_task_instance(script, entry)
            except Exception:
                # Assume it uses the CLI: a false warning beats missing one.
                needs.add('cli')
                continue
            if getattr(task, 'cli_upload', False) or getattr(
                task, 'add_files_only', False
            ):
                needs.add('cli')
    return needs


def resolved_task_path(runner, script: str, attr: str) -> Path | None:
    """Let the task work out its own paths rather than second-guessing config."""
    try:
        task = runner.create_task_instance(script, {})
    except Exception as err:
        logger.error(f'Could not set up {script} to check it: {err}')
        return None
    return getattr(task, attr, None)


# --------------------------- checks --------------------------- #


def report_crowdin_cli(state: str, installed: str | None, pinned: str | None,
                       blocking: bool) -> int:
    """Returns the number of problems. Only a missing CLI or a major version
    difference blocks; anything else is worth saying once and moving on."""
    if state in ('no_pin', 'match'):
        if state == 'match':
            logger.success(f'Crowdin CLI {installed} matches the pinned version.')
        return 0

    fatal = blocking and state in ('missing', 'major')
    say = logger.error if fatal else logger.warning

    if state == 'missing':
        say(
            f'Crowdin CLI not found on PATH. This task list uploads to Crowdin '
            f'and needs {pinned}. Run {UPDATE_SCRIPT} to install it.'
            if blocking
            else f'Crowdin CLI not found on PATH. Uploads need {pinned}. '
            f'Run {UPDATE_SCRIPT} to install it.'
        )
    elif state == 'major':
        say(
            f'Crowdin CLI is {installed}, but these tools are tested against '
            f'{pinned}: that is a different major version and the upload '
            f'commands may have changed. Run {UPDATE_SCRIPT}.'
        )
    elif state == 'unknown':
        say(
            f'Cannot compare Crowdin CLI {installed} with the pinned {pinned}. '
            f'Run {UPDATE_SCRIPT} if uploads misbehave.'
        )
    else:
        say(
            f'Crowdin CLI is {installed}, these tools are tested against '
            f'{pinned}. Run {UPDATE_SCRIPT} to line them up.'
        )

    return 1 if fatal else 0


def report_unreal_binary(path: Path | None, blocking: bool) -> int:
    """The editor binary is usually not in source control, so a fresh machine
    has none until someone builds it."""
    if path is not None and path.exists():
        logger.success(f'Unreal editor binary found: {path}')
        return 0

    say = logger.error if blocking else logger.warning
    where = f': {path}' if path else ''
    say(
        f'Unreal editor binary not found{where}. '
        + (
            'This task list gathers, exports, imports or compiles, all of which '
            'run through it. Build the editor, or fix engine_dir and '
            'unreal_binary in your config.'
            if blocking
            else 'Anything that gathers or compiles will fail. Build the editor, '
            'or fix engine_dir and unreal_binary in your config.'
        )
    )
    return 1 if blocking else 0


def report_p4_settings(path: Path | None, blocking: bool) -> int:
    """The editor writes this on first Perforce login and it is not in source
    control, so a fresh machine will not have it yet. A project that checks
    files out elsewhere never runs p4-checkout and never sees this."""
    if path is not None and path.exists():
        logger.success(f'Perforce settings found: {path}')
        return 0

    say = logger.error if blocking else logger.warning
    where = f' at {path}' if path else ''
    say(
        f'No Perforce settings{where}. '
        + (
            'This task list checks files out of Perforce and reads them. Connect '
            'the Unreal Editor to Perforce once, then run this again.'
            if blocking
            else 'p4-checkout reads them. Connect the Unreal Editor to Perforce '
            'once if you use it.'
        )
    )
    return 1 if blocking else 0


def warn_on_launch(runner) -> None:
    """Says once, at startup, whether the machine matches what these tools
    expect. Never blocks: the task list the user picks may not need any of it.
    """
    pinned = pinned_crowdin_cli_version()
    state = crowdin_cli_state(installed_crowdin_cli_version(), pinned)
    if state not in ('match', 'no_pin'):
        report_crowdin_cli(state, installed_crowdin_cli_version(), pinned, blocking=False)

    binary = resolved_task_path(runner, 'ue-loc-gather-cmd', '_unreal_binary_path')
    if binary is None or not binary.exists():
        report_unreal_binary(binary, blocking=False)


def check_before_running(runner, tasks: list[dict]) -> int:
    """Problems that will stop this particular task list, before it starts.

    Returns the number of blocking problems, so the caller can refuse to run
    rather than fail several minutes in.
    """
    needs = task_list_needs(runner, tasks)
    if not needs:
        return 0

    problems = 0

    if 'cli' in needs:
        pinned = pinned_crowdin_cli_version()
        installed = installed_crowdin_cli_version()
        problems += report_crowdin_cli(
            crowdin_cli_state(installed, pinned), installed, pinned, blocking=True
        )

    if 'ue' in needs:
        problems += report_unreal_binary(
            resolved_task_path(runner, 'ue-loc-gather-cmd', '_unreal_binary_path'),
            blocking=True,
        )

    if 'p4' in needs:
        problems += report_p4_settings(
            resolved_task_path(runner, 'p4-checkout', '_config_path'), blocking=True
        )

    return problems
