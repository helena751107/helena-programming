#!/usr/bin/env python3
"""
Deterministic enforcement — not LLM judgment.

Loads policy/tutorial_v1.json and fails closed if scenario/actions/quality
violate the contract. This is how we stop "LLM freeform" without requiring MCP.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent
POLICY_DIR = DIR / "policy"


class EnforceError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def load_policy(policy_id: str = "tutorial_v1") -> dict:
    path = POLICY_DIR / f"{policy_id}.json"
    if not path.exists():
        raise EnforceError([f"policy missing: {path}"])
    return json.loads(path.read_text(encoding="utf-8"))


def enforce_scenario(scenario: dict, policy: dict, *, scout: dict | None = None) -> list[str]:
    """Return list of errors (empty = pass)."""
    req = policy.get("require") or {}
    errs: list[str] = []

    if scenario.get("policy") != policy.get("id"):
        errs.append(f"scenario.policy must be '{policy.get('id')}' (got {scenario.get('policy')!r})")

    beats = scenario.get("beats") or []
    mn, mx = req.get("min_beats", 1), req.get("max_beats", 99)
    if not (mn <= len(beats) <= mx):
        errs.append(f"beats count {len(beats)} not in [{mn},{mx}]")

    max_chars = req.get("max_narration_chars", 200)
    forbid = req.get("forbid_phrases") or []
    optional_forbidden = req.get("optional_clicks_forbidden", False)

    for i, b in enumerate(beats):
        narr = (b.get("narration") or "").strip()
        if len(narr) > max_chars:
            errs.append(f"beat[{i}] narration too long ({len(narr)}>{max_chars})")
        for ph in forbid:
            if ph and ph in narr:
                errs.append(f"beat[{i}] forbid_phrase: {ph!r}")
        cam = b.get("camera") or {}
        if cam.get("action") == "scroll_to" and not cam.get("selector"):
            errs.append(f"beat[{i}] scroll_to missing selector")
        if cam.get("action") == "goto_top" and i != 0 and req.get("camera_must_have_selector_except_goto_top"):
            # allow only first beat goto_top
            pass
        clicks = b.get("clicks")
        if clicks is None:
            errs.append(f"beat[{i}] clicks key required")
            continue
        if optional_forbidden:
            for c in clicks:
                if c.get("optional", True):
                    errs.append(f"beat[{i}] optional click forbidden under policy: {c.get('selector')}")

    if req.get("scout_before_write") and scout is None and not scenario.get("from_scout"):
        # allow if scenario marked from_scout or scout provided
        if not scenario.get("scout_merged") and not scenario.get("from_scout"):
            errs.append("scout_before_write: provide scout or generate from scout")

    if req.get("clicks_required_when_scout_has_interactive") and scout:
        # at least some beats must declare clicks if scout found interactives
        inter = scout.get("interactive_count") or 0
        total_clicks = sum(len(b.get("clicks") or []) for b in beats)
        if inter >= 4 and total_clicks < 3:
            errs.append(f"scout has {inter} interactives but scenario only {total_clicks} clicks")

    return errs


def enforce_actions(actions_log: dict, policy: dict) -> list[str]:
    req = policy.get("require") or {}
    errs: list[str] = []
    if req.get("actions_log_required") and not actions_log:
        return ["actions_log missing"]
    ok_clicks = actions_log.get("successful_clicks") or 0
    need = req.get("min_successful_clicks", 0)
    if ok_clicks < need:
        errs.append(f"successful_clicks {ok_clicks} < required {need}")
    if req.get("show_cursor_highlight") and not actions_log.get("cursor_highlight"):
        errs.append("cursor_highlight not enabled in shoot")
    if req.get("show_caption_bar") and not actions_log.get("caption_bar"):
        errs.append("caption_bar not enabled in shoot")
    if req.get("show_spotlight") and not actions_log.get("spotlight"):
        errs.append("spotlight/focus ring not used in shoot")
    if req.get("min_overlay_version") and (
        (actions_log.get("overlay_version") or 0) < req["min_overlay_version"]
    ):
        errs.append(
            f"overlay_version {actions_log.get('overlay_version')} < {req['min_overlay_version']}"
        )
    if req.get("page_ready_contract") and not actions_log.get("page_ready"):
        errs.append("page_ready contract not logged")
    fails = actions_log.get("failed_clicks") or []
    # under tutorial, failed required clicks are errors
    for f in fails:
        if not f.get("optional", False):
            errs.append(f"required click failed: {f.get('selector')}")
    return errs


def enforce_quality(quality: dict, policy: dict) -> list[str]:
    req = policy.get("require") or {}
    errs: list[str] = []
    if req.get("quality_gate_must_pass") and not quality.get("pass"):
        errs.append("quality_gate did not pass")
        for c in quality.get("checks") or []:
            if not c.get("pass"):
                errs.append(f"quality:{c.get('id')}: {c.get('detail')}")
    return errs


def enforce_all(
    *,
    scenario: dict,
    policy: dict,
    scout: dict | None,
    actions_log: dict | None,
    quality: dict | None,
    stage: str = "pre_ship",
) -> None:
    """stage: pre_shoot | post_shoot | pre_ship"""
    errs: list[str] = []
    errs += enforce_scenario(scenario, policy, scout=scout)
    if stage in ("post_shoot", "pre_ship"):
        errs += enforce_actions(actions_log or {}, policy)
    if stage == "pre_ship":
        errs += enforce_quality(quality or {}, policy)
        ship = policy.get("ship") or {}
        if ship.get("block_without_scout_json") and scout is None:
            errs.append("ship requires scout.json")
    if errs:
        raise EnforceError(errs)


def stamp_scenario(scenario: dict, policy_id: str = "tutorial_v1") -> dict:
    scenario = dict(scenario)
    scenario["policy"] = policy_id
    # force optional=false on all clicks
    for b in scenario.get("beats") or []:
        clicks = []
        for c in b.get("clicks") or []:
            clicks.append({**c, "optional": False})
        b["clicks"] = clicks
        # caption default
        if not b.get("caption"):
            h = (b.get("scout_ref") or {}).get("heading") or b.get("id", "")
            b["caption"] = re.sub(r"\s+", " ", str(h))[:48]
        # hold clamp
        ha = b.get("hold_after_ms", 400)
        b["hold_after_ms"] = max(200, min(1200, int(ha)))
    return scenario
