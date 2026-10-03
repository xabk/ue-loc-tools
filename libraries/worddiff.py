"""Word-level diff for two versions of one string, rendered for a log.

Two sinks want two different things from the same finding. A terminal can
show the changed words in colour; a log file has to still make sense in a
text editor six months later, so it gets git's word-diff markers instead.

Colour is applied as a background rather than a foreground. Half the
differences worth seeing in localized text are whitespace -- a lost trailing
space, a leading space that should not be there -- and a coloured space on a
default background is a space.
"""

import re
import sys
from difflib import SequenceMatcher

# Keep whitespace as tokens of its own, so rebuilding is exact and a run of
# spaces can be the thing that differs.
_TOKENS = re.compile(r'\s+|\S+')

REMOVED_BG = '\x1b[41m'  # red
ADDED_BG = '\x1b[42m'  # green
BG_OFF = '\x1b[49m'  # background only, so the line keeps the level's colour


def _tokens(text: str) -> list[str]:
    return _TOKENS.findall(text)


def _spans(old: str, new: str) -> tuple[list[tuple[bool, str]], list[tuple[bool, str]]]:
    """Both sides as (is_changed, text) runs, each side marking only what is
    unique to it: the old side what was lost, the new side what was gained."""
    a, b = _tokens(old), _tokens(new)
    old_runs: list[tuple[bool, str]] = []
    new_runs: list[tuple[bool, str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b).get_opcodes():
        if tag in ('equal', 'delete', 'replace'):
            chunk = ''.join(a[i1:i2])
            if chunk:
                old_runs.append((tag != 'equal', chunk))
        if tag in ('equal', 'insert', 'replace'):
            chunk = ''.join(b[j1:j2])
            if chunk:
                new_runs.append((tag != 'equal', chunk))
    return old_runs, new_runs


def _coalesce(runs: list[tuple[bool, str]]) -> list[tuple[bool, str]]:
    """Join changed runs that are only separated by the space between two
    words, so a rewritten phrase reads as one change rather than one per
    word. The space joins them: it changed too, as part of the phrase."""
    out: list[tuple[bool, str]] = []
    for changed, text in runs:
        if out and out[-1][0] == changed:
            out[-1] = (changed, out[-1][1] + text)
        elif (
            len(out) >= 2
            and changed
            and out[-1][0] is False
            and not out[-1][1].strip()
            and out[-2][0] is True
        ):
            joined = out[-1][1] + text
            out.pop()
            out[-1] = (True, out[-1][1] + joined)
        else:
            out.append((changed, text))
    return out


def _render(runs: list[tuple[bool, str]], opener: str, closer: str) -> str:
    return ''.join(
        f'{opener}{t}{closer}' if changed else t for changed, t in _coalesce(runs)
    )


def word_diff(old: str, new: str) -> tuple[tuple[str, str], tuple[str, str]]:
    """Returns ((old_plain, new_plain), (old_colour, new_colour)).

    Plain uses git's word-diff markers, so it reads the same in any editor.
    """
    old_runs, new_runs = _spans(old, new)
    plain = (
        _render(old_runs, '[-', '-]'),
        _render(new_runs, '{+', '+}'),
    )
    colour = (
        _render(old_runs, REMOVED_BG, BG_OFF),
        _render(new_runs, ADDED_BG, BG_OFF),
    )
    return plain, colour


def colour_supported(stream=None) -> bool:
    """Raw escapes in a redirected stream are noise in whatever reads it."""
    stream = stream or sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:
        return False
