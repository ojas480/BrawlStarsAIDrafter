"""FastAPI backend for the Brawl Stars drafting AI."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from .brawlify import (
    Brawler,
    GameMap,
    index_brawlers_by_name,
    index_maps_by_id,
    load_brawlers,
    load_maps,
)
from .engine import RecommendationEngine
from .gemini_engine import GeminiEngine

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="Brawl Drafting AI")

# Loaded once at startup; tiny so just keep in memory.
_BRAWLERS: List[Brawler] = []
_MAPS: List[GameMap] = []
_BRAWLER_BY_NAME: dict = {}
_MAP_BY_ID: dict = {}
_ENGINE: Optional[RecommendationEngine] = None


@app.on_event("startup")
def _startup() -> None:
    global _BRAWLERS, _MAPS, _BRAWLER_BY_NAME, _MAP_BY_ID, _ENGINE
    _BRAWLERS = load_brawlers()
    _MAPS = load_maps(only_draft_modes=True)
    _BRAWLER_BY_NAME = index_brawlers_by_name(_BRAWLERS)
    _MAP_BY_ID = index_maps_by_id(_MAPS)
    _ENGINE = GeminiEngine()


# ---------------------------- API models ----------------------------

class BrawlerOut(BaseModel):
    id: int
    name: str
    className: str
    rarity: str
    imageUrl: str


class MapOut(BaseModel):
    id: int
    name: str
    mode: str
    imageUrl: str


class DraftState(BaseModel):
    map_id: int
    your_team: List[Optional[str]] = Field(min_length=3, max_length=3)
    enemy_team: List[Optional[str]] = Field(min_length=3, max_length=3)
    your_slot: int = Field(ge=0, le=2)
    owned_brawlers: Optional[List[str]] = None  # None or [] = no filter


class EvaluateRequest(DraftState):
    candidate: str


class RecommendationOut(BaseModel):
    brawler: str
    reason: str
    imageUrl: Optional[str] = None
    className: Optional[str] = None


class RecommendResponse(BaseModel):
    recommendations: List[RecommendationOut]


class EvaluateResponse(BaseModel):
    rating: str
    reason: str
    betterAlternativeArchetype: str


# ---------------------------- Helpers ----------------------------

def _to_brawler(name: Optional[str]) -> Optional[Brawler]:
    if not name:
        return None
    b = _BRAWLER_BY_NAME.get(name.lower())
    if not b:
        raise HTTPException(404, f"Unknown brawler: {name}")
    return b


def _resolve_state(state: DraftState):
    game_map = _MAP_BY_ID.get(state.map_id)
    if not game_map:
        raise HTTPException(404, f"Unknown map id: {state.map_id}")
    your_team = [_to_brawler(n) for n in state.your_team]
    enemy_team = [_to_brawler(n) for n in state.enemy_team]
    return game_map, your_team, enemy_team


def _available_brawlers(your_team, enemy_team) -> List[Brawler]:
    taken = {b.id for b in (*your_team, *enemy_team) if b is not None}
    return [b for b in _BRAWLERS if b.id not in taken]


# ---------------------------- Endpoints ----------------------------

@app.get("/api/brawlers", response_model=List[BrawlerOut])
def get_brawlers():
    return [
        BrawlerOut(
            id=b.id,
            name=b.name,
            className=b.class_name,
            rarity=b.rarity,
            imageUrl=b.image_url,
        )
        for b in _BRAWLERS
    ]


@app.get("/api/maps", response_model=List[MapOut])
def get_maps():
    return [
        MapOut(id=m.id, name=m.name, mode=m.mode, imageUrl=m.image_url)
        for m in _MAPS
    ]


def _filter_owned(available: List[Brawler], owned_names: Optional[List[str]]) -> List[Brawler]:
    if not owned_names:
        return available
    owned_lower = {n.lower() for n in owned_names if n}
    filtered = [b for b in available if b.name.lower() in owned_lower]
    return filtered


def _safe_engine_call(fn, *args):
    """Wrap engine calls so timeouts/SDK errors return clean HTTP errors instead of 500s."""
    try:
        return fn(*args)
    except Exception as e:
        msg = str(e)
        # google-genai wraps httpx timeouts; check the message for "timeout" / "timed out"
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            raise HTTPException(504, "AI took longer than 10s — try again.")
        if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
            raise HTTPException(429, "Gemini quota hit. Try a different model in .env or wait a minute.")
        raise HTTPException(502, f"AI error: {msg[:200]}")


@app.post("/api/recommend", response_model=RecommendResponse)
def post_recommend(state: DraftState):
    game_map, your_team, enemy_team = _resolve_state(state)
    if your_team[state.your_slot] is not None:
        raise HTTPException(400, "Your slot is already filled")
    available = _available_brawlers(your_team, enemy_team)
    available = _filter_owned(available, state.owned_brawlers)
    if not available:
        raise HTTPException(400, "No brawlers available — your collection filter is too narrow.")
    result = _safe_engine_call(
        _ENGINE.recommend, game_map, your_team, enemy_team, state.your_slot, available
    )
    out = []
    for r in result.recommendations:
        b = _BRAWLER_BY_NAME.get(r.brawler.lower())
        out.append(
            RecommendationOut(
                brawler=r.brawler,
                reason=r.reason,
                imageUrl=b.image_url if b else None,
                className=b.class_name if b else None,
            )
        )
    return RecommendResponse(recommendations=out)


@app.post("/api/evaluate", response_model=EvaluateResponse)
def post_evaluate(req: EvaluateRequest):
    game_map, your_team, enemy_team = _resolve_state(req)
    candidate = _to_brawler(req.candidate)
    if candidate is None:
        raise HTTPException(400, "candidate is required")
    result = _safe_engine_call(
        _ENGINE.evaluate, game_map, your_team, enemy_team, req.your_slot, candidate
    )
    return EvaluateResponse(
        rating=result.rating,
        reason=result.reason,
        betterAlternativeArchetype=result.better_alternative_archetype,
    )


# ---------------------------- Static frontend ----------------------------

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
