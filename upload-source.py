from libraries.crowdin import UECrowdinClient
from time import sleep
from pathlib import Path
from loguru import logger

# TODO: Add config file support
# TODO: Move parameters to config file

CONTENT_PATH = ''

TARGETS = ['Game']

SRC_LOCALE = 'io'

FNAME = 'Localization/{target}/{locale}/{target}.po'

crowdin_cli = UECrowdinClient('', None)


def main():
    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
    )

    logger.info('--- Upload source to Crowdin script start ---')

    content_path = ''
    if CONTENT_PATH != '' and Path(CONTENT_PATH).is_dir():
        content_path = Path(CONTENT_PATH)
    else:
        logger.info(
            'Resolving target directory assuming the file is in /Game/Content/Python/'
        )
        content_path = Path(__file__).absolute().parent.parent

    logger.info(f'Content path: {content_path}')

    targets_processed = []

    for target in TARGETS:
        fpath = content_path / Path(FNAME.format(target=target, locale=SRC_LOCALE))
        logger.info('Uploading file: {fpath}')
        r = crowdin_cli.update_file(fpath)
        if r == True:
            targets_processed += [target]
            logger.info('File updated.')
        else:
            logger.error(
                f'Something went wrong. Here\'s the last response from Crowdin: {r}'
            )

    if len(targets_processed) > 0:
        print(f'Targets processed: {len(targets_processed)} > {targets_processed}')
        return 0

    return 1


# Run the main functionality of the script if it's not imported
if __name__ == "__main__":
    main()
