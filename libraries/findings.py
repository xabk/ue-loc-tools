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
    detail: str = ''
    occurrences: int = 1

    def merge(self, other: 'Finding'):
        self.occurrences += other.occurrences
        # The first run to know where it happened keeps the answer: the same
        # problem is usually reported with context once and bare after that.
        if other.detail and not self.detail:
            self.detail = other.detail


@dataclass
class Findings:
    """Findings for one task, or for a whole run once they are merged."""

    source: str = ''
    by_key: dict[tuple[str, str], Finding] = field(default_factory=dict)

    def add(self, category: str, key: str, detail: str = ''):
        existing = self.by_key.get((category, key))
        if existing:
            existing.merge(Finding(category, key, detail))
        else:
            self.by_key[(category, key)] = Finding(category, key, detail)

    def merge(self, other: 'Findings'):
        for finding in other.by_key.values():
            self.add(finding.category, finding.key, finding.detail)

    def categories(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for finding in self.by_key.values():
            out.setdefault(finding.category, []).append(finding)
        for group in out.values():
            group.sort(key=lambda f: f.key)
        return out

    def __len__(self) -> int:
        return len(self.by_key)

    def __bool__(self) -> bool:
        return bool(self.by_key)

    def report(self, headings: dict[str, str] | None = None):
        """One block per category, every finding listed.

        Nothing is truncated. A list someone is meant to act on is no use
        with the end cut off, and there are only ever a handful of these --
        the volume was in the repetition, which is already gone.
        """
        headings = headings or {}
        for category, group in self.categories().items():
            total = sum(f.occurrences for f in group)
            heading = headings.get(category, category)
            said = '' if total == len(group) else f', said {total} time(s)'
            logger.warning(f'{len(group)} {heading}{said}:')
            for finding in group:
                detail = f'   {finding.detail}' if finding.detail else ''
                times = (
                    f'  ({finding.occurrences} references)'
                    if finding.occurrences > 1
                    else ''
                )
                logger.warning(f'  {finding.key}{detail}{times}')
