#
# Engine\Binaries\Win64\UE4Editor-cmd.exe Games\FactoryGame\FactoryGame.uproject
# -run=GatherText
# -config="Config\Localization\Game_Gather.ini;Config\Localization\Game_Export.ini"
# -SCCProvider=None
# Ashwin: -DisableSCC
# -Unattended
# -LogLocalizationConflict
# -Log="PyCmdLocGatherAndExport.log"
# -NullRHI

# TODO: Use all loc targets by default

import subprocess as subp
import re
from time import monotonic
from pathlib import Path
from loguru import logger

from dataclasses import dataclass, field

from libraries.utilities import LocTask, init_logging

COMMANDLET_VERDICT = r'GatherText completed with exit code (-?\d+)'
CONFIG_STARTED = r"Beginning GatherText Commandlet for '"
STEP_STARTED = r'Executing GatherTextStep\d+:'
STEP_COMPLETED = r'Completed GatherTextStep\d+:'
# One line per package, and a large project has a hundred thousand of them:
# `[ 12.3%] Gathering package: '/Game/Foo/Bar'...`
PROGRESS = r"\[\s*([\d.]+)%\]\s*(\w+) package: '([^']*)'"
# A reference to a string table entry that does not exist. The text falls
# back to its key on screen, so it is a content bug worth naming.
MISSING_ST_ENTRY = r"Failed to find string table entry for '([^']*)' '([^']*)'"


