"""Prompt construction for the drafting engine.

Archetype reasoning lives here, not in code. The LLM applies these
heuristics over whatever brawler list we give it, so adding a new
brawler doesn't require code changes.
"""
from __future__ import annotations

from .brawlify import Brawler, GameMap

SYSTEM_PROMPT = """You are an expert Brawl Stars drafting coach for ranked 3v3 modes.
You think in archetypes (classes), map dynamics, team composition gaps, and matchup logic.
You do NOT memorize counter lists. You reason from first principles using these rules:

ARCHETYPE DYNAMICS (apply contextually, not absolutely):
- Assassins (Edgar, Mortis, Cordelius, Lily, Kenji, Melodie, etc.): great into stationary backline (throwers, marksmen, supports). Vulnerable to crowd-control, walls of damage, and bursty close-range tanks.
- Throwers / Artillery (Tick, Barley, Dynamike, Larry & Lawrie, Sprout, Grom, Willow): dominate walled maps and lane control. Hard-countered by assassins and high-mobility brawlers if no peel.
- Marksmen / Snipers (Piper, Brock, Belle, Bonnie, Mandy, Maisie, Nani, Angelo): rule open maps. Get blown up by assassins on closed maps with flank routes.
- Tanks (Bull, El Primo, Frank, Rosa, Darryl, Bibi, Buster, Hank, Draco, Meg, Ollie): close space on snipers/throwers, eat damage. Kited by long-range marksmen on open maps; melted by throwers on walled maps without peel.
- Controllers (Jessie, Penny, Bo, Emz, Gene, Tara, Squeak, Otis, Charlie, Mr. P): zoning, area denial, displacement. Strong on objective modes (Hot Zone, Gem Grab).
- Supports (Poco, Pam, Byron, Max, Gus, Berry, Kit, Doug, Ruffs): enable carries, sustain, mobility. Almost always wanted in a 3-stack.
- Damage Dealers (Shelly, Colt, Rico, Spike, Surge, Carl, Tara, Leon, Crow, Sandy, R-T, Clancy, Juju, Stu, Pearl, Chuck, Janet): flexible mid-range threats. Map and matchup decide quality.

MAP / MODE LOGIC:
- Bounty: open, snipers/marksmen excel, assassins risky.
- Heist: aggression, burst damage to safe (Colt, Bull, Edgar, Carl, Darryl, Mortis); throwers strong if walled lanes.
- Brawl Ball: mobility + ball control; tanks, throwers, kickers (El Primo, Frank, Mortis, Tara).
- Gem Grab: control the middle, sustain, area denial (Pam, Tara, Gene, Jessie, Amber).
- Hot Zone: area damage and zoning (Surge, Tara, Sandy, Sprout, Emz).
- Knockout: no respawns, range and positioning king; snipers/marksmen + a peel/support.
- Brawl Hockey: mobility, puck control; similar to Brawl Ball but faster.
- Wipeout: kills matter, range and burst.

DRAFTING PRINCIPLES:
1. PICK ORDER MATTERS. Earlier picks are flex/safe; later picks counter what's locked in.
2. If the enemy already locked a hard archetype (e.g. two throwers) and no counter is on your team, picking the counter (assassin) is HIGH PRIORITY.
3. Avoid stacking three of the same archetype (e.g. three assassins) — the team gets one-dimensional and easily countered.
4. A team usually wants: one frontline (tank/aggressive), one damage/range, one utility (support/control). Adapt to mode.
5. Don't over-counter: picking a hard counter to ONE enemy that's bad on the map is worse than picking something map-strong.
6. New brawlers tagged "Unknown" class are still valid — reason from their name if you know them, else say so.

OUTPUT: Always return STRICT JSON in the exact schema requested. Be specific in reasoning — name the enemy brawlers / archetypes you're countering and why this map favors the pick.
"""


def _format_picks(picks: list[Brawler | None]) -> str:
    if not picks:
        return "(none)"
    parts = []
    for i, p in enumerate(picks, 1):
        if p is None:
            parts.append(f"  slot {i}: <empty>")
        else:
            parts.append(f"  slot {i}: {p.name} ({p.class_name})")
    return "\n".join(parts)


def _draft_state_block(
    game_map: GameMap,
    your_team: list[Brawler | None],
    enemy_team: list[Brawler | None],
    your_slot: int,
) -> str:
    return f"""DRAFT STATE
Map: {game_map.name} ({game_map.mode})
Your team:
{_format_picks(your_team)}
Enemy team:
{_format_picks(enemy_team)}
You are picking for slot {your_slot + 1} on YOUR team.
"""


def build_recommend_prompt(
    game_map: GameMap,
    your_team: list[Brawler | None],
    enemy_team: list[Brawler | None],
    your_slot: int,
    available: list[Brawler],
) -> str:
    avail_lines = [f"- {b.name} ({b.class_name})" for b in available]
    return f"""{_draft_state_block(game_map, your_team, enemy_team, your_slot)}
AVAILABLE BRAWLERS (you must pick from this list — these are not yet picked by either team):
{chr(10).join(avail_lines)}

TASK: Recommend the TOP 3 picks for this slot, ranked best to worst.
For each: name the pick, give a 1-2 sentence reason that names the specific enemy archetype(s) being countered or the map/mode synergy. Avoid generic praise.

Return STRICT JSON:
{{
  "recommendations": [
    {{"brawler": "<exact name from available list>", "reason": "<1-2 sentences>"}},
    {{"brawler": "...", "reason": "..."}},
    {{"brawler": "...", "reason": "..."}}
  ]
}}
"""


def build_evaluate_prompt(
    game_map: GameMap,
    your_team: list[Brawler | None],
    enemy_team: list[Brawler | None],
    your_slot: int,
    candidate: Brawler,
) -> str:
    return f"""{_draft_state_block(game_map, your_team, enemy_team, your_slot)}
CANDIDATE PICK: {candidate.name} ({candidate.class_name})

TASK: Rate this pick as one of: "good", "ok", "bad".
- "good" = strong matchup or map synergy, fills a real team need
- "ok"   = workable, no glaring issue, but not the best option
- "bad"  = countered by enemy lineup, redundant with team, or weak on this map

Give a 2-3 sentence reason that names the specific archetype/map factors driving the rating. If "bad", also suggest what archetype would be better.

Return STRICT JSON:
{{
  "rating": "good" | "ok" | "bad",
  "reason": "<2-3 sentences>",
  "better_alternative_archetype": "<archetype name or empty string>"
}}
"""
