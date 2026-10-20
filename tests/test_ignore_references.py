"""Rules that keep known-good missing references out of the recap.

Every line here is copied from the Satisfactory run of 2026-10-15, where
23 missing entries were reported and 6 of them were real.
"""

import pytest

from libraries.findings import Findings
from libraries.ue_findings import (
    MISSING_ENTRIES,
    IgnoreRule,
    collect,
    read_ignore_rules,
)

NAMED_CHEAT = (
    'LogGatherStringTableReferencesCommandlet: Warning: '
    '<MissingStringTableReference> StringTable: [OptionsInputs_Data], '
    'Key: [Player/Cheats/Teleport] Context: '
    '/Game/FactoryGame/Inputs/Player/MC_PlayerCheats.MC_PlayerCheats'
    ':PlayerMappableKeySettings_1.DisplayName'
)
NAMED_FICSMAS = (
    'LogGatherStringTableReferencesCommandlet: Warning: '
    '<MissingStringTableReference> StringTable: [FICSMAS_UI], '
    'Key: [Calendar/2020] Context: '
    '/Game/FactoryGame/Events/Christmas/UI/Calendar/BPW_ChristmasCalendar'
    '.BPW_ChristmasCalendar_C:WidgetTree.Widget_Window_DarkMode.mTitleText'
)
PLAIN_KICKED = (
    "LogStringTable: Warning: Failed to find string table entry for "
    "'Menus_UI' 'Players/Messages/YouGotKicked'. "
    'Did you forget to add a string table redirector?'
)
PLAIN_CHEAT = (
    "LogStringTable: Warning: Failed to find string table entry for "
    "'Player_UI' 'BuildMenu/Tabs/Cheats'. "
    'Did you forget to add a string table redirector?'
)

# Satisfactory lists every cleared reference by name. A '*Cheat*' glob would
# also hide strings nobody has looked at yet.
SATISFACTORY_RULES = [
    {
        'entry': 'OptionsInputs_Data,Player/Cheats/Teleport',
        'reason': 'Dev-only cheat string.',
    },
    {'entry': 'Player_UI,BuildMenu/Tabs/Cheats', 'reason': 'Dev-only cheat string.'},
    {'entry': 'FICSMAS_UI,Calendar/2020', 'reason': 'Retired FICSMAS year.'},
]


@pytest.fixture
def rules():
    return read_ignore_rules(SATISFACTORY_RULES)


def entries(findings: Findings) -> set[str]:
    return {f.key for f in findings.by_key.values() if f.category == MISSING_ENTRIES}


def test_named_reference_is_ignored_but_counted(rules):
    findings = Findings()
    assert collect(findings, NAMED_CHEAT, ignore=rules), 'still a handled line'
    assert entries(findings) == set()
    assert findings.ignored == {'OptionsInputs_Data,Player/Cheats/Teleport'}


def test_plain_warning_is_ignored_too(rules):
    """The text gather reports the same entries without naming an asset."""
    findings = Findings()
    collect(findings, PLAIN_CHEAT, ignore=rules)
    assert entries(findings) == set()
    assert findings.ignored == {'Player_UI,BuildMenu/Tabs/Cheats'}


def test_unmatched_reference_still_reported(rules):
    findings = Findings()
    collect(findings, PLAIN_KICKED, ignore=rules)
    assert entries(findings) == {'Menus_UI,Players/Messages/YouGotKicked'}
    assert not findings.ignored


def test_asset_pattern_must_match_as_well():
    """The same entry from somewhere else is a different question."""
    rules = read_ignore_rules(
        [{'entry': 'FICSMAS_UI,Calendar/2020', 'asset': '*/SomewhereElse/*'}]
    )
    findings = Findings()
    collect(findings, NAMED_FICSMAS, ignore=rules)
    assert entries(findings) == {'FICSMAS_UI,Calendar/2020'}


def test_asset_matched_as_the_recap_prints_it():
    """`_C` is collapsed before the rule sees the path, so a rule written
    from a recap line matches the raw log line it came from."""
    rules = read_ignore_rules(
        [
            {
                'entry': 'FICSMAS_UI,Calendar/2020',
                'asset': '*/BPW_ChristmasCalendar.BPW_ChristmasCalendar:*',
            }
        ]
    )
    findings = Findings()
    collect(findings, NAMED_FICSMAS, ignore=rules)
    assert findings.ignored == {'FICSMAS_UI,Calendar/2020'}


def test_entry_glob_still_works_for_a_project_that_wants_one():
    rules = read_ignore_rules([{'entry': 'Player_UI,BuildMenu/*'}])
    findings = Findings()
    collect(findings, PLAIN_CHEAT, ignore=rules)
    assert findings.ignored == {'Player_UI,BuildMenu/Tabs/Cheats'}


def test_omitted_asset_matches_anything():
    rule = IgnoreRule(entry='Player_UI,BuildMenu/Tabs/Cheats')
    assert rule.matches('Player_UI,BuildMenu/Tabs/Cheats', '')
    assert rule.matches('Player_UI,BuildMenu/Tabs/Cheats', '/Game/Anything')


def test_rule_matching_everything_is_refused():
    assert read_ignore_rules([{'reason': 'oops'}]) == []
    assert read_ignore_rules([{'entry': '*', 'asset': '*'}]) == []


def test_malformed_rules_are_skipped():
    assert read_ignore_rules(['OptionsInputs_Data,Player/Cheats/Teleport']) == []
    assert read_ignore_rules(None) == []


def test_no_rules_changes_nothing():
    findings = Findings()
    collect(findings, NAMED_CHEAT)
    assert entries(findings) == {'OptionsInputs_Data,Player/Cheats/Teleport'}
    assert not findings.ignored


def test_merge_carries_ignored_across_tasks():
    first, second = Findings(), Findings()
    first.ignore('A,one')
    second.ignore('B,two')
    first.merge(second)
    assert first.ignored == {'A,one', 'B,two'}