@dataclass
class UnrealLocGatherCommandlet(LocTask):
    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to None to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    tasks: list = field(
        default_factory=lambda: ['Gather', 'Export']
    )  # Steps to perform. Config/Localization .ini file suffixes:
    # Gather, Export, Import, Сompile, GenerateReports, etc.
    # Set this in task lists in config. Good combinations for text:
    # ['Gather', 'Export']
    # ['Import', 'Compile', 'GenerateReports']
    # ['Gather', 'Import', 'Compile', 'GenerateReports']

    # Unreal exits 1 if anything logged an error, so prefer the commandlet's
    # own reported exit code when it is present in the output
    trust_commandlet_exit_code: bool = True

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    # Assume we're in Content/Python/loctools/
    content_dir: str = '../../'
    project_dir: str = '../../../'
    engine_dir: str = '../../../../'
    unreal_binary: str = 'Engine/Binaries/Win64/UE4Editor-Cmd.exe'  # UE4
    # unreal_binary: str = 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'  # UE5
    # TODO: Use uetools to find the directories?

    try_patch_dependencies: bool = True
    # Should we patch dependencies in *_Gather.ini files?
    # This seems to be needed if the project and engine
    # are in completely separate directories

    # Skip irrelevant Unreal spam (e.g., 'LogLinker: ' if you have lots of warnings)
    log_to_skip: list = field(
        default_factory=lambda: [
            'LogLinker: ',
        ]
    )

    # The commandlet announces every package it loads and gathers. The
    # console is told once per this many percent instead.
    progress_step: int = 1

    # The console shows a progress line every progress_step percent, and at
    # least this often while the commandlet is working, so a package that
    # takes a while to load still looks like progress rather than a hang.
    # The log file keeps every line either way.
    progress_heartbeat: float = 1.0

    _config_pattern: str = 'Config/Localization/{loc_target}_{task}.ini'
    _content_path: Path | None = None
    _project_path: Path | None = None
    _uproject_path: Path | None = None
    _engine_path: Path | None = None
    _unreal_binary_path: Path | None = None

    _config_str: str | None = None

    def post_update(self):
        super().post_update()

        self._content_path = Path(self.content_dir).resolve()

        if self.project_dir:
            self._project_path = Path(self.project_dir).resolve()
        else:
            self._project_path = self._content_path.parent.resolve()

        try:
            self._uproject_path = next(self._project_path.glob('*.uproject'))
        except Exception as err:
            logger.error(
                f'Seems like no .uproject file found in {self._project_path}. '
                'Wrong path?'
            )
            logger.error(err)
            return False

        if self.engine_dir:
            self._engine_path = Path(self.engine_dir).resolve()
            self._unreal_binary_path = self._engine_path / self.unreal_binary
        else:
            # Try to find it as if we're in Games/..
            logger.info('Checking if engine path is ../../ from project directory.')
            self._engine_path = self._project_path.parent.parent
            self._unreal_binary_path = self._engine_path / self.unreal_binary

            if not self._unreal_binary_path.exists():
                # Try to find it in the .sln file
                solution_file = next(self._project_path.glob('*.sln'))
                logger.info(
                    f'Trying to find the engine path from solution file: '
                    f'{solution_file}'
                )
                if not solution_file.exists():
                    logger.error(
                        f'No solution file found in {self._project_path}. Aborting. '
                        'Try setting engine directory explicitely in config.'
                    )
                    return False

                with open(solution_file, mode='r') as file:
                    s = file.read()
                    engine_path = re.findall(
                        r'"UnrealBuildTool", "(.*?)Engine\\Source\\Programs'
                        r'\\UnrealBuildTool\\UnrealBuildTool.csproj"',
                        s,
                    )

                if len(engine_path) == 0:
                    logger.error(
                        "Couldn't find Engine path in the project solution file: "
                        f'{solution_file}. Aborting. '
                        'Try setting engine directory explicitely in config.'
                    )
                    return False

                # TODO: .sln path absolute if game and engine on different disks?..
                self._engine_path = (self._project_path / engine_path[0]).resolve()
                self._unreal_binary_path = self._engine_path / self.unreal_binary

        if not (self._unreal_binary_path and self._unreal_binary_path.exists()):
            logger.error(
                f'No unreal binary found for engine path {self._engine_path}. '
                f'Binary path: {self._unreal_binary_path}. '
                'Wrong path?'
            )
            return False

        self._config_str = ';'.join(
            [
                ';'.join(
                    [
                        self._config_pattern.format(loc_target=loc_target, task=t)
                        for t in self.tasks
                    ]
                )
                for loc_target in self.loc_targets
            ]
        )

        logger.info(f'Project path: {self._project_path}.')
        logger.info(f'Engine path: {self._engine_path}.')

        return True

    def patch_dependencies(self, loc_target: str):
        # Patching the gather.ini to fix paths to engine manifest dependencies
        logger.info('Trying to patch manifest dependencies...')
        with open(
            self._project_path / f'Config/Localization/{loc_target}_Gather.ini', 'r'
        ) as file:
            gather_ini = file.read()
            engine_path = re.subn(r'\\', '/', str(self._engine_path))[0]
            gather_ini, patched_dependencies = re.subn(
                r'(?<=ManifestDependencies=)[^\r\n]*?(?=/Engine/Content/Localization/)',
                engine_path,
                gather_ini,
            )

        if patched_dependencies > 0:
            with open(
                self._project_path / f'Config/Localization/{loc_target}_Gather.ini', 'w'
            ) as file:
                file.write(gather_ini)
            logger.info(f'Patched dependencies: {patched_dependencies}')
        else:
            logger.info('No dependencies patched.')

        return

    def run_tasks(self):
        logger.info(
            f'Processing targets ({len(self.loc_targets)}): '
            f'{self.loc_targets}. Tasks ({len(self.tasks)}): {self.tasks}'
        )

        if 'Gather' in self.tasks and self.try_patch_dependencies:
            for loc_target in self.loc_targets:
                self.patch_dependencies(loc_target)

        logger.info(
            f'Running Unreal loc gather commandlet with following config value: '
            f'{self._config_str}'
        )

        commands = [
            str(self._unreal_binary_path),
            str(self._uproject_path),
            '-run=GatherText',
            f'-config="{self._config_str}"',
            '-SCCProvider=None',  # Source Control Provider
            '-DisableSCC',  # Disable Source Control
            '-Unattended',  # Run without user interaction
            '-LogLocalizationConflict',  # Log localization conflicts
            '-NullRHI',  # Disable rendering to avoid shader compilation
        ]

        logger.info(f'Running command: {" ".join(commands)}')

        commandlet_codes = []
        errors = 0
        configs_started = 0
        steps_started = 0
        steps_completed = 0
        # The percentage the console has been told about, and when.
        next_percent = 0.0
        last_shown = 0.0
        last_package = None
        # (string table, key) -> how many times it was referenced
        missing_entries: dict[tuple[str, str], int] = {}

        try:
            with subp.Popen(
                commands,
                stdout=subp.PIPE,
                stderr=subp.STDOUT,
                cwd=self._engine_path,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace',
            ) as process:
                while True:
                    for line in process.stdout:
                        skip = False
                        for item in self.log_to_skip:
                            if item in line:
                                skip = True
                        if skip:
                            continue

                        line = re.sub(r'^\[[^]]+]', '', line.strip())
                        # Everything, throttled or not, in case this is the run
                        # that stops without explaining itself.

                        verdict = re.search(COMMANDLET_VERDICT, line)
                        if verdict:
                            commandlet_codes.append(int(verdict.group(1)))
                        elif re.search(CONFIG_STARTED, line):
                            configs_started += 1
                        elif re.search(STEP_STARTED, line):
                            steps_started += 1
                        elif re.search(STEP_COMPLETED, line):
                            steps_completed += 1

                        progress = re.search(PROGRESS, line)
                        if progress:
                            percent = float(progress.group(1))
                            last_package = (percent, progress.group(2),
                                            progress.group(3))
                            # The log keeps every one of these: it is the
                            # record of what the commandlet did. The console
                            # gets enough of them to show it is alive.
                            logger.bind(log_only=True).info(f'| UE | {line}')
                            now = monotonic()
                            if (
                                percent >= next_percent
                                or now - last_shown >= self.progress_heartbeat
                            ):
                                logger.bind(console_only=True).info(f'| UE | {line}')
                                next_percent = (
                                    int(percent // self.progress_step) + 1
                                ) * self.progress_step
                                last_shown = now
                            continue

                        # Counted for the summary and kept in the stream,
                        # where the commandlet raised it. Logged as a
                        # warning whichever way Unreal worded it: the
                        # same missing entry arrives as Display: in some
                        # contexts and Warning: in others.
                        missing = re.search(MISSING_ST_ENTRY, line)
                        if missing:
                            key = (missing.group(1), missing.group(2))
                            missing_entries[key] = missing_entries.get(key, 0) + 1
                            logger.warning(f'| UE | {line.strip()}')
                            continue

                        if 'Error: ' in line:
                            errors += 1
                            logger.error(f'| UE | {line.strip()}')
                        elif 'Warning: ' in line:
                            logger.warning(f'| UE | {line.strip()}')
                        else:
                            logger.info(f'| UE | {line.strip()}')
                    if process.poll() is not None:
                        break
                returncode = process.returncode

                logger.info(
                    f'Unreal loc gather commandlet finished with return code: {returncode}'
                )
        except (OSError, subp.SubprocessError) as err:
            logger.error(f'Reading the commandlet output failed: {err}')
            self.report_where_it_stopped(last_package)
            return False

        self.report_missing_entries(missing_entries)

        succeeded = self.task_succeeded(
            returncode,
            commandlet_codes,
            errors,
            configs_started,
            steps_started,
            steps_completed,
        )
        if not succeeded:
            self.report_where_it_stopped(last_package)
        return succeeded

    def report_where_it_stopped(self, last_package):
        """Where the commandlet got to, for a run that failed. Only the
        position: every line it wrote is in the log file already."""
        if last_package:
            percent, verb, package = last_package
            logger.error(
                f'The last package it reached was {package!r}, '
                f'{verb.lower()} at {percent:.0f}%.'
            )

    def report_missing_entries(self, missing: dict[tuple[str, str], int]):
        """String table entries that are referenced but do not exist.

        One missing entry is usually referenced from several places, and the
        commandlet says so once per reference, so they are counted and named
        once each instead."""
        if not missing:
            return
        references = sum(missing.values())
        logger.warning(
            f'{len(missing)} string table entr(ies) are referenced but do not '
            f'exist, from {references} place(s). The text falls back to its '
            'key on screen:'
        )
        for (table, key), count in sorted(missing.items()):
            times = '' if count == 1 else f'  ({count} references)'
            logger.warning(f'  {table},{key}{times}')

    def incomplete_run(
        self, configs_started: int, steps_started: int, steps_completed: int
    ) -> str | None:
        """What the run's own accounting says is missing, if anything."""
        expected = len(self.loc_targets) * len(self.tasks)
        if configs_started < expected:
            return (
                f'only {configs_started} of {expected} configs were started '
                f'({len(self.loc_targets)} target(s) x {len(self.tasks)} task(s))'
            )
        if steps_started == 0:
            return 'no gather steps ran at all'
        if steps_completed < steps_started:
            return (
                f'{steps_started - steps_completed} of {steps_started} gather '
                'steps never reported completion'
            )
        return None

    def task_succeeded(
        self,
        returncode: int,
        commandlet_codes: list[int],
        errors: int = 0,
        configs_started: int = 0,
        steps_started: int = 0,
        steps_completed: int = 0,
    ) -> bool:
        """Unreal exits non-zero if anything logged an error, including errors
        that have nothing to do with localization, so the commandlet's own
        verdict is the more accurate signal when we have it.

        One engine run covers several steps and normally reports once, but a
        single non-zero verdict fails the task however many are printed.

        UE4 streams no verdict at all, so its absence cannot mean failure:
        there the run is judged by its own accounting instead: every config
        started, every step that started also completed, and a clean process
        exit. That is weaker — counts cannot tell a step that succeeded from
        one that failed cleanly — so it is the fallback, not the rule."""
        if not self.trust_commandlet_exit_code:
            if returncode != 0 and commandlet_codes and not any(commandlet_codes):
                logger.warning(
                    'The commandlet reported success but Unreal exited '
                    f'{returncode}. Reporting failure because '
                    'trust_commandlet_exit_code is off.'
                )
            return returncode == 0

        incomplete = self.incomplete_run(
            configs_started, steps_started, steps_completed
        )

        if not commandlet_codes:
            if incomplete or returncode != 0:
                logger.error(
                    'GatherText never reported an exit code, and the run does '
                    'not look complete: '
                    f'{incomplete or f"Unreal exited {returncode}"}. Check the '
                    'log for a crash.'
                )
                return False

            logger.warning(
                'GatherText reported no exit code, which UE 4.27 and older do '
                f'not print. Accepting the run on its own accounting: '
                f'{configs_started} config(s) started, {steps_completed} of '
                f'{steps_started} steps completed, process exit 0.'
            )
            return True

        failed = [code for code in commandlet_codes if code != 0]
        if failed:
            logger.error(
                f'GatherText reported exit code(s) {failed} across '
                f'{len(commandlet_codes)} verdict(s).'
            )
            return False

        if incomplete:
            logger.error(
                f'GatherText reported success, but {incomplete}, so Unreal '
                'stopped part way through.'
            )
            return False

        if returncode != 0:
            logger.warning(
                f'GatherText completed with exit code 0, but Unreal exited '
                f'{returncode}. Unreal does that when anything logged an error '
                f'during the run ({errors} error line(s) here), including '
                'errors unrelated to localization. Treating the run as '
                'successful: check the log if the output looks wrong.'
            )

        return True

    def run(self):
        return self.run_tasks()


def main():
    log_file = init_logging()

    logger.info('')
    logger.info('--- Unreal gather text commandlet script ---')
    logger.info('')

    task = UnrealLocGatherCommandlet()

    task.read_config(Path(__file__).name)

    returncode = task.run()

    if returncode == 0:
        logger.info('')
        logger.info('--- Unreal gather text commandlet script end ---')
        logger.info('')
        return 0

    logger.error(f'Error occured, please see the log: {log_file}')
    return 1


# Run the script if the isn't imported
if __name__ == '__main__':
    main()
