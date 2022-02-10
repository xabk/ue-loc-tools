#
# Engine\Binaries\Win64\UE4Editor-cmd.exe Games\FactoryGame\FactoryGame.uproject -run=GatherText
# -config="Config\Localization\Game_Gather.ini;Config\Localization\Game_Export.ini" -SCCProvider=None
# -Unattended -LogLocalizationConflict -Log="PyCmdLocGatherAndExport.log"

# Engine\Binaries\Win64\UE4Editor-cmd.exe Games\FactoryGame\FactoryGame.uproject -run=GatherText
# -config="Config\Localization\Game_Gather.ini;Config\Localization\Game_ExportIO.ini" -SCCProvider=None
# -Unattended -LogLocalizationConflict -Log="PyCmdLocGatherAndExport.log"

# Engine\Binaries\Win64\UE4Editor-cmd.exe Games\FactoryGame\FactoryGame.uproject -run=GatherText
# -config="Config\Localization\Game_Import.ini;Config\Localization\Game_Compile.ini" -SCCProvider=None
# -Unattended -LogLocalizationConflicts -Log="PyCmdLocGatherAndImport.log"

#
# add "capture_output=True, text=True" to make it silent and catch output into result
#

# TODO: Use all loc targets by default
# TODO: Add config file support
# TODO: Move parameters to config file

import subprocess as subp
import re
from pathlib import Path
from loguru import logger

from dataclasses import dataclass, field

from libraries import utilities


@dataclass
class UnrealLocGatherCommandlet(utilities.Parameters):

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to empty list to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    # Relative to Game/Content directory
    tasks_to_perform: list = field(
        default_factory=lambda: ['Gather', 'Export']
    )  # Steps to perform. Config/Localization .ini file suffixes:
    # Gather, Export, Import, Сompile, GenerateReports, etc.

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    project_dir: str = None  # Will try to find it if None or empty
    engine_dir: str = None  # Will try to find it if None or empty
    # TODO: Use uetools to find the directories?

    try_patch_dependencies: bool = True
    # Should we patch dependencies in *_Gather.ini files?
    # This seems to be needed if the project and engine
    # are in completely separate directories

    _unreal_binary: str = 'Engine/Binaries/Win64/UE4Editor-cmd.exe'
    _config_pattern: str = 'Config/Localization/{loc_target}_{task}.ini'
    _content_path: Path = None
    _project_path: Path = None
    _uproject_path: Path = None
    _engine_path: Path = None
    _unreal_binary_path: Path = None

    _tasks: dict = None

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
        else:
            # Try to find it as if we're in Games/..
            logger.info('Checking if engine path is ../../ from project directory.')
            self._engine_path = self._project_path.parent.parent
            self._unreal_binary_path = self._engine_path / self._unreal_binary

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
                        f'Couldn\'t find Engine path in the project solution file: '
                        '{solution_file}. Aborting. '
                        'Try setting engine directory explicitely in config.'
                    )
                    return False

                # TODO: .sln path absolute if game and engine on different disks?..
                self._engine_path = (self._project_path / engine_path[0]).resolve()
                self._unreal_binary_path = self._engine_path / self._unreal_binary

        if not (self._unreal_binary_path and self._unreal_binary_path.exists()):
            logger.error(
                f'No unreal binary found for engine path {self._engine_path}. '
                'Wrong path?'
            )
            return False

        self._tasks = {
            loc_target: ';'.join(
                [
                    self._config_pattern.format(loc_target=loc_target, task=t)
                    for t in self.tasks_to_perform
                ]
            )
            for loc_target in self.loc_targets
        }

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
            engine_path = re.subn(r'\\', '/', self._engine_path)[0]
            gather_ini, patched_dependencies = re.subn(
                r'(?<=ManifestDependencies=)[^\r\n]*?(?=Engine/Content/Localization/)',
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

    def run_tasks_for_loc_target(self, loc_target: str):
        logger.info(f'Processing target {loc_target}. Tasks: {self.tasks_to_perform}')

        if 'Gather' in self.tasks_to_perform and self.try_patch_dependencies:
            self.patch_dependencies(loc_target)

        logger.info(
            f'Running Unreal loc gather commandlet with following config value: '
            f'{self._tasks[loc_target]}'
        )

        with subp.Popen(
            [
                self._unreal_binary_path,
                self._uproject_path,
                '-run=GatherText',
                f'-config="{self._tasks[loc_target]}"',
                '-SCCProvider=None',
                '-Unattended',
                '-LogLocalizationConflict',
                '-Log="PyCmdLocGatherAndExport.log"',
            ],
            stdout=subp.PIPE,
            stderr=subp.STDOUT,
            cwd=self._engine_path,
            universal_newlines=True,
        ) as process:
            while True:
                for line in process.stdout:
                    line = re.sub(r"^\[[^]]+]", "", line.strip())
                    logger.info(f'| UE | {line}')
                if process.poll() != None:
                    break
            returncode = process.returncode

        return returncode

    def run_tasks(self):

        logger.info(f'Targets to process ({len(self.loc_targets)}): {self.loc_targets}')
        logger.info(
            f'Tasks to perform ({len(self.tasks_to_perform)}): '
            f'{self.tasks_to_perform}'
        )

        targets_processed = []
        for t in self.loc_targets:
            if self.run_tasks_for_loc_target(t):
                targets_processed += [t]

        if targets_processed:
            logger.info(
                f'Targets processed ({len(targets_processed)}): {targets_processed}'
            )
            return True

        logger.warning('No targets processed.')

        return False


def main():

    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
    )

    logger.info('')
    logger.info('--- Unreal gather text commandlet script ---')
    logger.info('')

    cfg = UnrealLocGatherCommandlet()

    cfg.read_config(Path(__file__).name, logger)

    returncode = cfg.run_tasks()

    if returncode == 0:
        logger.info('')
        logger.info('--- Unreal gather text commandlet script end ---')
        logger.info('')
        return 0

    logger.error('Error occured, please see the Content/Python/Logs/locsync.log')
    return 1


# Run the script if the isn't imported
if __name__ == "__main__":
    main()
