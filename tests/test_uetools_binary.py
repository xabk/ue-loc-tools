"""UEProject has to find the editor binary across the layouts we ship to.

Standard engines keep it under Engine/; a project that renames its editor
target keeps it beside the project and needs unreal_binary to say so.
"""

import pytest

from libraries.uetools import UEProject

P4_SETTINGS = (
    '[PerforceSourceControl.PerforceSourceControlSettings]\n'
    'Port=example:1666\n'
    'UserName=user\n'
    'Workspace=workspace\n'
)


def make_project(root, binary_relative_to_engine, p4_config_dir):
    project = root / 'Proj'
    (project / 'Content' / 'Localization').mkdir(parents=True)
    (project / 'Config' / 'Localization').mkdir(parents=True)
    (project / 'Config' / 'DefaultEditor.ini').write_text('')
    (project / 'Game.uproject').write_text('{}')

    saved = project / 'Saved' / 'Config' / p4_config_dir
    saved.mkdir(parents=True)
    (saved / 'SourceControlSettings.ini').write_text(P4_SETTINGS)

    engine = root / 'Eng'
    binary = engine / binary_relative_to_engine
    binary.parent.mkdir(parents=True)
    binary.write_text('')

    return project, engine


LAYOUTS = [
    ('Engine/Binaries/Win64/UE4Editor-cmd.exe', 'Windows', None, 4),
    ('Engine/Binaries/Win64/UnrealEditor-Cmd.exe', 'WindowsEditor', None, 5),
    ('Binaries/Win64/UE4Editor-cmd.exe', 'Windows', None, 4),
    (
        'Binaries/Win64/RenamedEditor-Cmd.exe',
        'WindowsEditor',
        'Binaries/Win64/RenamedEditor-Cmd.exe',
        5,
    ),
]


@pytest.mark.parametrize('binary, p4_dir, unreal_binary, version', LAYOUTS)
def test_the_binary_is_found(tmp_path, binary, p4_dir, unreal_binary, version):
    project, engine = make_project(tmp_path, binary, p4_dir)

    ue = UEProject(
        project_path=str(project),
        engine_path=str(engine),
        unreal_binary=unreal_binary,
    )

    assert ue.cmd_binary_path.is_file()
    assert ue.cmd_binary_path == (engine / binary).resolve()
    assert ue.version == version


def test_a_renamed_target_is_unreachable_without_unreal_binary(tmp_path):
    project, engine = make_project(
        tmp_path, 'Binaries/Win64/RenamedEditor-Cmd.exe', 'WindowsEditor'
    )

    with pytest.raises(ValueError, match='No Unreal CMD binary found'):
        UEProject(project_path=str(project), engine_path=str(engine))


def test_an_explicit_version_is_kept(tmp_path):
    project, engine = make_project(
        tmp_path, 'Binaries/Win64/RenamedEditor-Cmd.exe', 'Windows'
    )

    ue = UEProject(
        ue_major_version=4,
        project_path=str(project),
        engine_path=str(engine),
        unreal_binary='Binaries/Win64/RenamedEditor-Cmd.exe',
    )

    assert ue.version == 4
