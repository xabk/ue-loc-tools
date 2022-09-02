try:
    import unreal

    UNREAL = True
except:
    UNREAL = False

from pathlib import Path
from loguru import logger
import re

from dataclasses import dataclass, field


@dataclass
class UELocTarget:
    '''
    A class to represent an Unreal localization target.

    ...

    Attributes
    ----------
    project_path: Path
        Project directory
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

    # TODO: write my own __init__ to preformat path strings
    # TODO: add and implement delete_locale method

    # Relative to project root
    _default_game_ini: str = 'Config/DefaultEditor.ini'
    _loc_task_inis: tuple = (
        'Config/Localization/{loc_target}_ImportDialogueScript.ini',
        'Config/Localization/{loc_target}_Compile.ini',
        'Config/Localization/{loc_target}_Export.ini',
        'Config/Localization/{loc_target}_ExportDialogueScript.ini',
        'Config/Localization/{loc_target}_Gather.ini',
        'Config/Localization/{loc_target}_Import.ini',
        'Config/Localization/{loc_target}_ImportDialogue.ini',
    )
    _loc_task_inis_no_native_culture: tuple = (
        'Config/Localization/{loc_target}_GenerateReports.ini',
    )

    _loc_root: str = 'Content/Localization/{loc_target}/'
    _locale_folder_pattern: str = 'Content/Localization/{loc_target}/{locale}'

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
    ) -> int:
        '''
        Add new locales without producing duplicates.
        Keep any existing locales and any any new locales from the supplied list.
        Changes DefaultEditor.ini and ini files in Config/Localization.
        Does NOT create new locale folders in Content/Localization.

        Args:
            new_locales: list of locales to add, duplicates will be ignored
        '''
        if len(list(dict.fromkeys(new_locales))) != len(new_locales):
            raise ValueError('Supplied new_locales list contains duplicates.')

        locales = self.get_current_locales()
        if locales is None:
            raise Exception('Could not get current locales for target.')

        locales = list(dict.fromkeys(locales + new_locales))

        return self.replace_all_locales(locales)

    # TODO: better logging
    def remove_locales(
        self,
        locales_to_remove: list[str] or str,
        *,
        delete_obsolete_loc_folders: bool = False,
    ) -> int:
        '''
        Remove locales from existing locale list for target.
        Changes DefaultEditor.ini and ini files in Config/Localization.
        By default, does NOT delete locale folders in Content/Localization.

        Args:
            locales_to_remove: list of locales to add, duplicates will be ignored
        '''

        if type(locales_to_remove) is str:
            locales_to_remove = [locales_to_remove]

        if len(list(dict.fromkeys(locales_to_remove))) != len(locales_to_remove):
            raise ValueError('Supplied locales_to_remove list contains duplicates.')

        native_culture = self.get_native_locale()[1]

        if native_culture in locales_to_remove:
            raise ValueError(
                'Impossible to delete native locale. '
                'Change the native locale to a new locale first.'
            )

        locales = self.get_current_locales()
        number_of_locales = len(locales)
        number_of_locales_to_remove = len(locales_to_remove)

        if locales is None:
            raise Exception('Could not get current locales for target.')
        locales = [loc for loc in locales if loc not in locales_to_remove]

        if number_of_locales - number_of_locales_to_remove != len(locales):
            print(
                'Not all locales from locales_to_remove were found and removed '
                'from the existing locales list.'
            )

        return self.replace_all_locales(
            locales, delete_obsolete_loc_folders=delete_obsolete_loc_folders
        )

    def _update_default_editor_ini(
        self,
        native_locale_index: int,
        locales: list[str],
    ) -> int:
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

        return 0

    # TODO: refactor update_loc_ini_native / non_native into one function
    def _update_target_loc_ini_native(
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

    def _update_target_loc_ini_no_native(
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
        processed = False

        for s in strings:
            if s.startswith(self._task_ini_culture_line_start):
                if processed:
                    continue

                processed = True
                new_config_lines += [
                    self._task_ini_culture_line_format.format(culture=locale)
                    for locale in locales
                ]
                continue

            new_config_lines.append(s)

        with open(self.project_path / ini.format(loc_target=self.name), 'w') as f:
            f.writelines(new_config_lines)
        pass

    def _rename_loc_folder(
        self,
        old_name: str,
        new_name: str,
    ) -> int:
        '''
        Internal: renames folder in Content/Localization
        '''
        folder_path = self.project_path / self._locale_folder_pattern.format(
            loc_target=self.name, locale=old_name
        )

        if not folder_path.exists():
            raise ValueError(
                f'Folder for locale old_name not found in '
                f'{self._loc_root.format(loc_target=self.name)}'
            )

        new_folder_path = self.project_path / self._locale_folder_pattern.format(
            loc_target=self.name, locale=new_name
        )

        if new_folder_path.exists():
            raise ValueError(
                f'Folder for locale new_name already exists in '
                f'{self._loc_root.format(loc_target=self.name)}'
            )

        folder_path.rename(new_folder_path)

        return 0

    def _delete_loc_folder(
        self,
        name: str,
    ) -> int:
        '''
        Internal: deletes folder in Content/Localization
        '''
        folder_path = self.project_path / self._locale_folder_pattern.format(
            loc_target=self.name, locale=name
        )

        if not folder_path.exists():
            raise ValueError(
                f'Folder for locale old_name not found in '
                f'{self._loc_root.format(loc_target=self.name)}'
            )

        folder_path.unlink()

        return 0

    def replace_all_locales(
        self,
        new_locales: list[str],
        *,
        keep_native_locale: bool = True,
        new_native_locale: str = None,
        new_native_locale_index: int = None,
        delete_obsolete_loc_folders: bool = False,
    ) -> int:
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

        locales = self.get_current_locales()
        native_locale = self.get_native_locale()[1]

        if keep_native_locale and native_locale not in new_locales:
            raise ValueError(
                'keep_native_locale is true but current native locale '
                'is not present in the new_locales list'
            )

        if keep_native_locale:
            new_native_locale = native_locale

        new_native_locale_index = new_locales.index(new_native_locale)

        self._update_default_editor_ini(new_native_locale_index, new_locales)

        for ini in self._loc_task_inis:
            self._update_target_loc_ini_native(
                ini.format(loc_target=self.name), new_native_locale, new_locales
            )

        for ini in self._loc_task_inis_no_native_culture:
            self._update_target_loc_ini_no_native(
                ini.format(loc_target=self.name), new_native_locale, new_locales
            )

        if delete_obsolete_loc_folders:
            for name in [loc for loc in locales if loc not in new_locales]:
                self._delete_loc_folder(name)

        return 0

    def rename_locale(
        self,
        old_name: str,
        new_name: str,
        *,
        rename_loc_folder: bool = True,
    ) -> int or None:
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

        if new_name == old_name:
            raise ValueError('Locale names old_name and new_name identical.')

        locales = self.get_current_locales()
        native_locale_index, native_locale = self.get_native_locale()

        if old_name not in locales:
            raise ValueError('Locale old_name not found in current locales.')

        if new_name in locales:
            raise ValueError(
                'Locale new_name already in current locales. '
                'Impossible to rename or it would create a duplicate locale.'
            )

        locales[locales.index(old_name)] = new_name

        self.replace_all_locales(
            locales,
            keep_native_locale=False,
            new_native_locale_index=native_locale_index,
        )

        if rename_loc_folder:
            return self._rename_loc_folder(old_name, new_name)

        return 0


class UnrealProject:
    '''
    A class to find and store paths, localization targets,
    and other UE project information, and to manipulate
    files and within Unreal.

    Some of the functions require `unreal` module to be available
    (the script using them should be launched from Unreal editor).
    '''

    def __init__(script_path='Content/Python', uproject_path=None, engine_path=None):
        '''
        Parameters
        ----------
        script_path : str
            Script location, absolute or relative to the project directory.

        uproject_path : str
            Project directory path, absolute or relative to the script path.
            If set to None, the script will try to find the uproject file.
            See :meth:`UnrealProject.find_uproject`

        engine_path : str
            Project directory path, absolute or relative to the script path.
            If set to None, the script will try to find the engine.
            See :meth:`UnrealProject.find_engine`
        '''
        pass

    def find_uproject():
        pass

    def find_engine():
        pass

    def find_loc_targets():
        pass

    def get_p4_settings():
        pass

    def patch_manifest_dependencies():
        pass

    project_path = ''
    project_file = ''

    content_path = ''

    engine_root = ''

    ue_cmd_file = ''

    loc_targets = []
