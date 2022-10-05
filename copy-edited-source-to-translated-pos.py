import polib
from pathlib import Path
from loguru import logger

path = Path(__file__).parent
encoding = 'utf-8-sig'
targets = ['Game']
src_loc = 'en'

logger.add(
    'logs/locsync.log',
    rotation='10MB',
    retention='1 month',
    enqueue=True,
    format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
    level='INFO',
    encoding='utf-8',
)

logger.info(f'Targets top  found ({len(targets)}): {targets}')
logger.info(f'------------------------------------')


for target in targets:
    src_path = ((path / target) / src_loc) / f'{target}.po'
    src_po = polib.pofile(src_path, wrapwidth=0, encoding=encoding)
    src_entries = len(src_po)
    logger.info(f'Source PO: {src_path}')
    logger.info(f'Entries in source PO: {src_entries}')

    directories = [
        f for f in (path / target).glob('*') if f.is_dir() and not f.name == src_loc
    ]
    logger.info(f'Directories found ({len(directories)}): {directories}')
    logger.info(f'------------------------------------')

    processed = []
    for dir in directories:
        po_path = dir / f'{target}.po'
        po = polib.pofile(po_path, wrapwidth=0, encoding=encoding)
        logger.info(f'Processing target PO: {po_path}')
        logger.info(f'Entries in translated PO: {len(po)}')
        not_found = []
        changed_sources = []
        for entry in po:
            for src_entry in src_po:
                if src_entry.msgctxt == entry.msgctxt:
                    if not entry.msgid == src_entry.msgstr:
                        entry.msgid = src_entry.msgstr
                        changed_sources += [entry.msgctxt]
                    break
            else:
                not_found += [entry.msgctxt]
        logger.info(f'Updated ({len(changed_sources)}): {changed_sources}')
        logger.warning(f'Not found ({len(not_found)}): {not_found}')
        logger.info(f'------------------------------------\n')
        po.save()
