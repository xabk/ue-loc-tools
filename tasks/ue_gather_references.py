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
from timeit import default_timer as timer

from loguru import logger

from libraries.uetools import UEProject
from libraries.utilities import LocTask

# Lines the commandlet prints that we key on.
PACKAGES_TO_LOAD = r'Preparing to load (\d+) packages'
PACKAGES_LOADED = r'Loaded (\d+) packages in ([\d.]+) seconds\. (\d+) failed'
PROGRESS = r'\[\s*([\d.]+)%\]'
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

    # The commandlet and the flags it needs. Both are here rather than hard
    # coded so a project with a renamed or extended commandlet can say so.
    commandlet: str = 'GatherStringTableReferences'
    # -Unattended so a modal cannot stop a run that is only ever unattended.
    extra_args: list[str] = field(
        default_factory=lambda: ['-NullRHI', '-Unattended']
    )

    # Engine start-up chatter that says nothing about the gather. Live
    # coding alone accounted for 96% of the lines on the first real run.
    log_to_skip: list[str] = field(
        default_factory=lambda: ['LogLiveCodingServer: ', 'LogLinker: ']
    )

    # Progress is one line per package, and a real project has tens of
    # thousands. Report every this-many percent instead of every line.
    progress_step: int = 10

    # One missing entry is often referenced from many places; list this many
    # before summarising the rest.
    missing_contexts_to_show: int = 3

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
        missing: dict[tuple[str, str], list[str]] = {}
        next_report = 0
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
                for line in process.stdout:
                    line = re.sub(r'^\[[^]]+]', '', line.strip())

                    if any(skip in line for skip in self.log_to_skip):
                        continue

                    match = re.search(PACKAGES_TO_LOAD, line)
                    if match:
                        expected = int(match.group(1))
                        logger.info(f'| UE | Loading {expected} packages...')
                        continue

                    match = re.search(PACKAGES_LOADED, line)
                    if match:
                        loaded, seconds, failed = (
                            int(match.group(1)),
                            float(match.group(2)),
                            int(match.group(3)),
                        )
                        logger.info(
                            f'| UE | Loaded {loaded} packages in {seconds:.0f}s, '
                            f'{failed} failed.'
                        )
                        continue

                    match = re.search(MISSING_REFERENCE, line)
                    if match:
                        table, key, context = match.groups()
                        missing.setdefault((table, key), []).append(context.strip())
                        continue

                    if re.search(MISSING_BANNER, line):
                        continue

                    if re.search(NO_ASSETS, line):
                        no_assets += 1
                        continue

                    match = re.search(PROGRESS, line)
                    if match:
                        percent = float(match.group(1))
                        if percent >= next_report:
                            logger.info(f'| UE | {percent:.0f}%')
                            next_report = percent + self.progress_step
                        continue

                    if 'Error: ' in line:
                        logger.error(f'| UE | {line}')
                    elif 'Warning: ' in line:
                        logger.warning(f'| UE | {line}')
        except (OSError, subp.SubprocessError) as err:
            logger.error(f'Could not run the commandlet: {err}')
            return False

        return self.verdict(
            process.returncode,
            expected,
            loaded,
            failed,
            no_assets,
            timer() - start,
            missing,
        )

    def verdict(
        self,
        returncode: int,
        expected: int | None,
        loaded: int | None,
        failed: int | None,
        no_assets: int,
        duration: float,
        missing: dict[tuple[str, str], list[str]] | None = None,
    ) -> bool:
        """The commandlet states its own failure count, so this leans on that
        rather than inferring success from the absence of errors."""
        if returncode != 0:
            logger.error(f'{self.commandlet} exited with code {returncode}.')
            return False

        if loaded is None:
            logger.error(
                f'{self.commandlet} never reported loading any packages. It may '
                'have stopped before it started gathering.'
            )
            return False

        if failed:
            # A big project always has a few packages that will not load.
            # The gather still produced references for everything else.
            logger.warning(
                f'{failed} of {loaded} packages failed to load. Their references are missing from the output.'
            )

        if expected is not None and loaded != expected:
            logger.warning(
                f'Planned to load {expected} packages but loaded {loaded}.'
            )

        self.report_missing_references(missing)

        # The source pass finds nothing on projects that keep their strings in
        # assets only, which is normal rather than a problem.
        if no_assets:
            logger.info(
                f'{no_assets} pass(es) matched no assets, which is expected when '
                'a project has no source-code string references.'
            )

        logger.success(
            f'{self.commandlet} gathered {loaded} packages in {duration:.0f}s.'
        )
        return True

    def report_missing_references(
        self, missing: dict[tuple[str, str], list[str]] | None
    ) -> None:
        """A reference to a string table entry that is not there. The text
        will fall back to its key in game, so this is worth surfacing, but it
        is a content problem rather than a failed run."""
        if not missing:
            return

        total = sum(len(contexts) for contexts in missing.values())
        logger.warning(
            f'{len(missing)} string table entr(ies) are referenced but do not '
            f'exist, from {total} place(s):'
        )
        for (table, key), contexts in sorted(missing.items()):
            logger.warning(f'| REF | {table},{key} - {len(contexts)} reference(s)')
            for context in contexts[: self.missing_contexts_to_show]:
                logger.warning(f'| REF |     {context}')
            if len(contexts) > self.missing_contexts_to_show:
                extra = len(contexts) - self.missing_contexts_to_show
                logger.warning(f'| REF |     ... and {extra} more')
