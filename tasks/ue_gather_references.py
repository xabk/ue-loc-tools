"""Gather string table references with the studio's Unreal plugin commandlet.

The commandlet walks every package in the project and records which assets
reference which string table entries. `test-lang` then folds that CSV into the
source locale as a `Refs` context field, so translators can see where a string
is used.

UE5 only: the plugin that provides the commandlet does not exist for UE4.

Its logging has nothing in common with GatherText -- no `Beginning ...
Commandlet for`, no `Executing ...StepN`, no `... completed with exit code`.
It reports a package count up front, percentage progress per package, and a
closing line with an explicit failure count, which is a better verdict than
GatherText offers.
"""

import re
import subprocess as subp
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from timeit import default_timer as timer

from loguru import logger

from libraries.findings import Findings
from libraries.ue_findings import UE_RECAP, collect
from libraries.uetools import UEProject
from libraries.utilities import LocTask

# Lines the commandlet prints that we key on.
PACKAGES_TO_LOAD = r'Preparing to load (\d+) packages'
PACKAGES_LOADED = r'Loaded (\d+) packages in ([\d.]+) seconds\. (\d+) failed'
PROGRESS = re.compile(r"\[\s*([\d.]+)%\]\s*(\w+) package: '([^']*)'")
NO_ASSETS = r'No assets matched the specified criteria'
# A reference to a string table entry that does not exist. The commandlet
# prints these between two banner lines at the end of its run.
MISSING_REFERENCE = (
    r'<MissingStringTableReference> StringTable: \[([^]]+)\], '
    r'Key: \[([^]]+)\] Context: (.*)'
)
MISSING_BANNER = r'Missing String Table References|={6,}'


