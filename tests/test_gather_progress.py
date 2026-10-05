"""The gather commandlet announces every package it touches, twice.

The log file keeps all of it, because that is the record of what the
commandlet did. The console gets a line every percent, and at least one a
second while it is working, so a package that takes a while to load looks
like progress rather than a hang.
"""

import re

from libraries.findings import Findings
from libraries.ue_findings import MISSING_ENTRIES, MISSING_ST_ENTRY, collect
from tasks.ue_loc_gather_cmd import (
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
    assert MISSING_ST_ENTRY.search(MISSING).groups() == (
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


def console(stream, step=1, heartbeat=1.0):
    """The same rule, plus the held line: progress as (percent, clock) and
    warnings as strings in, what the console is told out."""
    next_percent, last_shown, held, out = 0.0, 0.0, None, []
    for item in stream:
        if isinstance(item, str):
            if held:
                out.append(held)
                held = None
            out.append(item)
            continue
        percent, now = item
        if percent >= next_percent or now - last_shown >= heartbeat:
            out.append((percent, now))
            next_percent = (int(percent // step) + 1) * step
            last_shown = now
            held = None
        else:
            held = (percent, now)
    return out


def test_a_warning_is_preceded_by_the_package_it_came_from():
    """The throttle hid the packages in between."""
    out = console([(0.1, 0.0), (0.11, 0.0), (0.12, 0.0), 'Warning: no entry'])

    assert out == [(0.1, 0.0), (0.12, 0.0), 'Warning: no entry']


def test_the_package_is_not_repeated_when_it_was_just_shown():
    out = console([(0.1, 0.0), 'Warning: no entry'])

    assert out == [(0.1, 0.0), 'Warning: no entry']


def test_one_held_package_serves_every_warning_under_it():
    out = console([(0.1, 0.0), (0.11, 0.0), 'first', 'second'])

    assert out == [(0.1, 0.0), (0.11, 0.0), 'first', 'second']


def test_a_failed_run_says_where_it_stopped():
    """Only the position: the lines themselves are already in the log."""
    text = captured(task().report_where_it_stopped, (73.2, 'Gathering', '/Game/Foo'))
    assert "'/Game/Foo'" in text and '73%' in text and 'gathering' in text


def test_nothing_is_claimed_when_there_is_nothing_to_claim():
    assert captured(task().report_where_it_stopped, None) == ''



COLLISION = (
    "LogGatherTextFromAssetsCommandlet: Warning: Package '/Game/A/Build_Pipe' "
    "and '/Game/B/Build_Pipeline' have the same localization ID "
    "(8FC8078C4AE6323D1E17EB8D3FBA8278). Please reset one of these."
)
SOURCE_WARNING = (
    'LogGatherTextFromSourceCommandlet: Warning: Source/Foo/Public/Bar.h'
)
ENGINE_NOISE = 'LogEOSSDK: Warning: LogEOSP2P: Leave all connections'


def collected(lines, package=None):
    f = Findings()
    for line in lines:
        collect(f, line, package)
    return f


def test_a_missing_entry_is_keyed_by_what_is_wrong():
    f = collected([MISSING])
    assert len(f) == 1
    assert list(f.by_key)[0][1] == 'Menus_UI,Players/Messages/YouGotKicked'


def test_the_asset_is_recorded_when_there_is_one():
    f = collected([MISSING], package='/Game/FactoryGame/Profiling/Map_UI-Profile')
    assert list(f.by_key.values())[0].contexts == {
        'in /Game/FactoryGame/Profiling/Map_UI-Profile'
    }


def test_the_same_entry_from_two_places_is_one_finding():
    """One entry, however many times and wherever it was reported: every
    place that knew one is kept, and the ones that knew none add nothing."""
    f = collected([MISSING])
    f.add(MISSING_ENTRIES, 'Menus_UI,Players/Messages/YouGotKicked', 'in /Game/Foo')
    f.add(MISSING_ENTRIES, 'Menus_UI,Players/Messages/YouGotKicked', 'in /Game/Bar')
    assert len(f) == 1
    only = list(f.by_key.values())[0]
    assert only.occurrences == 3
    assert only.contexts == {'in /Game/Foo', 'in /Game/Bar'}


def test_a_collision_is_keyed_on_the_pair_either_way_round():
    f = collected([COLLISION])
    key = list(f.by_key)[0][1]
    assert key == '/Game/A/Build_Pipe and /Game/B/Build_Pipeline'


def test_a_gather_warning_is_collected():
    assert len(collected([SOURCE_WARNING])) == 1


def test_an_engine_warning_is_not_this_tools_business():
    """Forty-odd categories log during a gather; only the pipeline's count."""
    assert len(collected([ENGINE_NOISE])) == 0


def test_an_ordinary_line_is_collected_as_nothing():
    assert len(collected(['LogGatherTextCommandlet: Display: all fine'])) == 0


REF = ('LogGatherStringTableReferencesCommandlet: Warning: '
       '<MissingStringTableReference> StringTable: [FICSMAS_UI], '
       'Key: [Calendar/2020] Context: ')


def test_an_asset_and_its_generated_class_are_one_place():
    """Unreal names the asset, the _C class it compiles to, and the bytecode
    of the same function. Counting those separately trebles one problem."""
    f = collected([
        REF + '/Game/UI/BPW_Cal.BPW_Cal:WidgetTree.mTitleText',
        REF + '/Game/UI/BPW_Cal.BPW_Cal_C:WidgetTree.mTitleText',
    ])
    only = list(f.by_key.values())[0]
    assert only.occurrences == 2
    assert only.contexts == {'/Game/UI/BPW_Cal.BPW_Cal:WidgetTree.mTitleText'}


def test_the_bytecode_form_is_the_same_function():
    f = collected([
        REF + '/Game/UI/BPW_Cal.BPW_Cal_C:UpdateHeader [Script Bytecode]',
        REF + '/Game/UI/BPW_Cal.BPW_Cal:UpdateHeader',
    ])
    assert list(f.by_key.values())[0].contexts == {
        '/Game/UI/BPW_Cal.BPW_Cal:UpdateHeader'
    }


def test_two_real_places_stay_two():
    f = collected([
        REF + '/Game/UI/BC_Cheat.Default__BC_Cheat_C.mDisplayName',
        REF + '/Game/UI/SC_Cheat.Default__SC_Cheat_C.mDisplayName',
    ])
    assert len(list(f.by_key.values())[0].contexts) == 2
