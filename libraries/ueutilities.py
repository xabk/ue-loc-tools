from pathlib import Path

try:
    import unreal

    UNREAL = True
except:
    UNREAL = False


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
