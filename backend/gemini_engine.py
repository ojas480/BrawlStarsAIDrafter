"""Gemini implementation of RecommendationEngine (uses google-genai SDK)."""
from __future__ import annotations

import json
import os
from typing import List, Optional

from google import genai
from google.genai import types as gtypes

from .brawlify import Brawler, GameMap
from .engine import (
    EvaluateResult,
    RecommendationEngine,
    RecommendResult,
    Recommendation,
)
from .prompts import SYSTEM_PROMPT, build_evaluate_prompt, build_recommend_prompt


class GeminiEngine(RecommendationEngine):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=key)
        self.model_name = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    def _generate_json(self, prompt: str) -> dict:
        # Disable thinking on 2.5-flash — drafting is pattern matching, not deep reasoning,
        # and thinking pushes latency past our 10s budget.
        config = gtypes.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.4,
            thinking_config=gtypes.ThinkingConfig(thinking_budget=0),
            http_options=gtypes.HttpOptions(timeout=10_000),  # ms
        )
        resp = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config,
        )
        text = resp.text or ""
        return json.loads(text)

    def recommend(
        self,
        game_map: GameMap,
        your_team: List[Optional[Brawler]],
        enemy_team: List[Optional[Brawler]],
        your_slot: int,
        available: List[Brawler],
    ) -> RecommendResult:
        prompt = build_recommend_prompt(
            game_map, your_team, enemy_team, your_slot, available
        )
        data = self._generate_json(prompt)
        recs = [
            Recommendation(brawler=r["brawler"], reason=r["reason"])
            for r in data.get("recommendations", [])
        ]
        return RecommendResult(recommendations=recs)

    def evaluate(
        self,
        game_map: GameMap,
        your_team: List[Optional[Brawler]],
        enemy_team: List[Optional[Brawler]],
        your_slot: int,
        candidate: Brawler,
    ) -> EvaluateResult:
        prompt = build_evaluate_prompt(
            game_map, your_team, enemy_team, your_slot, candidate
        )
        data = self._generate_json(prompt)
        rating = data.get("rating", "ok")
        if rating not in ("good", "ok", "bad"):
            rating = "ok"
        return EvaluateResult(
            rating=rating,
            reason=data.get("reason", ""),
            better_alternative_archetype=data.get("better_alternative_archetype", ""),
        )
