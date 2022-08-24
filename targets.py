from pathlib import Path
from loguru import logger
import re

from dataclasses import dataclass, field

from libraries.utilities import LocTask


@dataclass
class UELocTarget:
    '''
    A class to represent an Unreal localization target.

    ...

    Attributes
    ----------
    name : str
        Localization target name
    '''

    # DefaulEditor.ini entry format:
    # +GameTargetsSettings=(Name="Audio",Guid=3E1B21FF40BD014967DDD2B65DD58E1A,TargetDependencies=,AdditionalManifestDependencies=,RequiredModuleNames=,GatherFromTextFiles=(IsEnabled=False,SearchDirectories=,ExcludePathWildcards=,FileExtensions=((Pattern="h"),(Pattern="cpp"),(Pattern="ini")),ShouldGatherFromEditorOnlyData=False),GatherFromPackages=(IsEnabled=True,IncludePathWildcards=((Pattern="Content/Audio/*")),ExcludePathWildcards=((Pattern="Content/L10N/*")),FileExtensions=((Pattern="umap"),(Pattern="uasset")),Collections=,ExcludeClasses=,ShouldExcludeDerivedClasses=False,ShouldGatherFromEditorOnlyData=False,SkipGatherCache=False),GatherFromMetaData=(IsEnabled=False,IncludePathWildcards=,ExcludePathWildcards=,KeySpecifications=,ShouldGatherFromEditorOnlyData=False),ExportSettings=(CollapseMode=IdenticalTextIdAndSource,POFormat=Unreal,ShouldPersistCommentsOnExport=True,ShouldAddSourceLocationsAsComments=True),CompileSettings=(SkipSourceCheck=False,ValidateFormatPatterns=True,ValidateSafeWhitespace=False),ImportDialogueSettings=(RawAudioPath=(Path=""),ImportedDialogueFolder="ImportedDialogue",bImportNativeAsSource=False),NativeCultureIndex=0,SupportedCulturesStatistics=((CultureName="en"),(CultureName="io")))
    # +GameTargetsSettings=(Name="Audio", ...
    # ... NativeCultureIndex=0,SupportedCulturesStatistics=((CultureName="en"),(CultureName="io")) ...
    # ... )

    # Task ini formats
    #
    # [CommonSettings]
    # ManifestDependencies=../Engine/Engine/Content/Localization/Engine/Engine.manifest
    # ManifestDependencies=../Engine/Engine/Content/Localization/Editor/Editor.manifest
    # SourcePath=Content/Localization/Game
    # DestinationPath=Content/Localization/Game
    # ManifestName=Game.manifest
    # ArchiveName=Game.archive
    # NativeCulture=en
    # CulturesToGenerate=en
    # ...
    # CulturesToGenerate=io
    # ...
    #
    # NativeCulture=en
    # CulturesToGenerate=en
    # ...
    # CulturesToGenerate=io
    #

    project_path: Path
    name: str

    # Relative to project root
    _default_game_ini: str = 'Config/DefaultEditor.ini'
    _loc_task_inis: tuple = (
        'Config/Localization/{loc_target}_ImportDialogueScript.ini',
        'Config/Localization/{loc_target}_Compile.ini',
        'Config/Localization/{loc_target}_Export.ini',
        'Config/Localization/{loc_target}_ExportDialogueScript.ini',
        'Config/Localization/{loc_target}_Gather.ini',
        'Config/Localization/{loc_target}_GenerateReports.ini',
        'Config/Localization/{loc_target}_Import.ini',
        'Config/Localization/{loc_target}_ImportDialogue.ini',
    )
    # TODO: Fix this to Content/Localization after testing
    _loc_root: str = 'Localization/{loc_target}/'
    _locale_folder_pattern: str = 'Localization/{loc_target}/{locale}'

    _culture_config_line_start_format: str = '+GameTargetsSettings=(Name="{name}",Guid='
    _task_ini_native_culture_line_start: str = 'NativeCulture='
    _task_ini_culture_line_start: str = 'CulturesToGenerate='

    _task_ini_native_culture_line_format: str = 'NativeCulture={culture}\n'
    _task_ini_culture_line_format: str = 'CulturesToGenerate={culture}\n'

    _culture_regex: str = r'\(CultureName="([a-zA-Z0-9\-]+)"\)'
    _native_culture_idx_regex: str = r'NativeCultureIndex=(\d+),'
    _target_split_regex: str = (
        r'NativeCultureIndex=\d+,'
        r'SupportedCulturesStatistics=\((?:\(CultureName="[a-zA-Z0-9\-]+"\),?)+\)'
    )

    _cultures_config_format: str = (
        'NativeCultureIndex={native_index},'
        'SupportedCulturesStatistics=({supported_cultures})'
    )
    _culture_entry_format: str = '(CultureName="{culture}")'

    def get_current_locales(self) -> list[str] or None:
        '''
        Returns a list of current locales configured for target.
        Taken from DefaultEditor.ini.
        Returns None is target configuration line not found in the ini.
        '''
        with open(self.project_path / self._default_game_ini, 'r') as f:
            strings = f.readlines()
            for s in strings[::-1]:
                if not s.startswith(
                    self._culture_config_line_start_format.format(name=self.name)
                ):
                    continue
                return re.findall(self._culture_regex, s)

        return None

    def get_native_locale(self) -> tuple[int, str] or None:
        '''
        Returns a tuple (native locale index, native locale name) configured for target.
        Taken from DefaultEditor.ini.
        Returns None is target configuration line not found in the ini.
        '''
        with open(self.project_path / self._default_game_ini, 'r') as f:
            strings = f.readlines()
            for s in strings[::-1]:
                if not s.startswith(
                    self._culture_config_line_start_format.format(name=self.name)
                ):
                    continue
                native_index = int(
                    re.search(self._native_culture_idx_regex, s).group(1)
                )
                return (
                    native_index,
                    re.findall(self._culture_regex, s)[native_index],
                )
        return None

    def add_locales(
        self,
        new_locales: list[str],
    ) -> int or None:
        '''
        Add new locales without producing duplicates.
        Keep any existing locales and any any new locales from the supplied list.
        Changes DefaultEditor.ini and ini files in Config/Localization.
        Does NOT create new locale folders in Content/Localization.

        Args:
            new_locales: list of locales to add, duplicates will be ignored
        '''
        # Unique only, preserving order: list(dict.fromkeys(...))

        if len(list(dict.fromkeys(new_locales))) != len(new_locales):
            raise ValueError('Supplied new_locales list contains duplicates.')

        locales = self.get_current_locales()
        if locales is None:
            raise Exception('Could not get current locales for target.')

        locales = list(dict.fromkeys(locales + new_locales))

        return self.replace_all_locales(locales)

    def _update_default_editor_ini(
        self,
        native_locale_index: int,
        locales: list[str],
    ) -> int or None:
        '''
        Internal: updates the DefaultEditor.ini file
        '''
        with open(self.project_path / self._default_game_ini, 'r') as f:
            strings = f.readlines()

        for i, s in enumerate(strings):
            if not s.startswith(
                self._culture_config_line_start_format.format(name=self.name)
            ):
                continue
            try:
                prefix, suffix = re.split(
                    self._target_split_regex,
                    s,
                    1,
                )
            except ValueError as e:
                raise ValueError(
                    'Could not split the target configuration string in DefaulEditor.ini.'
                )

            strings[i] = (
                prefix
                + self._cultures_config_format.format(
                    native_index=native_locale_index,
                    supported_cultures=','.join(
                        [self._culture_entry_format.format(culture=c) for c in locales]
                    ),
                )
                + suffix
            )

            break

        with open(self.project_path / self._default_game_ini, 'w') as f:
            f.writelines(strings)

    def _update_target_loc_ini(
        self,
        ini: str,
        native_locale: str,
        locales: list[str],
    ) -> int or None:
        '''
        Internal: updates any specified {loc_target}_{loc_task}.ini file
        '''
        with open(self.project_path / ini.format(loc_target=self.name), 'r') as f:
            strings = f.readlines()

        new_config_lines = []
        native_culture_found = False

        for s in strings:
            if s.startswith(self._task_ini_native_culture_line_start):
                native_culture_found = True
                new_config_lines.append(
                    self._task_ini_native_culture_line_format.format(
                        culture=native_locale
                    )
                )
                new_config_lines += [
                    self._task_ini_culture_line_format.format(culture=locale)
                    for locale in locales
                ]
                continue

            if s.startswith(self._task_ini_culture_line_start):
                continue

            new_config_lines.append(s)

        if not native_culture_found:
            raise Exception(f'Could not find native culture line in config: {ini}')

        with open(self.project_path / ini.format(loc_target=self.name), 'w') as f:
            f.writelines(new_config_lines)
        pass

    def replace_all_locales(
        self,
        new_locales: list[str],
        *,
        keep_native_locale: bool = True,
        new_native_locale: str = None,
        new_native_locale_index: int = None,
        delete_obsolete_loc_folders: bool = False,
    ) -> int or None:
        '''
        Replace existing locales with new ones.
        Changes DefaultEditor.ini and ini files in Config/Localization.
        By default, does NOT delete obsolete locale folders in Content/Localization.

        Args:
            new_locales: list of new locales, will replace existing locales
            delete_obsolete_loc_folders: controls whether to delete
                obsolete locale folders in Content/Localization
        '''

        if len(list(dict.fromkeys(new_locales))) != len(new_locales):
            raise ValueError('Supplied new_locales list contains duplicates.')

        # Check if supplied locales are valid
        # (basic: regex [a-zA-Z0-9\-], advanced: against list of possible locales?)

        if keep_native_locale and (
            new_native_locale is not None or new_native_locale_index is not None
        ):
            raise ValueError(
                'Either new_native_locale or new_native_locale_index is not None '
                'but keep_native_locale is True.'
            )

        if not keep_native_locale and not (
            new_native_locale is not None or new_native_locale_index is not None
        ):
            raise ValueError(
                'Either new_native_locale or new_native_locale_index required '
                'if keep_native_locale is false.'
            )

        if (
            not keep_native_locale
            and new_native_locale is not None
            and new_native_locale_index is not None
        ):
            raise ValueError(
                'Both new_native_locale and new_native_locale_index specified, '
                'please specify only one of these arguments.'
            )

        if (
            not keep_native_locale
            and new_native_locale_index is not None
            and new_native_locale_index >= len(new_locales)
        ):
            raise ValueError(
                'Supplied new_native_locale_index is too big: '
                'new_locales list has less elements than that.'
            )

        if (
            not keep_native_locale
            and new_native_locale is not None
            and new_native_locale not in new_locales
        ):
            raise ValueError(
                'Supplied new_native_locale is not present in the new_locales list.'
            )

        # Get current locale data

        with open(self.project_path / self._default_game_ini, 'r') as f:
            strings = f.readlines()

        for i, s in enumerate(strings):
            if not s.startswith(
                self._culture_config_line_start_format.format(name=self.name)
            ):
                continue
            native_index = int(re.search(self._native_culture_idx_regex, s).group(1))
            native_locale = re.findall(self._culture_regex, s)[native_index]

            if keep_native_locale and native_locale not in new_locales:
                raise ValueError(
                    'keep_native_locale is true but current native locale '
                    'is not present in the new_locales list'
                )

            if keep_native_locale:
                new_native_locale = native_locale
                new_native_locale_index = new_locales.index(new_native_locale)

            break

        self._update_default_editor_ini(new_native_locale_index, new_locales)

        for ini in self._loc_task_inis:
            self._update_target_loc_ini(ini, new_native_locale, new_locales)

        if delete_obsolete_loc_folders:
            print('Deleting obsolete folders is not implemented yet =(')

    def rename_locale(
        self,
        old_name: str,
        new_name: str,
        *,
        rename_loc_folder: bool = True,
    ):
        '''
        Renames the locale and keeps the translations by default.
        Changes DefaultEditor.ini and ini files in Config/Localization.
        By default, WILL also rename the locale folder in Content/Localization.

        Args:
            old_name: old locale name
            new_name: new locale name
            rename_loc_folder: controls whether to rename
                locale folder in Content/Localization
        '''
        pass


@dataclass
class ManipulateLocTargets(LocTask):

    # TODO: Process all loc targets if none are specified
    # TODO: Change lambda to None to process all loc targets when implemented
    loc_targets: list = field(
        default_factory=lambda: ['Game']
    )  # Localization targets, empty = process all targets

    # TODO: Do I need this here? Or rather in smth from uetools lib?
    content_dir: str = '../'
    config_dir: str = '../../'  # Will try to find it if None or empty
    # TODO: Use uetools to find the directories?

    _content_path: Path = None
    _config_path: Path = None

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

        returncode = 0

        return returncode


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

    loc_target = UELocTarget(Path('../'), 'Audio')

    print(loc_target.get_current_locales())
    print(loc_target.get_native_locale())

    loc_target.replace_all_locales(
        ['en', 'io', 'NEW-ta-dam'],
        keep_native_locale=True,
    )

    # task =

    # task.read_config(Path(__file__).name, logger)

    returncode = 0  # task.run_tasks()

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
