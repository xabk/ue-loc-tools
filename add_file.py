from libraries.crowdin import CSPCrowdinClient
from pathlib import Path

# TODO: Add config file support
# TODO: Move parameters to config file

CONTENT_PATH = ''

TARGETS = ['Game']

SRC_LOCALE = 'io'

FNAME = '{target}.po'

ORG = 'org'

crowdin = CSPCrowdinClient(token='TOKEN', organization=ORG)


def main():
    print(crowdin.get_data())
    content_path = ''
    if CONTENT_PATH != "" and Path(CONTENT_PATH).is_dir():
        content_path = Path(CONTENT_PATH)
    else:
        print(
            'Resolving target directory assuming the file is in /Game/Content/Python/'
        )
        content_path = Path(__file__).absolute().parent

    print('Content path:', content_path)

    targets_processed = []

    for target in TARGETS:
        fpath = content_path / Path(FNAME.format(target=target, locale=SRC_LOCALE))
        print(fpath.name)
        print('Uploading file:', fpath)
        r = crowdin.add_file(fpath, 'gettext_unreal')
        if r == True:
            targets_processed += [target]
            print('File added.')
        else:
            print('Something went wrong. Here\'s the last response from Crowdin:', r)

    if len(targets_processed) > 0:
        print('Targets processed', len(targets_processed), targets_processed)
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
