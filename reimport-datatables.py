# Has to be launched via Unreal to work, e.g.:
# ../../../../Engine/Binaries/Win64/UE4Editor-cmd.exe Games/YourGame/YourGame.uproject -run=pythonscript -script="reimport-datatables.py"

# TODO: Add config file support
# TODO: Move parameters to config file

import unreal

assets_to_reimport = [
    "DataTable'/Game/FactoryGame/Interface/UI/DT_Credits_Community.DT_Credits_Community'",
    "DataTable'/Game/Localization/DT_OptionsMenuLanguages.DT_OptionsMenuLanguages'",
]


@unreal.uclass()
class GetEditorAssetLibrary(unreal.EditorAssetLibrary):
    pass


def logw(message):
    unreal.log_warning(message)


logw('\n\n\n------ REIMPORT DATATABLES SCRIPT ------\n')

editorAssetLib = GetEditorAssetLibrary()

for assetPath in assets_to_reimport:
    asset = editorAssetLib.find_asset_data(assetPath).get_asset()

    task = unreal.AssetImportTask()

    task.filename = asset.get_editor_property('asset_import_data').get_first_filename()
    task.destination_path = asset.get_path_name().rpartition('/')[0]
    task.destination_name = asset.get_name()
    task.replace_existing = True
    task.automated = True
    task.save = True

    factory = unreal.CSVImportFactory()
    factory.set_editor_property(
        'automated_import_settings',
        unreal.CSVImportSettings(asset.get_editor_property('row_struct')),
    )
    task.factory = factory

    logw(
        'Reimporting asset: '
        + task.destination_path
        + task.destination_name
        + ' from '
        + task.filename
    )

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

    asset_tools.import_asset_tasks([task])
    if len(task.result) == 1:
        logw('Reimported:' + task.result[0])

logw('\n\n\n------ END OF SCRIPT ------\n')
