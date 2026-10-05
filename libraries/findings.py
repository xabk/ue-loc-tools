"""Things a task noticed that someone should look at.

A task's output is read once, while it scrolls past. What matters tends to
be a handful of facts scattered through thousands of lines, each repeated as
many times as the engine happened to hit it. Collecting them as they go by
and listing them at the end turns that into something a person can act on.

Findings are returned rather than only logged, so a later caller can gather
them from several tasks and report once for a whole run.
"""

from dataclasses import dataclass, field

from loguru import logger


@dataclass
class Finding:
    """One thing worth looking at, however many times it was said."""

    category: str
    key: str
    # Where it was seen. A set: the same problem is reported many times,
    # with somewhere to point only some of them.
    contexts: set[str] = field(default_factory=set)
    occurrences: int = 1
    # Decides the level the category is reported at.
    level: str = 'warning'

    def merge(self, other: 'Finding'):
        self.occurrences += other.occurrences
        self.contexts |= other.contexts


@dataclass
class Findings:
    """Findings for one task, or for a whole run once they are merged."""

    source: str = ''
    by_key: dict[tuple[str, str], Finding] = field(default_factory=dict)

    def add(self, category: str, key: str, context: str = '', level='warning'):
        found = Finding(category, key, {context} if context else set(), level=level)
        existing = self.by_key.get((category, key))
        if existing:
            existing.merge(found)
        else:
            self.by_key[(category, key)] = found

    def merge(self, other: 'Findings'):
        for finding in other.by_key.values():
            existing = self.by_key.get((finding.category, finding.key))
            if existing:
                existing.merge(finding)
            else:
                self.by_key[(finding.category, finding.key)] = Finding(
                    finding.category,
                    finding.key,
                    set(finding.contexts),
                    finding.occurrences,
                    finding.level,
                )

    def categories(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for finding in self.by_key.values():
            out.setdefault(finding.category, []).append(finding)
        for group in out.values():
            group.sort(key=lambda f: f.key)
        # Errors first: they are the reason a run failed.
        return dict(sorted(out.items(), key=lambda kv: kv[1][0].level != 'error'))

    def __len__(self) -> int:
        return len(self.by_key)

    def __bool__(self) -> bool:
        return bool(self.by_key)

    def report(self):
        """One block per category, errors first. Nothing is truncated:
        every finding and every place it was found is something to act on."""
        for category, group in self.categories().items():
            say = logger.error if group[0].level == 'error' else logger.warning
            say(f'{len(group)} {category}:')
            for finding in group:
                # Places where we have them, mentions where we do not.
                if finding.contexts:
                    times = f'  ({len(finding.contexts)} place(s))'
                elif finding.occurrences > 1:
                    times = f'  ({finding.occurrences} mentions)'
                else:
                    times = ''
                say(f'  {finding.key}{times}')
                for context in sorted(finding.contexts):
                    say(f'      {context}')
