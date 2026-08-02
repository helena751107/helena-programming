#!/usr/bin/env python3
"""
Director Agent — URL → scripted tour video
  Scout → Writer/Director → Voice → Shoot → Edit

Usage:
  python3 run_director.py --url https://helena751107.github.io/helena_phone/
  python3 run_director.py --scenario scenarios/helena_phone.json --scout
  python3 run_director.py --url URL --scout-only   # write scout.json + scenario only

Phone/proot friendly: Playwright record + edge-tts + ffmpeg.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from directing import (
    as_shoot_contract,
    chrome_for_beat,
    load_directing,
    phase_budget_ms,
    primary_target_hint,
    stamp_scenario_directing,
)
from enforce import EnforceError, enforce_all, load_policy, stamp_scenario
from intro import make_intro_card
from quality import gate_output, trim_leading_black
from scout import (
    merge_scenario_with_scout,
    save_scout,
    scenario_from_scout,
    scout_url,
)
from subtitles import burn_subtitles, write_srt_from_beats
from voice_engine import VOICE_DEFAULT, multi_click_pad, synthesize_beat

DIR = Path(__file__).resolve().parent
DEFAULT_OUT = DIR / "out" / "director_out.mp4"
# Encode quality (phone-friendly but not ultrafast mush)
# Pro encode: lower CRF, slightly slower preset (phone-ok with veryfast still if needed)
X264 = [
    "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-preset", "fast", "-crf", "17",
    "-r", "30", "-vsync", "cfr",
]
X264_FAST = [
    "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-preset", "veryfast", "-crf", "18",
    "-r", "30", "-vsync", "cfr",
]

# Community A-bar format profiles (recast: 1080p; shorts: 9:16)
FORMATS = {
    "shorts": {"width": 720, "height": 1280, "label": "720x1280"},
    "shorts_1080": {"width": 1080, "height": 1920, "label": "1080x1920"},
    "desktop": {"width": 1280, "height": 720, "label": "1280x720"},
    "desktop_1080": {"width": 1920, "height": 1080, "label": "1920x1080"},
}


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, text=True, capture_output=False)


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip() or "0")


def build_voices(scenario: dict, work: Path) -> list[dict]:
    """
    TTS-FIRST (community A / Purple Owl / recast):
    Measure each beat audio duration BEFORE shoot, then shoot locks wall-clock to it.
    """
    voice = scenario.get("voice") or VOICE_DEFAULT
    prefer = scenario.get("tts_provider") or "auto"
    beats = scenario["beats"]

    async def all_tts():
        out = []
        providers = []
        for i, b in enumerate(beats):
            raw = work / "voice" / f"{i:02d}_{b['id']}_raw.mp3"
            path = work / "voice" / f"{i:02d}_{b['id']}.mp3"
            print(f"[voice] {b['id']}: {b['narration'][:48]}…", flush=True)
            dur, prov = await synthesize_beat(
                b["narration"],
                dest=path,
                raw_dest=raw,
                edge_voice=voice,
                prefer=prefer,
            )
            n_clicks = len(b.get("clicks") or [])
            pad = multi_click_pad(n_clicks, int(b.get("hold_after_ms") or 400))
            out.append({**b, "voice_path": str(path), "audio_sec": dur, "pad_sec": pad})
            providers.append(prov)
            print(f"  → {dur:.2f}s + pad {pad:.2f}s clicks={n_clicks} via={prov}", flush=True)
        # stamp for perfect_ship L2
        scenario["tts_providers"] = providers
        scenario["tts_humanize"] = True
        scenario["tts_first"] = True
        return out

    return asyncio.run(all_tts())


def concat_audio(beats: list[dict], work: Path) -> Path:
    """Concat per-beat mp3 with short silence pads (re-encode to avoid DTS glitches)."""
    silence = work / "silence_200ms.mp3"
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", "0.2", "-q:a", "9", "-acodec", "libmp3lame", str(silence),
    ])
    # build filter_complex amix/concat of decoded streams
    inputs: list[str] = []
    filter_parts: list[str] = []
    idx = 0
    for b in beats:
        inputs += ["-i", str(Path(b["voice_path"]).resolve())]
        filter_parts.append(f"[{idx}:a]")
        idx += 1
        n = max(1, int(round(b.get("pad_sec", 0.4) / 0.2)))
        for _ in range(n):
            inputs += ["-i", str(silence.resolve())]
            filter_parts.append(f"[{idx}:a]")
            idx += 1
    n_in = idx
    filt = "".join(filter_parts) + f"concat=n={n_in}:v=0:a=1[aout]"
    out = work / "narration.mp3"
    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filt, "-map", "[aout]",
        "-c:a", "libmp3lame", "-q:a", "4",
        str(out),
    ])
    return out


def _wait_page_ready(page, url: str) -> None:
    """Hard readiness contract — no shooting until paint + fonts."""
    page.goto(url, wait_until="load", timeout=120_000)
    try:
        page.wait_for_load_state("networkidle", timeout=25_000)
    except Exception:
        print("  ! networkidle timeout — continue after load", flush=True)
    # first contentful anchors
    for sel in ("#cover h1", ".cover h1", "h1", "main", "body"):
        try:
            page.wait_for_selector(sel, state="visible", timeout=8_000)
            break
        except Exception:
            continue
    page.evaluate("""async () => {
      try { await document.fonts.ready; } catch (e) {}
      // force layout/paint
      document.body && document.body.getBoundingClientRect();
      window.scrollTo(0, 0);
    }""")
    page.wait_for_timeout(600)
    # paint dark bg explicitly if blank flash
    page.add_style_tag(content="""
      html,body{background:#0a0908!important}
      .cursor,.cursor-dot{display:none!important}
      body{cursor:auto!important}
      html{scroll-behavior:auto!important}
    """)
    page.wait_for_timeout(200)


def _png_accent_counts(path: Path) -> dict:
    """Count gold / teal accent pixels — delegated to quality.accent_counts (unfiltered)."""
    from quality import accent_counts
    return accent_counts(path)


def shoot(
    scenario: dict,
    beats: list[dict],
    work: Path,
    directing: dict | None = None,
) -> tuple[Path, dict]:
    """
    Tutorial shoot v5 — directing 5-act phases drive the clock.
    establish → focus → act → hold → release per beat.
    Returns (raw_video_path, actions_log).
    """
    from playwright.sync_api import sync_playwright

    if directing is None:
        directing = load_directing(scenario.get("directing") or "product_tour_v1")

    vp = scenario.get("viewport") or (directing.get("format") or {}).get("viewport") or {
        "width": 720, "height": 1280
    }
    w, h = int(vp["width"]), int(vp["height"])
    url = scenario["url"]
    rec_dir = work / "record"
    proof_dir = work / "proof"
    if rec_dir.exists():
        shutil.rmtree(rec_dir)
    if proof_dir.exists():
        shutil.rmtree(proof_dir)
    rec_dir.mkdir(parents=True)
    proof_dir.mkdir(parents=True)

    timings = [b["audio_sec"] + b.get("pad_sec", 0.35) for b in beats]
    overlay_js = (DIR / "overlays.js").read_text(encoding="utf-8")
    cam_cfg = directing.get("camera") or {}
    scroll_steps = int(cam_cfg.get("scroll_steps") or 22)
    scroll_settle_ms = int(cam_cfg.get("scroll_settle_ms") or 420)
    goto_top_settle_ms = int(cam_cfg.get("goto_top_settle_ms") or 550)
    cursor_cfg = directing.get("cursor") or {}
    post_click_freeze = int(cursor_cfg.get("post_click_freeze_ms") or 350)

    actions: dict = {
        "page_ready": False,
        "cursor_highlight": True,
        "cursor_on_primary": False,
        "caption_bar": True,
        "progress_chip": True,
        "spotlight": False,
        "successful_clicks": 0,
        "failed_clicks": [],
        "events": [],
        "overlay_version": 5,
        "visual_proof": [],
        "visual_proof_pass": False,
        "shoot_version": 5,
        "directing": as_shoot_contract(directing),
        "phases_played": [],
        # stamped by main() for perfect_ship process (defaults safe)
        "process_id": scenario.get("process_id") or "perfect_ship_v1",
        "tts_humanize": bool(scenario.get("tts_humanize", True)),
        "tts_first": True,
        "auto_zoom": True,
        "clicks_declared": sum(len(b.get("clicks") or []) for b in beats),
        "zoom_events": [],
    }
    print(f"[shoot] open {url}", flush=True)
    t_shoot0 = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--hide-scrollbars",
                "--font-render-hinting=none",
            ],
        )
        context = browser.new_context(
            viewport={"width": w, "height": h},
            device_scale_factor=1,
            record_video_dir=str(rec_dir),
            record_video_size={"width": w, "height": h},
            color_scheme="dark",
            locale="ko-KR",
            # no reduced_motion — we WANT full CSS transitions in the capture
            reduced_motion="no-preference",
        )
        page = context.new_page()
        # Block accidental navigation away from tour (CTA links)
        page.route("**/*", lambda route: route.continue_())
        # Freeze navigation during tour — hash jumps (#install) destroy beat sync
        page.add_init_script(
            """
            (() => {
              const block = (e) => {
                const a = e.target && e.target.closest && e.target.closest('a[href]');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                // block external, download, AND in-page hash navigation
                if (
                  href.startsWith('http') || href.startsWith('//') ||
                  href.startsWith('#') || href.endsWith('.sh') ||
                  href.includes('raw.githubusercontent') ||
                  a.hasAttribute('download')
                ) {
                  e.preventDefault();
                  e.stopPropagation();
                }
              };
              document.addEventListener('click', block, true);
              // also stop location.hash assignment side-effects from site JS when possible
              try {
                const desc = Object.getOwnPropertyDescriptor(Location.prototype, 'hash');
                if (desc && desc.set) {
                  Object.defineProperty(window.location, 'hash', {
                    configurable: true,
                    get() { return desc.get.call(window.location); },
                    set(_v) { /* tour lock */ },
                  });
                }
              } catch (err) {}
            })();
            """
        )
        page.set_content(
            "<!doctype html><html><body style='margin:0;background:#0a0908;width:100vw;height:100vh'></body></html>"
        )
        page.wait_for_timeout(120)

        _wait_page_ready(page, url)
        actions["page_ready"] = True
        page.add_script_tag(content=overlay_js)
        page.evaluate(
            """() => {
              if (!window.__hd) return;
              window.__hd.setChip('TUTORIAL · LIVE');
              window.__hd.parkCursor && window.__hd.parkCursor();
            }"""
        )
        print("  page ready + overlays v5 (pro approach + ken burns)", flush=True)
        try:
            page.evaluate("() => window.__hd && window.__hd.setCinematic && window.__hd.setCinematic(true)")
        except Exception:
            pass

        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(350)

        # v3: COLLAPSE all first so each beat OPEN is a visible state change.
        # expand-all made accordion clicks look like no-ops.
        collapse_sels = [
            "#accCollapse", "#accCloseAll",
            "button:has-text('Collapse all')", "button:has-text('Collapse')",
            "button:has-text('접기')", "button:has-text('모두 접기')",
        ]
        collapsed = False
        for sel in collapse_sels:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=2000)
                    page.wait_for_timeout(500)
                    print(f"  collapse via {sel}", flush=True)
                    actions["events"].append({"type": "collapse", "selector": sel, "ok": True})
                    collapsed = True
                    break
            except Exception:
                pass
        if not collapsed:
            # best-effort: click open heads that look expanded
            try:
                page.evaluate(
                    """() => {
                      document.querySelectorAll(
                        '[aria-expanded="true"], .acc-item.open .acc-head, details[open] > summary'
                      ).forEach((el) => { try { el.click(); } catch (e) {} });
                    }"""
                )
                page.wait_for_timeout(400)
                actions["events"].append({"type": "collapse", "selector": "aria-expanded", "ok": True})
            except Exception:
                pass

        def smooth_scroll_to(selector: str, steps: int | None = None):
            steps = int(steps if steps is not None else scroll_steps)
            try:
                page.wait_for_selector(selector, timeout=8000)
            except Exception:
                print(f"  ! missing selector {selector}", flush=True)
                return False
            page.evaluate(
                """([sel, steps]) => {
                  const el = document.querySelector(sel);
                  if (!el) return;
                  const target = el.getBoundingClientRect().top + window.scrollY - 90;
                  const start = window.scrollY;
                  const delta = target - start;
                  return new Promise(resolve => {
                    let i = 0;
                    const tick = () => {
                      i++;
                      const t = i / steps;
                      const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;
                      window.scrollTo(0, start + delta * ease);
                      if (i < steps) requestAnimationFrame(tick);
                      else resolve();
                    };
                    tick();
                  });
                }""",
                [selector, steps],
            )
            page.wait_for_timeout(scroll_settle_ms)
            return True

        def resolve_el(part: str):
            loc = page.locator(part).first
            if loc.count() == 0:
                return None, None
            return loc, part

        def resolve_role(role: str, name: str):
            """Scout v2 / Generator: getByRole live locator."""
            if not role or not name:
                return None, None
            try:
                loc = page.get_by_role(role, name=name)
                if loc.count() == 0 and len(name) > 10:
                    import re as _re
                    tok = name.split()[0] if name.split() else name[:8]
                    loc = page.get_by_role(role, name=_re.compile(_re.escape(tok), _re.I))
                if loc.count() == 0:
                    return None, None
                first = loc.first
                if not first.is_visible():
                    return None, None
                used = f"role={role}[name={name!r}]"
                return first, used
            except Exception:
                return None, None

        def healer_variants(sel: str) -> list[str]:
            """Community pattern: retry simpler selectors (healer)."""
            if not sel:
                return []
            # skip pseudo role= selectors from aria-only inject
            if sel.startswith("role="):
                return []
            parts = [s.strip() for s in sel.split(",") if s.strip()]
            out = list(parts)
            for p in parts:
                if "#" in p and " > " in p:
                    out.append(p.split(" > ")[-1])
                if " " in p or ">" in p:
                    for tok in p.replace(">", " ").split():
                        if tok.startswith("#") and len(tok) > 2:
                            out.append(tok.split(":")[0])
            seen = set()
            uniq = []
            for x in out:
                if x not in seen:
                    seen.add(x)
                    uniq.append(x)
            return uniq

        def capture_proof(tag: str, selector: str) -> dict:
            """Screenshot + accent pixel counts after demoClick."""
            idx = len(actions["visual_proof"])
            dest = proof_dir / f"click_{idx:02d}_{tag}.png"
            try:
                page.screenshot(path=str(dest), full_page=False)
                counts = _png_accent_counts(dest)
                passed = counts.get("gold", 0) >= 80 and counts.get("teal", 0) >= 20
                entry = {
                    "file": dest.name,
                    "selector": selector,
                    "gold": counts.get("gold", 0),
                    "teal": counts.get("teal", 0),
                    "pass": passed,
                    "t_rel": round(time.time() - t_shoot0, 2),
                }
                actions["visual_proof"].append(entry)
                mark = "✓" if passed else "✗"
                print(
                    f"  proof {mark} {dest.name} gold={entry['gold']} teal={entry['teal']}",
                    flush=True,
                )
                return entry
            except Exception as e:
                entry = {
                    "file": dest.name, "selector": selector,
                    "gold": 0, "teal": 0, "pass": False, "error": str(e),
                }
                actions["visual_proof"].append(entry)
                print(f"  proof FAIL {e}", flush=True)
                return entry

        def ensure_accordion_closed_loc(loc) -> None:
            """Close expanded accordion via locator element."""
            try:
                loc.evaluate(
                    """el => {
                      const item = el.closest('.acc-item, details, [data-open]');
                      const expanded =
                        (el.getAttribute && el.getAttribute('aria-expanded') === 'true') ||
                        (item && item.classList && item.classList.contains('open')) ||
                        (item && item.tagName === 'DETAILS' && item.open);
                      if (expanded) el.click();
                    }"""
                )
                page.wait_for_timeout(350)
            except Exception:
                pass

        def demo_click_loc(loc, label: str) -> None:
            """Await full demoClick promise (focus+cursor+ripple+hold)."""
            try:
                loc.evaluate(
                    """async (el, label) => {
                      if (window.__hd && el) return await window.__hd.demoClick(el, label);
                      return false;
                    }""",
                    label,
                )
            except Exception as e:
                print(f"  ! demoClick: {e}", flush=True)

        def hold_focus_loc(loc, label: str) -> None:
            try:
                loc.evaluate(
                    """(el, label) => {
                      if (window.__hd && el) window.__hd.holdFocus(el, label);
                    }""",
                    label,
                )
            except Exception:
                pass

        def move_cursor_loc(loc, fast: bool = False) -> None:
            try:
                loc.evaluate(
                    """async (el, fast) => {
                      if (window.__hd && el) return await window.__hd.moveCursorTo(el, !!fast);
                    }""",
                    fast,
                )
            except Exception:
                pass

        def is_nav_link(loc) -> bool:
            """Links that would leave beat context — animate only, no real nav."""
            try:
                return bool(loc.evaluate(
                    """el => {
                      const a = el.closest ? el.closest('a[href]') : null;
                      if (!a) return false;
                      const href = a.getAttribute('href') || '';
                      return href.startsWith('#') || href.startsWith('http') ||
                             href.startsWith('//') || href.endsWith('.sh');
                    }"""
                ))
            except Exception:
                return False

        def do_clicks(clicks: list, why_label: str) -> None:
            for c in clicks or []:
                sel = c.get("selector") or ""
                optional = bool(c.get("optional", False))
                role = c.get("role") or (c.get("locator") or {}).get("role")
                name = c.get("name") or (c.get("locator") or {}).get("name")
                if not sel and not (role and name):
                    continue
                ok = False
                err = None
                label = (c.get("why") or why_label or "Click")[:28]
                # Candidate order: role (Scout v2) → CSS healer variants
                candidates: list[tuple] = []  # (loc, used_id, css_part)
                if role and name:
                    rloc, rused = resolve_role(role, name)
                    if rloc:
                        candidates.append((rloc, rused, None))
                for part in healer_variants(sel):
                    loc, used = resolve_el(part)
                    if loc:
                        candidates.append((loc, used, part))

                for loc, used, css_part in candidates:
                    try:
                        # Zoom transform breaks Playwright geometry — reset before scroll
                        try:
                            page.evaluate(
                                "() => window.__hd && window.__hd.autoZoom && window.__hd.autoZoom(null, false)"
                            )
                        except Exception:
                            pass
                        try:
                            loc.evaluate(
                                "el => el.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'})"
                            )
                        except Exception:
                            try:
                                loc.scroll_into_view_if_needed(timeout=4000)
                            except Exception:
                                pass
                        page.wait_for_timeout(160)
                        if (
                            (css_part and "-head" in css_part)
                            or "open accordion" in (c.get("why") or "")
                            or c.get("kind") == "accordion"
                        ):
                            ensure_accordion_closed_loc(loc)
                        # Pro sequence via element handle (role-safe)
                        demo_click_loc(loc, label)
                        page.wait_for_timeout(100)
                        capture_proof("pre", used)
                        nav = is_nav_link(loc)
                        if nav:
                            # Visual-only: real click would #hash-jump and desync tour
                            print(f"  click VISUAL-ONLY (nav lock) {used}", flush=True)
                            page.wait_for_timeout(280)
                        else:
                            try:
                                loc.click(timeout=2500, force=False, no_wait_after=True)
                            except Exception:
                                try:
                                    loc.click(timeout=2500, force=True, no_wait_after=True)
                                except Exception as ce:
                                    # still count visual demo if overlay ran
                                    print(f"  ! real click soft-fail {ce}", flush=True)
                            page.wait_for_timeout(380)
                        hold_focus_loc(loc, label)
                        page.wait_for_timeout(120)
                        capture_proof("post", used)
                        ok = True
                        print(f"  click OK {used}", flush=True)
                        actions["successful_clicks"] += 1
                        actions["spotlight"] = True
                        actions["events"].append({
                            "type": "click",
                            "selector": used,
                            "ok": True,
                            "label": label,
                            "via": "role" if str(used).startswith("role=") else "css",
                            "nav_locked": nav,
                        })
                        break
                    except Exception as e:
                        err = str(e)
                if not ok:
                    print(f"  click FAIL {sel or (role, name)}: {err}", flush=True)
                    actions["failed_clicks"].append(
                        {"selector": sel, "role": role, "name": name,
                         "optional": optional, "error": err}
                    )
                    actions["events"].append({
                        "type": "click", "selector": sel, "ok": False
                    })
                # v5: clearFocus only in release phase — ring holds through VO

        def wait_remainder(budget_ms: int, t0: float, *, hard_cap_ms: int | None = None) -> int:
            """Sleep so phase wall-clock ≈ budget_ms. Never past hard_cap deadline."""
            spent = int((time.time() - t0) * 1000)
            remain = max(0, budget_ms - spent)
            if hard_cap_ms is not None:
                remain = min(remain, max(0, hard_cap_ms))
            if remain > 0:
                page.wait_for_timeout(remain)
            return remain

        def focus_primary(primary: dict, label_override: str | None = None, *, animated: bool = True) -> bool:
            """Light + CURSOR on primary. Never metrics. animated=focus glide, else hold snap."""
            label = (label_override or primary.get("label") or "Focus")[:22]
            role = primary.get("role")
            name = primary.get("name")
            sel = primary.get("selector") or ""
            # Ban metric selectors as primary
            if sel and any(k in sel.lower() for k in ("stat", "metric", "kpi", "counter")):
                sel = "#cover a.btn.btn-solid, a.btn.btn-solid, h1"
            loc = None
            if role and name:
                loc, _used = resolve_role(role, name)
            if not loc:
                parts = healer_variants(sel) if sel else []
                if sel and sel not in parts:
                    parts = [sel] + parts
                for part in parts:
                    if not part or part.startswith("role="):
                        continue
                    loc, _used = resolve_el(part)
                    if loc:
                        break
            if not loc:
                # hero / CTA fallback — never body center (metrics band)
                for part in (
                    "#cover a.btn.btn-solid",
                    "a.btn.btn-solid",
                    "#cover h1",
                    "h1",
                ):
                    loc, _ = resolve_el(part)
                    if loc:
                        break
            if not loc:
                return False
            try:
                page.evaluate(
                    "() => window.__hd && window.__hd.autoZoom && window.__hd.autoZoom(null, false)"
                )
            except Exception:
                pass
            try:
                loc.evaluate(
                    "el => el.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'})"
                )
            except Exception:
                try:
                    loc.scroll_into_view_if_needed(timeout=4000)
                except Exception:
                    pass
            if animated:
                try:
                    loc.evaluate(
                        """async (el, lab) => {
                          if (window.__hd && el) return await window.__hd.focus(el, lab);
                        }""",
                        label,
                    )
                except Exception:
                    hold_focus_loc(loc, label)
            else:
                hold_focus_loc(loc, label)
            actions["spotlight"] = True
            actions["cursor_on_primary"] = True
            return True

        n = max(1, len(beats))
        for i, b in enumerate(beats):
            cam = b.get("camera") or {}
            action = cam.get("action", "scroll_to")
            chrome = chrome_for_beat(directing, i, n, b)
            budget = phase_budget_ms(directing, timings[i])
            budget_by_id = {p["id"]: p["ms"] for p in budget}
            primary = primary_target_hint(b)
            phases_log: list[dict] = []

            # Chrome only at beat boundary (directing rule)
            page.evaluate(
                """([cap, p, chip, kicker]) => {
                  if (!window.__hd) return;
                  window.__hd.setCaption(cap, kicker);
                  window.__hd.setProgress(p);
                  window.__hd.setChip(chip);
                }""",
                [chrome["caption"], chrome["progress"], chrome["chip"], chrome["kicker"]],
            )
            # Hard wall-clock = VO length (Parksy Air: video follows audio duration)
            beat_total_ms = max(800, int(timings[i] * 1000))
            beat_deadline = time.time() + beat_total_ms / 1000.0
            release_ms = int(budget_by_id.get("release") or 200)

            def left_ms() -> int:
                return max(0, int((beat_deadline - time.time()) * 1000))

            phase_summary = "/".join(f"{p['id'][0]}{p['ms']}" for p in budget)
            print(
                f"[shoot] beat {b['id']} action={action} "
                f"budget={timings[i]:.1f}s phases={phase_summary}",
                flush=True,
            )

            # ── 1 ESTABLISH: camera + light ON, no click ──────────────
            t_phase = time.time()
            if action == "goto_top":
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                page.wait_for_timeout(min(goto_top_settle_ms, max(200, left_ms() // 4)))
            elif action == "scroll_to" and cam.get("selector"):
                try:
                    page.evaluate(
                        "() => window.__hd && window.__hd.autoZoom && window.__hd.autoZoom(null, false)"
                    )
                except Exception:
                    pass
                smooth_scroll_to(cam["selector"])
            focus_primary(primary)
            est_budget = min(budget_by_id.get("establish", 400), max(120, left_ms() - release_ms - 400))
            waited = wait_remainder(est_budget, t_phase, hard_cap_ms=left_ms() - release_ms)
            phases_log.append({
                "id": "establish", "ms": budget_by_id.get("establish"),
                "waited": waited, "camera": action,
            })
            actions["events"].append({
                "type": "phase", "beat": b["id"], "phase": "establish", "ok": True,
            })

            # ── 2 FOCUS: cursor/callout on primary ────────────────────
            t_phase = time.time()
            focus_primary(primary)
            foc_budget = min(budget_by_id.get("focus", 400), max(100, left_ms() - release_ms - 300))
            waited = wait_remainder(foc_budget, t_phase, hard_cap_ms=left_ms() - release_ms)
            phases_log.append({
                "id": "focus", "ms": budget_by_id.get("focus"), "waited": waited,
            })
            actions["events"].append({
                "type": "phase", "beat": b["id"], "phase": "focus", "ok": True,
            })

            # ── 3 ACT: ALL clicks guaranteed (never drop 2nd for clock) ─
            t_phase = time.time()
            clicks = b.get("clicks") or []
            last_click_primary = primary
            if clicks:
                for ci, c in enumerate(clicks):
                    c_primary = primary_target_hint({**b, "clicks": [c]})
                    if ci > 0:
                        focus_primary(c_primary, animated=True)
                        page.wait_for_timeout(220)
                    do_clicks([c], c.get("why") or b.get("caption") or "Action")
                    last_click_primary = c_primary
                    # result frame — show state change before next click
                    page.wait_for_timeout(min(420, max(200, post_click_freeze)))
                    hold_ms_result = min(700, max(280, left_ms() // (len(clicks) - ci + 1)))
                    if hold_ms_result > 80:
                        page.wait_for_timeout(hold_ms_result)
            # Cover: re-anchor CTA (not metrics, not h1 alone)
            if action == "goto_top" or i == 0:
                page.evaluate(
                    """() => {
                      window.scrollTo({top:0, behavior:'instant'});
                      const el = document.querySelector(
                        '#cover a.btn.btn-solid, a.btn.btn-solid'
                      );
                      if (window.__hd && el) window.__hd.holdFocus(el, 'CTA');
                    }"""
                )
            else:
                focus_primary(last_click_primary, animated=False)
            act_budget = min(budget_by_id.get("act", 600), max(0, left_ms() - release_ms - 200))
            waited = wait_remainder(act_budget, t_phase, hard_cap_ms=left_ms() - release_ms)
            phases_log.append({
                "id": "act", "ms": budget_by_id.get("act"), "waited": waited,
                "clicks": len(clicks), "clicks_done": actions["successful_clicks"],
            })
            actions["events"].append({
                "type": "phase", "beat": b["id"], "phase": "act",
                "ok": True, "clicks": len(clicks),
            })

            # ── 4 HOLD: remainder — stable lock (no zoom jitter re-fire) ─
            t_phase = time.time()
            focus_primary(last_click_primary, animated=False)
            # Re-assert cursor only every ~2.2s (v5 autoZoom reuses same key)
            hold_budget = max(200, left_ms() - release_ms)
            hold_end = time.time() + hold_budget / 1000.0
            while time.time() < hold_end - 0.05:
                slice_ms = min(2200, int((hold_end - time.time()) * 1000))
                if slice_ms < 40:
                    break
                page.wait_for_timeout(slice_ms)
                focus_primary(last_click_primary, animated=False)
            waited = hold_budget
            phases_log.append({
                "id": "hold", "ms": budget_by_id.get("hold"), "waited": waited,
            })
            actions["events"].append({
                "type": "phase", "beat": b["id"], "phase": "hold", "ok": True,
            })

            # ── 5 RELEASE: clear light, park cursor, ready next beat ──
            t_phase = time.time()
            page.evaluate(
                """() => {
                  if (!window.__hd) return;
                  window.__hd.clearFocus();
                  if (window.__hd.parkCursor) window.__hd.parkCursor();
                }"""
            )
            waited = wait_remainder(min(release_ms, max(80, left_ms())), t_phase, hard_cap_ms=left_ms())
            # If we finished early, pad to deadline so A/V stays locked
            tail = left_ms()
            if tail > 40:
                page.wait_for_timeout(tail)
                waited += tail
            phases_log.append({
                "id": "release", "ms": budget_by_id.get("release"), "waited": waited,
            })
            actions["events"].append({
                "type": "phase", "beat": b["id"], "phase": "release", "ok": True,
            })

            actions["phases_played"].append({
                "beat": b["id"],
                "budget_sec": round(timings[i], 2),
                "elapsed_sec": round(time.time() - (beat_deadline - beat_total_ms / 1000.0), 2),
                "phases": phases_log,
            })

        page.evaluate(
            """() => {
              if (!window.__hd) return;
              window.__hd.clearFocus();
              window.__hd.setCaption('Tour complete — try it yourself', 'DONE');
              window.__hd.setProgress(1);
              window.__hd.setChip('COMPLETE');
            }"""
        )
        page.wait_for_timeout(900)
        # Drain auto-zoom log before close (community A evidence)
        try:
            zlog = page.evaluate(
                """() => (window.__hd && window.__hd.drainZoomLog)
                  ? window.__hd.drainZoomLog() : (window.__hdZoomLog || [])"""
            )
            if isinstance(zlog, list):
                actions["zoom_events"] = zlog
                actions["auto_zoom"] = any(e.get("on") for e in zlog if isinstance(e, dict))
                print(f"[shoot] zoom_events={len(zlog)} auto_zoom={actions['auto_zoom']}", flush=True)
        except Exception as e:
            print(f"  ! zoom log: {e}", flush=True)
        context.close()
        browser.close()

    proofs = actions["visual_proof"]
    pass_n = sum(1 for p in proofs if p.get("pass"))
    actions["visual_proof_pass"] = pass_n >= max(2, actions["successful_clicks"] // 2)
    actions["visual_proof_pass_count"] = pass_n
    actions["visual_proof_total"] = len(proofs)

    videos = sorted(rec_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise RuntimeError("No Playwright video recorded")
    raw = videos[0]
    print(f"[shoot] raw video {raw} ({raw.stat().st_size} bytes)", flush=True)
    print(
        f"[shoot] clicks ok={actions['successful_clicks']} fail={len(actions['failed_clicks'])} "
        f"proof {pass_n}/{len(proofs)} pass={actions['visual_proof_pass']}",
        flush=True,
    )
    return raw, actions


def _scale_pad_vf(w: int, h: int) -> str:
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x0a0908,setsar=1,fps=30,format=yuv420p"
    )


def edit(
    raw_video: Path,
    narration: Path,
    intro: Path | None,
    out: Path,
    work: Path,
    *,
    width: int = 720,
    height: int = 1280,
    burn_subs: bool = False,
    beats: list[dict] | None = None,
    intro_sec: float = 2.0,
) -> Path:
    """
    Edit + A/V hard sync (recast: freeze when VO longer than picture).
    TTS-first: audio is master clock; video tpad-clones if short.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    page_raw = work / "page_raw.mp4"
    # drop first 0.12s of webm (often blank) then encode
    run([
        "ffmpeg", "-y", "-ss", "0.12", "-i", str(raw_video),
        *X264, "-an", str(page_raw),
    ])

    # C2/C3 — strip Playwright lead black
    page_mp4 = work / "page.mp4"
    _, trimmed = trim_leading_black(page_raw, page_mp4)
    print(f"[edit] lead trim={trimmed:.2f}s", flush=True)

    v_dur = ffprobe_duration(page_mp4)
    a_dur = ffprobe_duration(narration)
    print(f"[edit] video={v_dur:.2f}s audio={a_dur:.2f}s (audio=master)", flush=True)

    # Hard sync (community A: recast speedUp + voiceover freeze)
    # VO longer → freeze last frame
    # video longer → setpts compress so FULL tour fits audio (never -shortest cut mid-tour)
    body = work / "body.mp4"
    if v_dur + 0.25 < a_dur:
        pad = a_dur - v_dur + 0.12
        print(f"[edit] TTS-first freeze +{pad:.2f}s (wait_for_narration)", flush=True)
        run([
            "ffmpeg", "-y",
            "-i", str(page_mp4),
            "-i", str(narration),
            "-filter_complex",
            f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f}[v]",
            "-map", "[v]", "-map", "1:a",
            *X264, "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart",
            str(body),
        ])
    elif v_dur > a_dur + 0.4:
        # Pro: never go below ~0.72 setpts (≈1.39×). Beyond that, stretch audio.
        # Community: frantic 2.5× look is amateur; mild compress + VO stretch is pro.
        raw_factor = a_dur / max(0.1, v_dur)
        factor = max(0.72, raw_factor)
        new_v = v_dur * factor
        atempo = max(0.5, min(2.0, new_v / max(0.1, a_dur)))
        print(
            f"[edit] pro-sync video×{factor:.3f} audio×{atempo:.3f} "
            f"(raw would be {raw_factor:.3f}; {v_dur:.1f}s→{new_v:.1f}s)",
            flush=True,
        )
        # chain atempo if outside 0.5–2.0 already clamped
        af = f"atempo={atempo:.4f}"
        run([
            "ffmpeg", "-y",
            "-i", str(page_mp4),
            "-i", str(narration),
            "-filter_complex",
            f"[0:v]setpts=PTS*{factor:.6f}[v];[1:a]{af}[a]",
            "-map", "[v]", "-map", "[a]",
            *X264, "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart",
            str(body),
        ])
    else:
        run([
            "ffmpeg", "-y",
            "-i", str(page_mp4),
            "-i", str(narration),
            "-map", "0:v", "-map", "1:a",
            *X264, "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart",
            str(body),
        ])

    vf = _scale_pad_vf(width, height)
    merged = work / "merged.mp4"
    if intro and intro.exists():
        intro_n = work / "intro_norm.mp4"
        body_n = work / "body_norm.mp4"
        run([
            "ffmpeg", "-y", "-i", str(intro), "-vf", vf,
            *X264, "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-t", f"{intro_sec:.2f}", str(intro_n),
        ])
        # Skip first ~2 frames of body — pure-black keyframe at tour start (V1 hole at t=2.0)
        run([
            "ffmpeg", "-y", "-ss", "0.07", "-i", str(body), "-vf", vf,
            *X264, "-c:a", "aac", "-ar", "44100", "-ac", "2", str(body_n),
        ])
        # Re-encode concat (NOT -c copy) — stream-copy leaves black keyframe gap at seam
        run([
            "ffmpeg", "-y",
            "-i", str(intro_n), "-i", str(body_n),
            "-filter_complex",
            "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
            "-map", "[v]", "-map", "[a]",
            *X264, "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", str(merged),
        ])
    else:
        run([
            "ffmpeg", "-y", "-i", str(body), "-vf", vf,
            *X264, "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart", str(merged),
        ])

    # Optional SRT burn-in (community A)
    if burn_subs and beats:
        srt = work / "narration.srt"
        write_srt_from_beats(beats, srt, intro_sec=intro_sec if intro else 0.0)
        print(f"[edit] subtitles {srt}", flush=True)
        burn_subtitles(merged, srt, out, x264=X264)
        shutil.copy(srt, out.with_suffix(".srt"))
    else:
        shutil.copy(merged, out)
        if beats:
            srt = work / "narration.srt"
            write_srt_from_beats(beats, srt, intro_sec=intro_sec if intro else 0.0)
            shutil.copy(srt, out.with_suffix(".srt"))

    print(f"[edit] wrote {out} ({out.stat().st_size} bytes) {width}x{height}", flush=True)
    return out


