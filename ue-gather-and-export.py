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

# TODO: Support several localization targets via parameters
#       and use all loc targets by default
# TODO: Add config file support
# TODO: Move parameters to config file

import subprocess as subp
import re
from pathlib import Path
from timeit import default_timer as timer
from loguru import logger


def main():
    start = timer()
    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
    )

    logger.info('--- Gather and export ---')

    logger.info('Gathering text and exporting Game locale...')

    project_path = Path(__file__).parent.parent.parent.absolute()

    # Trying to find the path to Unreal Build Tool in the .sln file
    solution_file = next(project_path.glob('*.sln'))
    logger.info(f'Trying to find the engine path from solution file: {solution_file}')
    with open(solution_file, mode='r') as file:
        s = file.read()
        engine_path = re.findall(
            r'"UnrealBuildTool", "(.*?)Engine\\Source\\Programs\\UnrealBuildTool\\UnrealBuildTool.csproj"',
            s,
        )

    if len(engine_path) == 0:
        logger.error(
            f'Aborting. Couldn\'t find Engine path in the project solution file: {solution_file}'
        )

    cwd = (project_path / engine_path[0]).resolve()

    # Patching the gather.ini to fix paths to engine manifest dependencies
    logger.info('Trying to patch manifest dependencies...')
    with open(project_path / 'Config/Localization/Game_Gather.ini', 'r') as file:
        gather_ini = file.read()
        engine_path = re.subn(r'\\', '/', str(engine_path[0]))[0]
        gather_ini, patched_dependencies = re.subn(
            r'(?<=ManifestDependencies=)[^\r\n]*?(?=Engine/Content/Localization/)',
            engine_path,
            gather_ini,
        )

    if patched_dependencies > 0:
        with open(project_path / 'Config/Localization/Game_Gather.ini', 'w') as file:
            file.write(gather_ini)
        logger.info(f'Patched dependencies: {patched_dependencies}')
    else:
        logger.info('No dependencies patched.')

    fpath = (cwd / 'Engine/Binaries/Win64/UE4Editor-cmd.exe').absolute()

    # Finding the .uproject file path
    uproject = next(project_path.glob('*.uproject')).absolute()

    logger.info(f'Working directory: {cwd}')

    returncode = 0

    with subp.Popen(
        [
            fpath,
            uproject,
            '-run=GatherText',
            '-config="Config\\Localization\\Game_Gather.ini;Config\\Localization\\Game_Export.ini"',
            '-SCCProvider=None',
            '-Unattended',
            '-LogLocalizationConflict',
            '-Log="PyCmdLocGatherAndExport.log"',
        ],
        stdout=subp.PIPE,
        stderr=subp.STDOUT,
        cwd=cwd,
        universal_newlines=True,
    ) as process:
        while True:
            for line in process.stdout:
                line = re.sub(r"^\[[^]]+]", "", line.strip())
                logger.info(f'| UE | {line}')
            if process.poll() != None:
                break
        returncode = process.returncode

    elapsed = timer() - start
    logger.info('')
    logger.info(f'Execution time: {elapsed:.2f} sec.')
    if returncode == 0:
        logger.info('Gathered the text and exported all locales.')
        logger.info('--- Gather and export script end ---')
        return 0
    else:
        logger.error('Error occured, please see the Content/Python/Logs/locsync.log')
        return 1


# Run the script if the isn't imported
if __name__ == "__main__":
    main()
