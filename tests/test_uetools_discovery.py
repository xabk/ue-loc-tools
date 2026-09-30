"""Finding the engine and the UE version when the config says neither.

Setting a project up by hand has gone wrong in the same places every time: an
engine path that walked a level too far, and a UE4 project taken for UE5 --
which decides where Perforce settings are read from. Both are answerable from
the files.

The layouts below are the four real ones: an engine directly above the project,
an engine in a folder of its own beside it, a project nested inside the engine
tree, and a project that builds its own editor into its own Binaries.
"""

import json

import pytest

from libraries.uetools import UEProject

P4_SETTINGS = (
    '[PerforceSourceControl.PerforceSourceControlSettings]\n'
    'Port=example:1666\n'
    'UserName=user\n'
    'Workspace=workspace\n'
)

UE4 = 'UE4Editor-Cmd.exe'
UE5 = 'UnrealEditor-Cmd.exe'


def make_engine(root, binary=UE5, version=None):
    win64 = root / 'Engine' / 'Binaries' / 'Win64'
    win64.mkdir(parents=True, exist_ok=True)
    if binary:
        (win64 / binary).write_text('')
    if version is not None:
        build = root / 'Engine' / 'Build'
        build.mkdir(parents=True, exist_ok=True)
        (build / 'Build.version').write_text(json.dumps({'MajorVersion': version}))
    return root


def make_project(root):
    (root / 'Content' / 'Localization').mkdir(parents=True, exist_ok=True)
    (root / 'Config' / 'Localization').mkdir(parents=True, exist_ok=True)
    (root / 'Config' / 'DefaultEditor.ini').write_text('')
    (root / 'Game.uproject').write_text('{}')
    for where in ('Windows', 'WindowsEditor'):
        saved = root / 'Saved' / 'Config' / where
        saved.mkdir(parents=True, exist_ok=True)
        (saved / 'SourceControlSettings.ini').write_text(P4_SETTINGS)
    return root


# --- the four real shapes, with nothing supplied but the project


def test_an_engine_directly_above_the_project(tmp_path):
    """Satisfactory and Fellowship."""
    make_engine(tmp_path, UE5, version=5)
    project = make_project(tmp_path / 'FactoryGame')

    ue = UEProject(project_path=str(project))

    assert ue.engine_path == tmp_path.resolve()
    assert ue.version == 5


def test_an_engine_in_a_folder_of_its_own(tmp_path):
    """Goat 1 keeps its engine at Engine/Code/ beside the project, so the
    engine root is not an ancestor of the project at all."""
    make_engine(tmp_path / 'Engine' / 'Code', UE4, version=4)
    project = make_project(tmp_path / 'Goatsim_UE4')

    ue = UEProject(project_path=str(project))

    assert ue.engine_path == (tmp_path / 'Engine' / 'Code').resolve()
    assert ue.version == 4


def test_a_project_nested_inside_the_engine_tree(tmp_path):
    """Goat 3 sits at UE4/Games/GoatGame."""
    make_engine(tmp_path / 'UE4', UE4, version=4)
    project = make_project(tmp_path / 'UE4' / 'Games' / 'GoatGame')

    ue = UEProject(project_path=str(project))

    assert ue.engine_path == (tmp_path / 'UE4').resolve()
    assert ue.version == 4


def test_an_editor_built_into_the_project(tmp_path):
    """Rabbithole ships IntoTheUnwellEditor-Cmd.exe in the project. Neither the
    engine root nor the standard names lead to it."""
    make_engine(tmp_path, UE5, version=5)
    project = make_project(tmp_path / 'Rabbithole')
    own = project / 'Binaries' / 'Win64'
    own.mkdir(parents=True)
    (own / 'IntoTheUnwellEditor-Cmd.exe').write_text('')

    ue = UEProject(project_path=str(project))

    assert ue.cmd_binary_path.name == 'IntoTheUnwellEditor-Cmd.exe'
    assert ue.version == 5


# --- the version, which picks where Perforce settings are read from


def test_build_version_beats_the_binary_name(tmp_path):
    """The name says UE5. Build.version says 4, and it is right."""
    make_engine(tmp_path, UE5, version=4)
    project = make_project(tmp_path / 'Game')

    ue = UEProject(
        project_path=str(project),
        engine_path=str(tmp_path),
        unreal_binary=f'Engine/Binaries/Win64/{UE5}',
    )

    assert ue.version == 4


def test_a_custom_editor_name_takes_its_version_from_build_version(tmp_path):
    """Reading 5 out of 'not UE4Editor' is how a UE4 project ends up looking
    for its Perforce settings in the UE5 location."""
    make_engine(tmp_path, binary=None, version=4)
    project = make_project(tmp_path / 'Game')
    own = project / 'Binaries' / 'Win64'
    own.mkdir(parents=True)
    (own / 'MyGameEditor-Cmd.exe').write_text('')

    ue = UEProject(
        project_path=str(project),
        engine_path=str(project),
        unreal_binary='Binaries/Win64/MyGameEditor-Cmd.exe',
    )

    # engine_path is the project here, so there is no Build.version to read and
    # the name is all there is. It is not UE4Editor, so it reads as 5.
    assert ue.version == 5


def test_an_explicit_version_still_wins(tmp_path):
    """Build.version says 5. The caller says 4, and the caller decides."""
    make_engine(tmp_path, UE4, version=5)
    project = make_project(tmp_path / 'Game')

    ue = UEProject(ue_major_version=4, project_path=str(project))

    assert ue.version == 4


# --- the search has to stay inside this workspace


def test_a_neighbouring_workspace_is_not_used(tmp_path):
    """A machine holds several checkouts side by side. Reaching into one of
    them would configure this project against an engine that has nothing to do
    with it."""
    neighbour = tmp_path / 'other-workspace'
    make_engine(neighbour, UE5, version=5)

    workspace = tmp_path / 'this-workspace'
    project = make_project(workspace / 'Game')

    with pytest.raises(ValueError, match='does not exist or is not a directory'):
        UEProject(project_path=str(project))


def test_no_engine_anywhere_says_so(tmp_path):
    project = make_project(tmp_path / 'Game')

    with pytest.raises(ValueError, match='does not exist or is not a directory'):
        UEProject(project_path=str(project))
