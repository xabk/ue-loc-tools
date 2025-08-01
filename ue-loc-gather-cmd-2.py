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
from pathlib import Path
from loguru import logger

from dataclasses import dataclass, field

from libraries.utilities import LocTask, init_logging


@dataclass
class UnrealLocGatherCommandlet(LocTask):
    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to None to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    tasks: list = field(
        default_factory=lambda: ['Import', 'Compile']
    )  # Steps to perform. Config/Localization .ini file suffixes:
    # Gather, Export, Import, Сompile, GenerateReports, etc.
    # Set this in task lists in config. Good combinations for text:
    # ['Gather', 'Export']
    # ['Import', 'Compile', 'GenerateReports']
    # ['Gather', 'Import', 'Compile', 'GenerateReports']

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    # Assume we're in Content/Python/loctools/
    content_dir: str = '../../'
    project_dir: str = '../../../'
    engine_dir: str = '../../../../Engine/'
    unreal_binary: str = 'Binaries/Win64/UE4Editor-Cmd.exe'  # UE4
    # unreal_binary: str = 'Binaries/Win64/UnrealEditor-Cmd.exe'  # UE5
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

        with subp.Popen(
            commands,
            stdout=subp.PIPE,
            stderr=subp.STDOUT,
            cwd=self._engine_path,
            universal_newlines=True,
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
                    if 'Error: ' in line:
                        logger.error(f'| UE | {line.strip()}')
                    elif 'Warning: ' in line:
                        logger.warning(f'| UE | {line.strip()}')
                    else:
                        logger.info(f'| UE | {line.strip()}')
                if process.poll() is not None:
                    break
            returncode = process.returncode

        return returncode

    def run(self):
        return self.run_tasks()


def main():
    init_logging()

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

    logger.error('Error occured, please see the Content/Python/Logs/locsync.log')
    return 1


# Run the script if the isn't imported
if __name__ == '__main__':
    main()
