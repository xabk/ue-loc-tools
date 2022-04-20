# Has to be launched via Unreal to work, e.g.:
# ../../../../Engine/Binaries/Win64/UE4Editor-cmd.exe Games/YourGame/YourGame.uproject -run=pythonscript -script="reimport-datatables.py"
# Add -stdout -FullStdOutLogOutput for full output
# Use -script="script.py any parameters" to pass parameters to script
# ../../../../Engine/Binaries/Win64/UE4Editor-cmd.exe Games/FactoryGame/FactoryGame.uproject -run=pythonscript -script="reimport-datatables.py task-list-name"

import unreal

import re
from pathlib import Path

assets_to_reimport = []

CFG_FILE = 'Python/base.config.yaml'  # Relative to Content directory


@unreal.uclass()
class GetEditorAssetLibrary(unreal.EditorAssetLibrary):
    pass


def logw(message):
    unreal.log_warning(message)


def main():

    logw('\n\n\n------ REIMPORT DATATABLES SCRIPT ------\n')

    config_file = Path(unreal.Paths.project_content_dir()) / CFG_FILE

    if not config_file.exists():
        logw(f'Config file not found: {config_file}. Aborting.')
        return

    logw(f'Trying to get asset list from config: {config_file}')

    with open(config_file, 'r') as f:
        s = f.readlines()

    i = 0
    done = False
    in_section = False
    while True:
        if done or i >= len(s):
            break

        if not in_section and re.match(r'\s*ue-reimport-assets:.*', s[i]):
            i += 1
            if not i >= len(s) and re.match(r'\s*assets_to_reimport: \[.*', s[i]):
                in_section = True
                i += 1
                continue

        if not in_section:
            i += 1
            continue

        if re.match('\s*].*', s[i]):
            break
        asset = re.search(r'(?<=")[^"]*(?=",?$)', s[i].strip())
        if asset and re.match(r'^[^\']+\'[^\']+\'$', asset.group()):
            assets_to_reimport.append(asset.group())
        else:
            logw(f'Couldn\'t parse line in config: {s[i]}')

        i += 1

    logw(f'Assets to reimport: {assets_to_reimport}')

    editorAssetLib = GetEditorAssetLibrary()

    for assetPath in assets_to_reimport:
        asset = editorAssetLib.find_asset_data(assetPath).get_asset()

        task = unreal.AssetImportTask()

        task.filename = asset.get_editor_property(
            'asset_import_data'
        ).get_first_filename()
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


# Run the script if the isn't imported
if __name__ == "__main__":
    main()
