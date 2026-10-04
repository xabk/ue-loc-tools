"""The gather commandlet announces every package it touches, twice.

The log file keeps all of it, because that is the record of what the
commandlet did. The console gets a line every percent, and at least one a
second while it is working, so a package that takes a while to load looks
like progress rather than a hang.
"""

import re

from tasks.ue_loc_gather_cmd import (
    MISSING_ST_ENTRY,
    PROGRESS,
    UnrealLocGatherCommandlet,
)

GATHERING = (
    "LogGatherTextFromAssetsCommandlet: Display: [ 64.34%] "
    "Gathering package: '/Game/FactoryGame/Inputs/Player/MC_Player'..."
)
LOADING = (
    "LogGatherTextFromAssetsCommandlet: Display: [  0.03%] "
    "Loading package: '/Game/FactoryGame/-Shared/Blueprint/BP_Voice'..."
)
MISSING = (
    "LogStringTable: Warning: Failed to find string table entry for "
    "'Menus_UI' 'Players/Messages/YouGotKicked'. Did you forget to add a "
    "string table redirector?"
)


def captured(fn, *args):
    import loguru

    seen = []
    handle = loguru.logger.add(lambda m: seen.append(m), level='INFO')
    fn(*args)
    loguru.logger.remove(handle)
    return ''.join(seen)


def task():
    return UnrealLocGatherCommandlet.__new__(UnrealLocGatherCommandlet)


def test_progress_reads_percent_phase_and_package():
    m = re.search(PROGRESS, GATHERING)
    assert m.group(1) == '64.34'
    assert m.group(2) == 'Gathering'
    assert m.group(3) == '/Game/FactoryGame/Inputs/Player/MC_Player'


def test_loading_and_gathering_are_both_progress():
    """Two phases of one package, logged back to back at the same percent."""
    assert re.search(PROGRESS, LOADING).group(2) == 'Loading'
    assert re.search(PROGRESS, GATHERING).group(2) == 'Gathering'


def test_a_missing_entry_yields_its_table_and_key():
    assert re.search(MISSING_ST_ENTRY, MISSING).groups() == (
        'Menus_UI', 'Players/Messages/YouGotKicked')


def test_an_ordinary_line_is_not_mistaken_for_progress():
    for line in (MISSING, 'LogInit: Display: something [100%] done', ''):
        assert re.search(PROGRESS, line) is None


def shown(stream, step=1, heartbeat=1.0):
    """The console rule as run_tasks applies it: (percent, clock) in, the
    ones the console is told about out."""
    next_percent, last_shown, out = 0.0, 0.0, []
    for percent, now in stream:
        if percent >= next_percent or now - last_shown >= heartbeat:
            out.append((percent, now))
            next_percent = (int(percent // step) + 1) * step
            last_shown = now
    return out


def test_the_console_gets_one_line_per_percent():
    instant = [(i / 10, 0.0) for i in range(1, 1001)]
    assert len(shown(instant)) == 101  # 0.1% then every whole percent


def test_the_last_line_is_a_hundred_percent():
    assert shown([(i / 10, 0.0) for i in range(1, 1001)])[-1][0] == 100.0


def test_a_slow_percent_still_reports_every_second():
    """One percent that takes ten seconds must not look like a hang."""
    crawl = [(1.0, float(t)) for t in range(10)]
    assert len(shown(crawl)) == 10


def test_a_fast_run_is_not_padded_by_the_heartbeat():
    """Everything inside one second, so only the percent rule applies."""
    quick = [(i / 10, 0.05) for i in range(1, 1001)]
    assert len(shown(quick)) == 101


def test_missing_entries_are_named_once_with_their_reference_count():
    text = captured(task().report_missing_entries, {('Menus_UI', 'Foo/Bar'): 3})
    assert 'Menus_UI,Foo/Bar' in text
    assert '(3 references)' in text


def test_nothing_is_logged_when_nothing_is_missing():
    assert captured(task().report_missing_entries, {}) == ''


def test_a_failed_run_says_where_it_stopped():
    """Only the position: the lines themselves are already in the log."""
    text = captured(task().report_where_it_stopped, (73.2, 'Gathering', '/Game/Foo'))
    assert "'/Game/Foo'" in text and '73%' in text and 'gathering' in text


def test_nothing_is_claimed_when_there_is_nothing_to_claim():
    assert captured(task().report_where_it_stopped, None) == ''
