#!/usr/bin/env python3
"""
Director Plan loader — 연출 설정이 scenario/shoot의 상위 시계다.

order of authority:
  directing/product_tour_v1.json  →  how to stage
  policy/tutorial_v1.json          →  what must not fail ship
  scenarios/*.json                 →  what to say / where to point
  run_director.shoot               →  executes phases from directing

Usage:
  from directing import load_directing, phase_budget_ms, stamp_scenario_directing
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent
DIRECTING_DIR = DIR / "directing"
DEFAULT_ID = "product_tour_v1"


class DirectingError(Exception):
    pass


def load_directing(directing_id: str = DEFAULT_ID) -> dict:
    path = DIRECTING_DIR / f"{directing_id}.json"
    if not path.exists():
        raise DirectingError(f"directing plan missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("id") != directing_id:
        raise DirectingError(f"id mismatch in {path}")
    _validate(data)
    return data


def _validate(d: dict) -> None:
    need = ("id", "beat_phases", "light", "cursor", "chrome", "sync", "format")
    for k in need:
        if k not in d:
            raise DirectingError(f"directing missing key: {k}")
    phases = (d.get("beat_phases") or {}).get("phases") or []
    if len(phases) < 4:
        raise DirectingError("beat_phases.phases need ≥4 phases")
    total = sum(float(p.get("frac") or 0) for p in phases)
    if abs(total - 1.0) > 0.08:
        raise DirectingError(f"phase fracs must sum ~1.0 (got {total:.3f})")


def stamp_scenario_directing(scenario: dict, directing: dict) -> dict:
    """Attach directing id + resolved timing defaults onto scenario."""
    scenario = dict(scenario)
    scenario["directing"] = directing["id"]
    scenario["directing_version"] = directing.get("version", 1)
    # format override from directing if scenario silent
    fmt = directing.get("format") or {}
    if not scenario.get("viewport") and fmt.get("viewport"):
        scenario["viewport"] = fmt["viewport"]
    voice = directing.get("voice") or {}
    if not scenario.get("voice") and voice.get("voice_id"):
        scenario["voice"] = voice["voice_id"]
    return scenario


def phase_budget_ms(directing: dict, beat_total_sec: float) -> list[dict[str, Any]]:
    """
    Split one beat's wall-clock into phase budgets (ms).
    hold absorbs remainder so sum == beat_total_sec.
    """
    phases = list((directing.get("beat_phases") or {}).get("phases") or [])
    total_ms = max(800, int(beat_total_sec * 1000))
    out = []
    used = 0
    for i, p in enumerate(phases):
        if i == len(phases) - 1:
            ms = max(80, total_ms - used)
        else:
            ms = max(80, int(total_ms * float(p.get("frac") or 0)))
            used += ms
        out.append({
            "id": p["id"],
            "ms": ms,
            "do": list(p.get("do") or []),
        })
    return out


def primary_target_hint(beat: dict) -> dict:
    """
    Resolve who owns the light for this beat.
    Priority: first click selector → camera heading → cover CTA (never metrics).
    """
    clicks = beat.get("clicks") or []
    cam = beat.get("camera") or {}
    if clicks:
        c0 = clicks[0]
        return {
            "kind": "click",
            "selector": c0.get("selector"),
            "role": c0.get("role") or (c0.get("locator") or {}).get("role"),
            "name": c0.get("name") or (c0.get("locator") or {}).get("name"),
            "label": (c0.get("why") or "Click")[:22],
        }
    if cam.get("selector"):
        # Prefer accordion head / heading inside section, not whole #section
        sel = cam["selector"]
        head = f"{sel}-head, {sel} .acc-head, {sel} h2, {sel} h1, {sel}"
        return {
            "kind": "section",
            "selector": head,
            "label": (beat.get("caption") or "Section")[:22],
        }
    # Cover: CTA first — never stat grid (cursor park anti-pattern)
    return {
        "kind": "hero",
        "selector": "#cover a.btn.btn-solid, a.btn.btn-solid, #cover h1, h1",
        "label": "CTA",
    }


def chrome_for_beat(directing: dict, i: int, n: int, beat: dict) -> dict:
    ch = directing.get("chrome") or {}
    chip_t = (ch.get("chip") or {}).get("template") or "{i}/{n} · PRODUCT TOUR"
    kick_t = (ch.get("caption") or {}).get("kicker_template") or "STEP {i}/{n}"
    caption = (
        beat.get("caption")
        or (beat.get("scout_ref") or {}).get("heading")
        or beat.get("id")
        or ""
    )
    max_c = int((ch.get("caption") or {}).get("max_chars") or 48)
    caption = str(caption).strip()[:max_c]
    return {
        "chip": chip_t.format(i=i + 1, n=n),
        "kicker": kick_t.format(i=i + 1, n=n),
        "caption": caption,
        "progress": (i + 1) / max(1, n),
    }


def light_config(directing: dict) -> dict:
    return dict(directing.get("light") or {})


def cursor_config(directing: dict) -> dict:
    return dict(directing.get("cursor") or {})


def pre_tour(directing: dict) -> dict:
    return dict(directing.get("pre_tour") or {})


def as_shoot_contract(directing: dict) -> dict:
    """Compact contract injected into actions_log for enforce/audit."""
    return {
        "directing_id": directing.get("id"),
        "version": directing.get("version"),
        "phases": [p["id"] for p in (directing.get("beat_phases") or {}).get("phases") or []],
        "dim_opacity": (directing.get("light") or {}).get("dim_opacity"),
        "cursor_move_ms": (directing.get("cursor") or {}).get("move_ms"),
        "nav_links": (directing.get("click_policy") or {}).get("nav_links"),
        "collapse_all": (directing.get("pre_tour") or {}).get("collapse_all"),
        "sync_clock": (directing.get("sync") or {}).get("clock"),
    }


if __name__ == "__main__":
    d = load_directing()
    print(json.dumps({
        "id": d["id"],
        "phases": [p["id"] for p in d["beat_phases"]["phases"]],
        "budget_example_10s": phase_budget_ms(d, 10.0),
    }, ensure_ascii=False, indent=2))
