"""Pluggable recommendation engine interface.

Add new backends (Claude, local model, rules-only) by implementing
RecommendationEngine and registering in main.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from .brawlify import Brawler, GameMap

Rating = Literal["good", "ok", "bad"]


@dataclass
class Recommendation:
    brawler: str
    reason: str


@dataclass
class RecommendResult:
    recommendations: list[Recommendation]


@dataclass
class EvaluateResult:
    rating: Rating
    reason: str
    better_alternative_archetype: str = ""


class RecommendationEngine(ABC):
    @abstractmethod
    def recommend(
        self,
        game_map: GameMap,
        your_team: list[Brawler | None],
        enemy_team: list[Brawler | None],
        your_slot: int,
        available: list[Brawler],
    ) -> RecommendResult: ...

    @abstractmethod
    def evaluate(
        self,
        game_map: GameMap,
        your_team: list[Brawler | None],
        enemy_team: list[Brawler | None],
        your_slot: int,
        candidate: Brawler,
    ) -> EvaluateResult: ...
