from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from decimal import Decimal

from backend.app.domain.models import Skill, TAXONOMY_VERSION

STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "with",
        "learn",
        "learning",
        "research",
    }
)
TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in TOKEN_PATTERN.sub(" ", normalized).split() if part)


class Taxonomy:
    def __init__(self, skills: Iterable[Skill], version: str = TAXONOMY_VERSION) -> None:
        self.version = version
        self.skills = {skill.id: skill for skill in skills}
        self.alias_to_id: dict[str, str] = {}
        for skill in sorted(self.skills.values(), key=lambda item: item.id):
            for alias in (skill.id, skill.label, *skill.aliases):
                normalized = normalize_text(alias)
                if normalized:
                    self.alias_to_id[normalized] = skill.id

    def token_weights(self, values: Iterable[str], *, explicit_tags: bool) -> dict[str, Decimal]:
        weights: dict[str, Decimal] = {}
        for value in values:
            normalized = normalize_text(value)
            if not normalized:
                continue
            direct = self.alias_to_id.get(normalized)
            if direct is not None:
                weights[direct] = max(weights.get(direct, Decimal(0)), Decimal(2 if explicit_tags else 1))
                continue
            for token in normalized.split():
                if token in STOP_WORDS:
                    continue
                canonical = self.alias_to_id.get(token, token)
                weights[canonical] = max(weights.get(canonical, Decimal(0)), Decimal(1))
        return dict(sorted(weights.items()))


def weighted_jaccard(
    left: dict[str, Decimal], right: dict[str, Decimal]
) -> tuple[Decimal | None, list[str]]:
    keys = sorted(set(left) | set(right))
    denominator = sum((max(left.get(key, Decimal(0)), right.get(key, Decimal(0))) for key in keys), Decimal(0))
    if denominator == 0:
        return None, []
    numerator = sum((min(left.get(key, Decimal(0)), right.get(key, Decimal(0))) for key in keys), Decimal(0))
    matched = [key for key in keys if left.get(key, 0) > 0 and right.get(key, 0) > 0]
    return numerator / denominator, matched
