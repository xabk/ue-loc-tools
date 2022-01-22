from zipfile import ZipFile
import shutil
from libraries import crowdin
import requests
from pathlib import Path
from time import sleep
from loguru import logger

# TODO: Add config file support
# TODO: Move parameters to config file

CONTENT_PATH = ""  # If empty, the script expects itself to be in Content/Python folder of the project
# and resolves relative project paths accordingly: Content/Python/../Localization
# otherwise, it's CONTENT_PATH/Localization

ZIP_NAME = Path('Temp/LocFilesTemp.zip')
TMP_DIR = Path('Temp/LocFilesTemp')
LOCALES_TO_DELETE = ['en-US-POSIX']

TARGETS = ['Game']
DEST_DIR = 'Localization/{target}/'


def build_and_download(zip_name=ZIP_NAME, tmp_dir=TMP_DIR):
    crowd_cli = crowdin.init_crowdin()

    build_data = crowdin.check_or_build(crowd_cli)

    if build_data['status'] == 'finished':
        logger.info(
            f'Build status and progress: {build_data["status"]} / {build_data["progress"]}'
        )
        build_data = crowdin.check_or_build(crowd_cli, build_data)
    else:
        while not 'url' in build_data:
            logger.info(
                f'Build status and progress: {build_data["status"]} / {build_data["progress"]}'
            )
            sleep(10)
            build_data = crowdin.check_or_build(crowd_cli, build_data)

    logger.info(
        f'Build compelete. Trying to download {build_data["url"]} to: {zip_name}'
    )

    response = requests.get(build_data['url'])
    zip_name.touch(exist_ok=True)
    zip_name.write_bytes(response.content)

    logger.info('Download complete.')


def unzip_file(zip_name=ZIP_NAME, tmp_dir=TMP_DIR):

    logger.info('Unzipping the file...')
    with ZipFile(zip_name, 'r') as zipfile:
        zipfile.extractall(tmp_dir)

    logger.info(f'Extracted to {tmp_dir}')


def process_target(t: str, tmp_dir=TMP_DIR, dest_dir=DEST_DIR) -> bool:
    logger.info(f'---\nProcessing localization target: {t}')
    if not (tmp_dir / t).is_dir():
        logger.error(f'{tmp_dir / t} directory not found for target {t}')
        return False

    logger.info(f'Removing locales we do not want to overwrite: {LOCALES_TO_DELETE}')

    for f in LOCALES_TO_DELETE:
        if (tmp_dir / t / f).is_file():
            (tmp_dir / t / f).unlink()
        elif (tmp_dir / t / f).is_dir():
            shutil.rmtree(tmp_dir / t / f)

    if CONTENT_PATH and Path(CONTENT_PATH).is_dir():
        dest_dir = Path(CONTENT_PATH) / dest_dir.format(target=t)
    else:
        logger.info(
            'Resolving target directory assuming the file is in /Game/Content/Python/'
        )
        dest_dir = Path(__file__).absolute().parent.parent / dest_dir.format(target=t)
        logger.info(dest_dir)

    logger.info(f'Destination directory: {dest_dir}')

    logger.info('Copying PO files...')

    processed = []
    directories = [f for f in (tmp_dir / t).glob('*') if f.is_dir()]
    for dir in directories:
        src_path = dir / f'{t}.po'
        dst_path = dest_dir / dir.name / f'{t}.po'
        if src_path.exists() and dst_path.exists():
            logger.info(f'Moving {src_path} to {dst_path}')
            shutil.move(src_path, dst_path)
            processed += [dir.name]
        else:
            logger.warning(
                f'Skip: {src_path} / {src_path.exists()} → {dst_path} / {dst_path.exists()}'
            )

    logger.info(f'Locales processed: {len(processed)} >> {processed}\n')

    if len(processed) > 0:
        return True

    return False


def main():
    logger.add(
        'logs/locsync.log',
        rotation='10MB',
        retention='1 month',
        enqueue=True,
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
    )

    logger.info(
        '--- Build and download from Crowdin, extract and move to Localization directory ---'
    )

    build_and_download()

    unzip_file()

    logger.info(f'Targets to process ({len(TARGETS)}): {TARGETS}')

    targets_processed = []
    for t in TARGETS:
        if process_target(t):
            targets_processed += [t]

    if len(targets_processed) > 0:
        logger.info(
            f'Targets processed ({len(targets_processed)}): {targets_processed}'
        )
        ZIP_NAME.unlink()
        shutil.rmtree(TMP_DIR)
        logger.info('--- Build, download, and move script end ---')
        return 0

    return 1


if __name__ == "__main__":
    main()
