"""Brawlify data layer: load cached brawler/map metadata, expose lookups."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

BRAWLERS_URL = "https://api.brawlify.com/v1/brawlers"
MAPS_URL = "https://api.brawlify.com/v1/maps"
GAMEMODES_URL = "https://api.brawlify.com/v1/gamemodes"

# 3v3 competitive modes — what drafting actually applies to.
DRAFT_MODES = {
    "Gem Grab",
    "Brawl Ball",
    "Heist",
    "Bounty",
    "Hot Zone",
    "Knockout",
    "Brawl Hockey",
    "Wipeout",
}


@dataclass(frozen=True)
class Brawler:
    id: int
    name: str
    class_name: str
    rarity: str
    image_url: str

    @property
    def is_classified(self) -> bool:
        return self.class_name != "Unknown"


@dataclass(frozen=True)
class GameMap:
    id: int
    name: str
    mode: str
    image_url: str


def _load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def refresh_cache() -> None:
    """Pull fresh JSON from Brawlify and write to cache. Run periodically."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30) as client:
        for url, name in [
            (BRAWLERS_URL, "brawlers.json"),
            (MAPS_URL, "maps.json"),
            (GAMEMODES_URL, "gamemodes.json"),
        ]:
            r = client.get(url)
            r.raise_for_status()
            (CACHE_DIR / name).write_text(r.text)


def load_brawlers() -> list[Brawler]:
    raw = _load_json(CACHE_DIR / "brawlers.json")
    out: list[Brawler] = []
    for b in raw["list"]:
        if not b.get("released", True):
            continue
        out.append(
            Brawler(
                id=b["id"],
                name=b["name"],
                class_name=(b.get("class") or {}).get("name") or "Unknown",
                rarity=(b.get("rarity") or {}).get("name") or "Unknown",
                image_url=b.get("imageUrl2") or b.get("imageUrl") or "",
            )
        )
    out.sort(key=lambda b: b.name)
    return out


def load_maps(only_draft_modes: bool = True) -> list[GameMap]:
    raw = _load_json(CACHE_DIR / "maps.json")
    out: list[GameMap] = []
    for m in raw["list"]:
        if m.get("disabled"):
            continue
        gm = m.get("gameMode") or {}
        mode = gm.get("name") or ""
        if only_draft_modes and mode not in DRAFT_MODES:
            continue
        out.append(
            GameMap(
                id=m["id"],
                name=m["name"],
                mode=mode,
                image_url=m.get("imageUrl") or "",
            )
        )
    out.sort(key=lambda m: (m.mode, m.name))
    return out


def index_brawlers_by_name(brawlers: Iterable[Brawler]) -> dict[str, Brawler]:
    return {b.name.lower(): b for b in brawlers}


def index_maps_by_id(maps: Iterable[GameMap]) -> dict[int, GameMap]:
    return {m.id: m for m in maps}
