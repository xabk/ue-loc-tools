"""An empty translation in the CSV either clears the PO entry or leaves it.

A project with Skip Untranslated Strings exports every row, with an empty
target where nothing is translated. Imported over another project's
translations, those empty targets would wipe them, so skip_empty_translations
leaves the PO entry alone instead.
"""

import csv

import pytest

from libraries import polib
from tasks.build_and_download import BuildAndDownloadTranslations

FIELDS = ['Key', 'SourceString', 'TargetString', 'MaxLength', 'Labels', 'CrowdinContext']


def po_with(entries: dict[str, tuple[str, str]]) -> polib.POFile:
    """key -> (source, translation already in the PO)"""
    po = polib.POFile()
    for key, (source, translation) in entries.items():
        po.append(polib.POEntry(msgctxt=key, msgid=source, msgstr=translation))
    return po


def csv_with(tmp_path, rows: dict[str, tuple[str, str]]):
    """key -> (source on Crowdin, translation on Crowdin)"""
    path = tmp_path / 'Game.csv'
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for key, (source, translation) in rows.items():
            writer.writerow(
                {'Key': key, 'SourceString': source, 'TargetString': translation}
            )
    return [path]


@pytest.fixture
def task():
    return BuildAndDownloadTranslations()


def msgstr(po: polib.POFile, key: str) -> str:
    return next(e.msgstr for e in po if e.msgctxt == key)


def test_empty_translation_clears_the_entry_by_default(task, tmp_path):
    po = po_with({'NS,a': ('Sword', 'Épée (AI)')})

    findings = task.load_csv_files_to_po(csv_with(tmp_path, {'NS,a': ('Sword', '')}), po)

    assert msgstr(po, 'NS,a') == ''
    assert findings.empty_skipped == set()


def test_empty_translation_keeps_the_entry_when_skipping(task, tmp_path):
    task.skip_empty_translations = True
    po = po_with({'NS,a': ('Sword', 'Épée (AI)')})

    findings = task.load_csv_files_to_po(csv_with(tmp_path, {'NS,a': ('Sword', '')}), po)

    assert msgstr(po, 'NS,a') == 'Épée (AI)'
    assert findings.empty_skipped == {'NS,a'}


def test_a_real_translation_always_wins(task, tmp_path):
    task.skip_empty_translations = True
    po = po_with({'NS,a': ('Sword', 'Épée (AI)')})

    findings = task.load_csv_files_to_po(
        csv_with(tmp_path, {'NS,a': ('Sword', 'Lame')}), po
    )

    assert msgstr(po, 'NS,a') == 'Lame'
    assert findings.empty_skipped == set()


def test_whitespace_is_a_translation_not_an_empty_one(task, tmp_path):
    """Some sources are whitespace on purpose, and so are their translations."""
    task.skip_empty_translations = True
    po = po_with({'NS,a': (' ', 'old')})

    task.load_csv_files_to_po(csv_with(tmp_path, {'NS,a': (' ', ' ')}), po)

    assert msgstr(po, 'NS,a') == ' '


def test_skipping_holds_when_only_edge_whitespace_differs(task, tmp_path):
    task.skip_empty_translations = True
    po = po_with({'NS,a': ('Sword ', 'Épée (AI)')})

    findings = task.load_csv_files_to_po(csv_with(tmp_path, {'NS,a': ('Sword', '')}), po)

    assert msgstr(po, 'NS,a') == 'Épée (AI)'
    assert findings.whitespace_ignored == {'NS,a'}
    assert findings.empty_skipped == {'NS,a'}


def test_skipping_holds_when_source_mismatch_is_ignored(task, tmp_path):
    task.skip_empty_translations = True
    task.ignore_source_mismatch = True
    po = po_with({'NS,a': ('Sword', 'Épée (AI)')})

    findings = task.load_csv_files_to_po(csv_with(tmp_path, {'NS,a': ('Blade', '')}), po)

    assert msgstr(po, 'NS,a') == 'Épée (AI)'
    assert findings.mismatch_ignored == {'NS,a'}
    assert findings.empty_skipped == {'NS,a'}


def test_a_source_mismatch_is_still_reported(task, tmp_path):
    """Skipping empty translations does not hide a source that moved on."""
    task.skip_empty_translations = True
    po = po_with({'NS,a': ('Sword', 'Épée (AI)')})

    findings = task.load_csv_files_to_po(csv_with(tmp_path, {'NS,a': ('Blade', '')}), po)

    assert msgstr(po, 'NS,a') == 'Épée (AI)'
    assert set(findings.source_mismatch) == {'NS,a'}
    assert findings.empty_skipped == set()
