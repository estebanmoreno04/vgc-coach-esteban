"""Species identities shared by every source.

Sources name Pokémon differently: VGC History uses slugs that already encode
the Mega form ("raichu-mega-x"), while Limitless uses the base form plus the
held Mega Stone ("raichu" holding "Raichunite X"). Everything is normalized
to a ``(species_id, mega_id)`` pair of Showdown-style slugs, with Showdown
display names ("Raichu", "Raichu-Mega-X").

The registry comes from VGC History's ``MONS`` table and is persisted to
data/current/pokedex.json so it is available when that source is down.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Base species whose own name contains a hyphen (Showdown display names).
_HYPHENATED_BASES = {
    "ho-oh": "Ho-Oh",
    "porygon-z": "Porygon-Z",
    "jangmo-o": "Jangmo-o",
    "hakamo-o": "Hakamo-o",
    "kommo-o": "Kommo-o",
    "mr-mime": "Mr. Mime",
    "mime-jr": "Mime Jr.",
    "mr-rime": "Mr. Rime",
    "type-null": "Type: Null",
    "wo-chien": "Wo-Chien",
    "chien-pao": "Chien-Pao",
    "ting-lu": "Ting-Lu",
    "chi-yu": "Chi-Yu",
    "nidoran-f": "Nidoran-F",
    "nidoran-m": "Nidoran-M",
}
_STONE_SUFFIX_RE = re.compile(r"ite(?:\s+([xyz]))?$", re.IGNORECASE)
_NOT_STONES = {"eviolite"}


def slug(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    ascii_text = folded.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = ascii_text.replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


@dataclass
class Pokedex:
    names: dict[str, str] = field(default_factory=dict)  # slug -> display name
    mega_base: dict[str, str] = field(default_factory=dict)  # mega slug -> species slug
    stones: dict[str, str] = field(default_factory=dict)  # stone slug -> mega slug

    # -- construction ------------------------------------------------------

    @classmethod
    def from_vgchistory(cls, mons: dict[str, Any]) -> "Pokedex":
        dex = cls()
        for key, entry in mons.items():
            if not isinstance(entry, dict):
                continue
            display = str(entry.get("ps") or "").strip()
            if display:
                dex.names[key] = display
            if "-mega" in key:
                dex.mega_base[key] = str(entry.get("tfrom") or entry.get("base") or key.split("-mega")[0])
        return dex

    @classmethod
    def load(cls, path: Path) -> "Pokedex":
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            names=dict(payload.get("names", {})),
            mega_base=dict(payload.get("mega_base", {})),
            stones=dict(payload.get("stones", {})),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "names": dict(sorted(self.names.items())),
            "mega_base": dict(sorted(self.mega_base.items())),
            "stones": dict(sorted(self.stones.items())),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")

    def merge(self, other: "Pokedex") -> None:
        self.names.update(other.names)
        self.mega_base.update(other.mega_base)
        self.stones.update(other.stones)

    def learn_stone(self, item: str | None, mega_id: str | None) -> None:
        """Record which stone produced a Mega form (from open team sheets)."""
        if item and mega_id and _looks_like_stone(item):
            self.stones[slug(item)] = mega_id

    # -- normalization -------------------------------------------------------

    def identity(self, raw_id: str, item: str | None = None) -> tuple[str, str | None]:
        """Return ``(species_id, mega_id)`` for a source id and held item."""
        key = slug(raw_id)
        if "-mega" in key:
            return self.mega_base.get(key, key.split("-mega")[0]), key
        return key, self.mega_for(key, item)

    def mega_for(self, species_id: str, item: str | None) -> str | None:
        if not item or not _looks_like_stone(item):
            return None
        stone = slug(item)
        known = self.stones.get(stone)
        if known and self.mega_base.get(known, known.split("-mega")[0]) == species_id:
            return known
        candidates = sorted(mega for mega, base in self.mega_base.items() if base == species_id)
        if not candidates:
            # No registry: accept a stone whose name starts like the species.
            base = species_id.split("-")[0]
            if stone[:4] == base[:4]:
                letter = _STONE_SUFFIX_RE.search(item.strip())
                suffix = f"-{letter.group(1).lower()}" if letter and letter.group(1) else ""
                return f"{base}-mega{suffix}"
            return None
        letter = _STONE_SUFFIX_RE.search(item.strip())
        wanted = letter.group(1).lower() if letter and letter.group(1) else None
        for mega in candidates:
            mega_letter = mega.rsplit("-mega", 1)[1].lstrip("-") or None
            if mega_letter == wanted:
                return mega
        return candidates[0] if len(candidates) == 1 else None

    def display(self, slug_id: str | None) -> str | None:
        if slug_id is None:
            return None
        if slug_id in self.names:
            return self.names[slug_id]
        for base, name in _HYPHENATED_BASES.items():
            if slug_id == base or slug_id.startswith(base + "-"):
                rest = slug_id[len(base):]
                return name + "-".join(part.capitalize() for part in rest.split("-"))
        return "-".join(part.capitalize() for part in slug_id.split("-"))


def _looks_like_stone(item: str) -> bool:
    text = item.strip()
    return bool(_STONE_SUFFIX_RE.search(text)) and slug(text) not in _NOT_STONES


def clean_name(value: str | None) -> str | None:
    """Tidy an item, ability, nature or move name for display."""
    if value is None:
        return None
    text = unicodedata.normalize("NFC", str(value)).replace("’", "'").replace("​", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def name_key(value: str | None) -> str | None:
    """Grouping key that merges spelling variants ("Trick-or-Treat" / "Trick or Treat")."""
    if not value:
        return None
    return re.sub(r"[^a-z0-9]", "", slug(value)) or None