@dataclass
class GatherStringTableReferences(LocTask):
    """Runs the reference gathering commandlet and reports what it did."""

    # Configurable for a project that renamed or extended the commandlet.
    commandlet: str = 'GatherStringTableReferences'
    # -Unattended so a modal cannot stop a run that is only ever unattended.
    extra_args: list[str] = field(
        default_factory=lambda: ['-NullRHI', '-Unattended']
    )

    # Engine start-up chatter that says nothing about the gather.
    log_to_skip: list[str] = field(
        default_factory=lambda: ['LogLiveCodingServer: ', 'LogLinker: ']
    )

    # The console is told once per this many percent, and at least once
    # per progress_heartbeat. The log file keeps every package.
    progress_step: int = 1
    progress_heartbeat: float = 1.0

    # Unreal exits 1 if anything logged an error, localization or not, so
    # prefer the commandlet's own count. False fails on any non-zero exit.
    trust_commandlet_exit_code: bool = True

    # Same shape as ue-loc-gather-cmd, so a project configures paths once.
    project_dir: str | None = None  # Absolute or relative to cwd
    engine_dir: str | None = None  # Absolute or relative to cwd
    unreal_binary: str | None = None  # Relative to engine root

    _ue: UEProject | None = None
    _uproject_path: Path | None = None

    def post_update(self):
        super().post_update()

        engine_path = Path(self.engine_dir).resolve() if self.engine_dir else None
        try:
            self._ue = UEProject(
                project_path=self.project_dir or '../../../',
                engine_path=engine_path,
                unreal_binary=self.unreal_binary,
            )
        except (ValueError, OSError) as err:
            # Building the task must not blow up where the project is not
            # checked out: --check creates every task just to validate config.
            logger.error(f'Could not resolve the Unreal project: {err}')
            return True

        uprojects = sorted(self._ue.project_path.glob('*.uproject'))
        if not uprojects:
            logger.error(f'No .uproject found in {self._ue.project_path}')
        else:
            self._uproject_path = uprojects[0]

        logger.info(f'Project path: {self._ue.project_path}.')
        logger.info(f'Editor binary: {self._ue.cmd_binary_path}.')

    def run(self) -> bool:
        if not self._uproject_path:
            logger.error('No project file to run the commandlet against.')
            return False

        binary = self._ue.cmd_binary_path if self._ue else None
        if not (binary and binary.exists()):
            logger.error(
                f'Unreal editor binary not found: {binary}. Build the editor, or '
                'fix engine_dir and unreal_binary in your config.'
            )
            return False

        commands = [
            str(binary),
            str(self._uproject_path),
            f'-run={self.commandlet}',
            *self.extra_args,
        ]
        logger.info(f'Running: {" ".join(commands)}')

        expected = None
        loaded = failed = None
        no_assets = 0
        # (string table, key) -> the contexts that reference it
        next_percent = 0.0
        last_shown = 0.0
        last_seen = None
        self.findings = Findings(source=self.__class__.__name__)
        collecting = True
        start = timer()

        try:
            with subp.Popen(
                commands,
                stdout=subp.PIPE,
                stderr=subp.STDOUT,
                cwd=self._ue.project_path,
                universal_newlines=True,
                encoding='utf-8',
                # Unreal writes log text in the console codepage, and one byte
                # outside UTF-8 would otherwise kill the read mid-run.
                errors='replace',
                stdin=subp.DEVNULL,
            ) as process:
                last_package = None
                for line in process.stdout:
                    line = re.sub(r'^\[[^]]+]', '', line.strip())

                    if any(skip in line for skip in self.log_to_skip):
                        continue

                    match = re.search(PACKAGES_TO_LOAD, line)
                    if match:
                        expected = int(match.group(1))

                    match = re.search(PACKAGES_LOADED, line)
                    if match:
                        loaded, seconds, failed = (
                            int(match.group(1)),
                            float(match.group(2)),
                            int(match.group(3)),
                        )

                    if re.search(NO_ASSETS, line):
                        no_assets += 1

                    progress = PROGRESS.search(line)
                    if progress:
                        percent = float(progress.group(1))
                        package = progress.group(3)
                        # Announced once per phase, same name both times.
                        if package == last_package:
                            continue
                        last_package = package
                        last_seen = (percent, progress.group(2), package)
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

                    if UE_RECAP.search(line):
                        collecting = False

                    if collecting and collect(self.findings, line):
                        logger.warning(f'| UE | {line}')
                        continue

                    if re.search(MISSING_BANNER, line):
                        continue

                    if 'Error: ' in line:
                        logger.error(f'| UE | {line}')
                    elif 'Warning: ' in line:
                        logger.warning(f'| UE | {line}')
                    else:
                        logger.info(f'| UE | {line}')
        except (OSError, subp.SubprocessError) as err:
            logger.error(f'Could not run the commandlet: {err}')
            return False

        succeeded = self.verdict(
            process.returncode,
            expected,
            loaded,
            failed,
            no_assets,
            timer() - start,
        )

        # Reported however the run went, not only on the way out clean.
        self.findings.report()
        return succeeded

    def verdict(
        self,
        returncode: int,
        expected: int | None,
        loaded: int | None,
        failed: int | None,
        no_assets: int,
        duration: float,
    ) -> bool:
        """The commandlet states its own failure count, so this leans on that
        rather than inferring success from the absence of errors.

        Unreal exits non-zero whenever anything logged an error during the
        run, and on a project of any size that includes broken assets the
        gather neither touches nor depends on. A run that loaded every package
        it planned to has done its job, so the exit code is reported and set
        aside; it only decides the verdict when the accounting is missing or
        falls short."""
        if not self.trust_commandlet_exit_code and returncode != 0:
            logger.error(f'{self.commandlet} exited with code {returncode}.')
            return False

        if loaded is None:
            logger.error(
                f'{self.commandlet} never reported loading any packages. It may '
                'have stopped before it started gathering.'
            )
            return False

        if failed:
            # Not fatal: the gather still has every other package.
            logger.warning(
                f'{failed} of {loaded} packages failed to load. Their references are missing from the output.'
            )

        if expected is not None and loaded != expected:
            if returncode != 0:
                logger.error(
                    f'Planned to load {expected} packages but loaded {loaded}, '
                    f'and Unreal exited {returncode}. The run stopped part way '
                    'through.'
                )
                return False
            logger.warning(
                f'Planned to load {expected} packages but loaded {loaded}.'
            )

        # The source pass finds nothing on projects that keep their strings in
        # assets only, which is normal rather than a problem.
        if no_assets:
            logger.info(
                f'{no_assets} pass(es) matched no assets, which is expected when '
                'a project has no source-code string references.'
            )

        if returncode != 0:
            logger.warning(
                f'{self.commandlet} loaded every one of its {loaded} packages, '
                f'but Unreal exited {returncode}. Unreal does that when '
                'anything logged an error during the run, including errors '
                'unrelated to localization. Treating the run as successful: '
                'check the log if the output looks wrong.'
            )

        logger.success(
            f'{self.commandlet} gathered {loaded} packages in {duration:.0f}s.'
        )
        return True