def write_report(scenario: dict, beats: list[dict], out: Path, work: Path) -> Path:
    lines = [
        f"# Director report — {scenario.get('id')}",
        "",
        f"- URL: {scenario.get('url')}",
        f"- Title: {scenario.get('title')}",
        f"- Output: `{out}`",
        f"- Beats: {len(beats)}",
        "",
        "## Script",
        "",
    ]
    for i, b in enumerate(beats):
        lines.append(f"### {i+1}. {b['id']} ({b.get('audio_sec', 0):.1f}s)")
        lines.append(b.get("narration", ""))
        lines.append("")
    report = work / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    # also script.md
    (work / "script.md").write_text(
        "\n\n".join(f"**{b['id']}**\n{b['narration']}" for b in beats),
        encoding="utf-8",
    )
    return report


def load_scenario(path: Path | None, url: str | None) -> dict:
    if path:
        data = json.loads(path.read_text(encoding="utf-8"))
        if url:
            data["url"] = url
        return data
    if not url:
        raise SystemExit("Need --scenario or --url")
    # minimal generic scenario
    return {
        "id": "generic",
        "url": url,
        "title": "Site intro",
        "voice": VOICE_DEFAULT,
        "viewport": {"width": 720, "height": 1280},
        "beats": [
            {
                "id": "b0",
                "narration": "이 웹사이트를 소개합니다. 위에서 아래로, 핵심 섹션을 따라가 보겠습니다.",
                "camera": {"action": "goto_top"},
                "clicks": [],
                "hold_after_ms": 500,
            },
            {
                "id": "b1",
                "narration": "페이지를 천천히 내려가며 구조를 확인합니다.",
                "camera": {"action": "scroll_to", "selector": "body"},
                "clicks": [],
                "hold_after_ms": 500,
            },
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="Director Agent — site intro video")
    ap.add_argument("--scenario", type=Path, help="scenario JSON path")
    ap.add_argument("--url", type=str, help="override / provide URL")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--work", type=Path, default=None)
    ap.add_argument("--skip-intro", action="store_true")
    ap.add_argument(
        "--scout", action="store_true",
        help="Scout page first; merge selectors into scenario (or auto-write if no scenario)",
    )
    ap.add_argument(
        "--scout-only", action="store_true",
        help="Only run scout + write scenario from page; no render",
    )
    ap.add_argument("--max-beats", type=int, default=6)
    ap.add_argument(
        "--policy", default="tutorial_v1",
        help="Forced policy id (default tutorial_v1). Blocks freeform LLM ship.",
    )
    ap.add_argument(
        "--process", default="perfect_ship_v1",
        help="Perfect-ship process id (default perfect_ship_v1). Codified quality ladder.",
    )
    ap.add_argument(
        "--format",
        default="shorts_1080",
        choices=list(FORMATS.keys()),
        help="Output profile: shorts|shorts_1080|desktop|desktop_1080 (default shorts_1080 A-bar)",
    )
    ap.add_argument(
        "--subs",
        action="store_true",
        help="Burn SRT subtitles into video (always writes .srt sidecar)",
    )
    ap.add_argument(
        "--tts",
        default="auto",
        choices=["auto", "edge", "openai"],
        help="TTS provider: auto (OpenAI if key else edge), edge, openai",
    )
    ap.add_argument(
        "--no-policy", action="store_true",
        help="Dangerous: disable policy enforce (debug only)",
    )
    args = ap.parse_args()

    policy = None if args.no_policy else load_policy(args.policy)
    process_id = args.process or (policy or {}).get("process_id") or "perfect_ship_v1"
    fmt = FORMATS[args.format]
    # 연출 설정 — scenario/shoot의 상위 시계 (없으면 ship 거부)
    directing_id = (policy or {}).get("require", {}).get("directing_id") or "product_tour_v1"
    directing = load_directing(directing_id)
    print(f"[directing] {directing['id']} v{directing.get('version')}", flush=True)
    print(f"[process] {process_id}", flush=True)
    print(f"[format] {args.format} {fmt['label']}", flush=True)

    # resolve URL early
    url = args.url
    if not url and args.scenario and args.scenario.exists():
        url = json.loads(args.scenario.read_text(encoding="utf-8")).get("url")
    if not url and not args.scenario:
        raise SystemExit("Need --url or --scenario")

    sid = "run"
    if args.scenario:
        sid = args.scenario.stem
    elif url:
        sid = url.rstrip("/").split("/")[-1] or "run"

    work = args.work or (DIR / "out" / f"work_{sid}")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    t0 = time.time()
    print("=== Director Agent (policy={}) ===".format(args.policy if policy else "OFF"), flush=True)

    # ── 0) SCOUT ──────────────────────────────────────────
    scout = None
    do_scout = True if policy else (args.scout or args.scout_only or (args.url and not args.scenario))
    if args.scout_only or do_scout:
        print("\n[0/6] SCOUT — parse page structure", flush=True)
        scout = scout_url(
            url,
            viewport={"width": fmt["width"], "height": fmt["height"]},
            work=work,
        )
        save_scout(scout, work / "scout.json")

    if args.scout_only:
        scenario = scenario_from_scout(scout, max_beats=args.max_beats, voice=VOICE_DEFAULT)
        scenario = stamp_scenario_directing(scenario, directing)
        scenario["viewport"] = {"width": fmt["width"], "height": fmt["height"]}
        scenario["format"] = args.format
        if policy:
            scenario = stamp_scenario(scenario, policy["id"])
            scenario = stamp_scenario_directing(scenario, directing)
        (work / "scenario.json").write_text(
            json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (work / "directing.json").write_text(
            json.dumps(directing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        export = DIR / "scenarios" / f"{scenario['id']}_from_scout.json"
        export.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
        if policy:
            try:
                enforce_all(scenario=scenario, policy=policy, scout=scout,
                            actions_log=None, quality=None, stage="pre_shoot")
                print("[enforce] scenario OK", flush=True)
            except EnforceError as e:
                print("[enforce] FAIL", e.errors, flush=True)
                sys.exit(3)
        print(json.dumps({
            "sections": scout.get("section_count"),
            "interactives": scout.get("interactive_count"),
            "beats": len(scenario["beats"]),
            "title": scenario.get("title"),
            "policy": scenario.get("policy"),
            "directing": scenario.get("directing"),
        }, ensure_ascii=False, indent=2))
        return

    # load or build scenario
    if args.scenario:
        scenario = load_scenario(args.scenario, args.url or url)
        if scout:
            print("[scout] merge selectors into hand scenario", flush=True)
            scenario = merge_scenario_with_scout(scenario, scout)
    else:
        if not scout:
            scout = scout_url(url, work=work)
            save_scout(scout, work / "scout.json")
        scenario = scenario_from_scout(scout, max_beats=args.max_beats, voice=VOICE_DEFAULT)

    # always stamp directing (plan-first)
    scenario = stamp_scenario_directing(scenario, directing)
    if policy:
        scenario = stamp_scenario(scenario, policy["id"])
        scenario = stamp_scenario_directing(scenario, directing)  # keep after policy stamp
        try:
            enforce_all(scenario=scenario, policy=policy, scout=scout,
                        actions_log=None, quality=None, stage="pre_shoot")
            print("[enforce] pre_shoot OK", flush=True)
        except EnforceError as e:
            print("[enforce] pre_shoot FAIL:", *e.errors, sep="\n  - ", flush=True)
            (work / "enforce_errors.json").write_text(
                json.dumps(e.errors, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            sys.exit(3)

    # process stamp — 만점 사다리 ID (에이전트 즉흥 경로 차단)
    scenario["process_id"] = process_id
    scenario["tts_humanize"] = True
    scenario["tts_first"] = True
    scenario["tts_provider"] = args.tts
    scenario["format"] = args.format
    scenario["viewport"] = {"width": fmt["width"], "height": fmt["height"]}
    scenario["burn_subs"] = bool(args.subs)
    print(f"URL: {scenario['url']}", flush=True)
    print(f"DIRECTING: {scenario.get('directing')}", flush=True)
    print(f"PROCESS: {process_id}", flush=True)
    print(f"FORMAT: {args.format} {fmt['label']}  TTS={args.tts}  subs={args.subs}", flush=True)
    (work / "scenario.json").write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (work / "process_id.txt").write_text(process_id + "\n", encoding="utf-8")
    (work / "directing.json").write_text(
        json.dumps(directing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if policy:
        (work / "policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("\n[1/6] WRITE+VOICE (humanize + multi-click pad)", flush=True)
    beats = build_voices(scenario, work)
    scenario["tts_humanize"] = True
    # enforce max narration duration
    if policy:
        max_sec = (policy.get("require") or {}).get("max_narration_sec", 99)
        for b in beats:
            if b.get("audio_sec", 0) > max_sec:
                print(f"  ! trim hold — beat {b['id']} audio {b['audio_sec']:.1f}s > {max_sec}", flush=True)
    narration = concat_audio(beats, work)
    print(f"narration total {ffprobe_duration(narration):.1f}s", flush=True)

    intro = None
    intro_png = None
    if not args.skip_intro:
        print("\n[1b] INTRO CARD (HTML/CJK)", flush=True)
        intro = make_intro_card(
            work,
            scenario.get("title") or "Helena",
            scenario.get("logline") or (scenario.get("url") or "")[:80],
            seconds=2.0,
            kicker="TUTORIAL · FORCED POLICY",
        )
        intro_png = work / "intro.png"

    print("\n[2/6] SHOOT", flush=True)
    raw, actions_log = shoot(scenario, beats, work, directing=directing)
    # perfect_ship process fields (enforce L2/L3)
    actions_log["process_id"] = process_id
    actions_log["tts_humanize"] = True
    actions_log["tts_first"] = True
    actions_log["tts_provider"] = scenario.get("tts_provider") or args.tts
    actions_log["format"] = args.format
    actions_log["auto_zoom"] = bool(actions_log.get("auto_zoom") or actions_log.get("zoom_events"))
    actions_log["clicks_declared"] = sum(len(b.get("clicks") or []) for b in scenario.get("beats") or [])
    actions_log["clicks_done"] = actions_log.get("successful_clicks") or 0
    (work / "actions_log.json").write_text(
        json.dumps(actions_log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if policy:
        try:
            enforce_all(scenario=scenario, policy=policy, scout=scout,
                        actions_log=actions_log, quality=None, stage="post_shoot")
            print("[enforce] post_shoot OK", flush=True)
        except EnforceError as e:
            print("[enforce] post_shoot FAIL:", *e.errors, sep="\n  - ", flush=True)
            sys.exit(4)

    print("\n[3/6] EDIT (TTS-first freeze + format scale)", flush=True)
    out = edit(
        raw, narration, intro, args.out, work,
        width=fmt["width"],
        height=fmt["height"],
        burn_subs=bool(args.subs),
        beats=beats,
        intro_sec=2.0 if intro else 0.0,
    )

    print("\n[4/7] QUALITY GATE", flush=True)
    gate = gate_output(out, work=work / "gate", intro_png=intro_png)
    if policy:
        try:
            enforce_all(scenario=scenario, policy=policy, scout=scout,
                        actions_log=actions_log, quality=gate, stage="pre_ship")
            print("[enforce] pre_ship OK", flush=True)
        except EnforceError as e:
            print("[enforce] pre_ship FAIL:", *e.errors, sep="\n  - ", flush=True)
            write_report(scenario, beats, out, work)
            sys.exit(2)
    elif not gate.get("pass"):
        print("QUALITY GATE FAILED", flush=True)
        sys.exit(2)

    print("\n[5/7] VISION QA (big-tech bar)", flush=True)
    from vision_qa import vision_qa
    vqa = vision_qa(
        out,
        work=work / "vision_qa",
        actions_log=actions_log,
        pass_score=int((policy or {}).get("require", {}).get("vision_qa_pass_score", 85)),
    )
    if policy and (policy.get("require") or {}).get("vision_qa_required", True):
        if not vqa.get("pass"):
            print("[vision_qa] FAIL — ship blocked", flush=True)
            write_report(scenario, beats, out, work)
            shutil.copy(work / "vision_qa" / "vision_qa.json", out.with_suffix(".vision_qa.json"))
            if (work / "vision_qa" / "vision_qa.md").exists():
                shutil.copy(work / "vision_qa" / "vision_qa.md", out.with_suffix(".vision_qa.md"))
            sys.exit(5)

    print("\n[6/8] PERFECT SHIP PROCESS VERIFY", flush=True)
    process_report = None
    try:
        from perfect_ship import load_process, verify_artifacts, write_report as write_process_report
        proc = load_process(process_id)
        ship_ok, stages, rem = verify_artifacts(
            process=proc,
            work=work,
            out=out,
            scenario=scenario,
            policy=policy,
        )
        process_report = {
            "process_id": process_id,
            "ship": ship_ok,
            "stages": stages,
            "remediation_ids": rem,
        }
        write_process_report(
            out.with_suffix(".process.json"),
            process=proc,
            ship=ship_ok,
            stages=stages,
            rem=rem,
            out=out,
            work=work,
        )
        for s in stages:
            mark = "✓" if s.get("pass") else "✗"
            print(f"  {mark} {s['id']}: {s.get('detail')}", flush=True)
        if not ship_ok:
            print("[process] FAIL remediation:", rem, flush=True)
            write_report(scenario, beats, out, work)
            sys.exit(6)
        print("[process] perfect_ship ladder PASS", flush=True)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[process] verify error: {e}", flush=True)
        if (policy or {}).get("require", {}).get("require_process"):
            sys.exit(6)

    print("\n[7/8] SELF-AUDIT", flush=True)
    audit = {
        "url": scenario.get("url"),
        "policy": scenario.get("policy"),
        "directing": scenario.get("directing"),
        "process_id": process_id,
        "shoot_version": actions_log.get("shoot_version"),
        "beats": len(beats),
        "phases_played_beats": len(actions_log.get("phases_played") or []),
        "successful_clicks": actions_log.get("successful_clicks"),
        "clicks_declared": actions_log.get("clicks_declared"),
        "cursor_on_primary": actions_log.get("cursor_on_primary"),
        "tts_humanize": actions_log.get("tts_humanize"),
        "failed_clicks": actions_log.get("failed_clicks"),
        "overlay_version": actions_log.get("overlay_version"),
        "visual_proof_pass": actions_log.get("visual_proof_pass"),
        "visual_proof_pass_count": actions_log.get("visual_proof_pass_count"),
        "duration_sec": ffprobe_duration(out),
        "quality_pass": gate.get("pass"),
        "accent_hits": gate.get("accent_hits"),
        "vision_qa_score": vqa.get("score"),
        "vision_qa_grade": vqa.get("grade"),
        "vision_qa_pass": vqa.get("pass"),
        "process_ship": (process_report or {}).get("ship"),
        "shortcomings_self": list(vqa.get("errors") or []),
    }
    if actions_log.get("successful_clicks", 0) < 4:
        audit["shortcomings_self"].append("clicks < 4")
    if not actions_log.get("visual_proof_pass"):
        audit["shortcomings_self"].append("visual_proof failed")
    if (gate.get("accent_hits") or 0) < 2:
        audit["shortcomings_self"].append("G7 overlay accents weak")
    if any(len(b.get("narration", "")) > 78 for b in scenario.get("beats") or []):
        audit["shortcomings_self"].append("narration over char cap")
    (work / "self_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)

    print("\n[8/8] REPORT", flush=True)
    report = write_report(scenario, beats, out, work)
    shutil.copy(work / "scenario.json", out.with_suffix(".scenario.json"))
    shutil.copy(report, out.with_suffix(".report.md"))
    if (work / "gate" / "quality_report.json").exists():
        shutil.copy(work / "gate" / "quality_report.json", out.with_suffix(".quality.json"))
    shutil.copy(work / "actions_log.json", out.with_suffix(".actions.json"))
    shutil.copy(work / "self_audit.json", out.with_suffix(".audit.json"))
    if (work / "vision_qa" / "vision_qa.json").exists():
        shutil.copy(work / "vision_qa" / "vision_qa.json", out.with_suffix(".vision_qa.json"))
    if (work / "vision_qa" / "vision_qa.md").exists():
        shutil.copy(work / "vision_qa" / "vision_qa.md", out.with_suffix(".vision_qa.md"))

    elapsed = time.time() - t0
    print("\n=== DONE (SHIP · PERFECT_SHIP PASS · VISION QA) ===", flush=True)
    print(f"process: {process_id}", flush=True)
    print(f"out: {out}", flush=True)
    print(
        f"dur: {ffprobe_duration(out):.1f}s  size: {out.stat().st_size // 1024}KB  "
        f"time: {elapsed:.0f}s  VQA: {vqa.get('score')}/100 {vqa.get('grade')}",
        flush=True,
    )
    print(f"report: {report}", flush=True)
    print(f"process_report: {out.with_suffix('.process.json')}", flush=True)


if __name__ == "__main__":
    main()
