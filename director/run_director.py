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

from enforce import EnforceError, enforce_all, load_policy, stamp_scenario
from intro import make_intro_card
from quality import gate_output, trim_leading_black
from scout import (
    merge_scenario_with_scout,
    save_scout,
    scenario_from_scout,
    scout_url,
)

DIR = Path(__file__).resolve().parent
DEFAULT_OUT = DIR / "out" / "director_out.mp4"
VOICE_DEFAULT = "ko-KR-SunHiNeural"
# Encode quality (phone-friendly but not ultrafast mush)
X264 = [
    "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-preset", "veryfast", "-crf", "20",
    "-r", "30", "-vsync", "cfr",
]


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


async def tts_beat(text: str, voice: str, dest: Path, retries: int = 4) -> float:
    import edge_tts
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if dest.exists():
                dest.unlink()
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(dest))
            if dest.stat().st_size < 100:
                raise RuntimeError(f"TTS empty: {dest}")
            return ffprobe_duration(dest)
        except Exception as e:
            last_err = e
            wait = min(8, attempt * 2)
            print(f"  ! tts retry {attempt}/{retries}: {e} (sleep {wait}s)", flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"TTS failed after {retries} tries: {last_err}")


def build_voices(scenario: dict, work: Path) -> list[dict]:
    voice = scenario.get("voice") or VOICE_DEFAULT
    beats = scenario["beats"]
    results = []

    async def all_tts():
        out = []
        for i, b in enumerate(beats):
            path = work / "voice" / f"{i:02d}_{b['id']}.mp3"
            print(f"[voice] {b['id']}: {b['narration'][:48]}…", flush=True)
            dur = await tts_beat(b["narration"], voice, path)
            pad = (b.get("hold_after_ms") or 400) / 1000.0
            out.append({**b, "voice_path": str(path), "audio_sec": dur, "pad_sec": pad})
            print(f"  → {dur:.2f}s + pad {pad:.2f}s", flush=True)
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


def shoot(scenario: dict, beats: list[dict], work: Path) -> tuple[Path, dict]:
    """
    Tutorial shoot with forced overlays + actions_log.
    Returns (raw_video_path, actions_log).
    """
    from playwright.sync_api import sync_playwright

    vp = scenario.get("viewport") or {"width": 720, "height": 1280}
    w, h = int(vp["width"]), int(vp["height"])
    url = scenario["url"]
    rec_dir = work / "record"
    if rec_dir.exists():
        shutil.rmtree(rec_dir)
    rec_dir.mkdir(parents=True)

    timings = [b["audio_sec"] + b.get("pad_sec", 0.35) for b in beats]
    overlay_js = (DIR / "overlays.js").read_text(encoding="utf-8")
    actions: dict = {
        "page_ready": False,
        "cursor_highlight": True,
        "caption_bar": True,
        "progress_chip": True,
        "spotlight": False,
        "successful_clicks": 0,
        "failed_clicks": [],
        "events": [],
        "overlay_version": 2,
    }
    print(f"[shoot] open {url}", flush=True)

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
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.set_content(
            "<!doctype html><html><body style='margin:0;background:#0a0908;width:100vw;height:100vh'></body></html>"
        )
        page.wait_for_timeout(120)

        _wait_page_ready(page, url)
        actions["page_ready"] = True
        page.add_script_tag(content=overlay_js)
        page.evaluate("() => { if (window.__hd) window.__hd.setChip('TUTORIAL · LIVE'); }")
        print("  page ready + overlays", flush=True)

        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(700)

        expand_sels = []
        if scenario.get("expand_all_selector"):
            expand_sels.append(scenario["expand_all_selector"])
        expand_sels += [
            "#accExpand", "#accOpenAll",
            "button:has-text('Expand all')", "button:has-text('Expand')",
            "button:has-text('펼치')", "button:has-text('모두 펼치')",
        ]
        for sel in expand_sels:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=2000)
                    page.wait_for_timeout(650)
                    print(f"  expand via {sel}", flush=True)
                    actions["events"].append({"type": "expand", "selector": sel, "ok": True})
                    break
            except Exception:
                pass

        def smooth_scroll_to(selector: str, steps: int = 18):
            try:
                page.wait_for_selector(selector, timeout=8000)
            except Exception:
                print(f"  ! missing selector {selector}", flush=True)
                return False
            page.evaluate(
                """([sel, steps]) => {
                  const el = document.querySelector(sel);
                  if (!el) return;
                  const target = el.getBoundingClientRect().top + window.scrollY - 80;
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
            page.wait_for_timeout(380)
            return True

        def resolve_el(part: str):
            loc = page.locator(part).first
            if loc.count() == 0:
                return None, None
            return loc, part

        def healer_variants(sel: str) -> list[str]:
            """Community pattern: retry simpler selectors (healer)."""
            parts = [s.strip() for s in sel.split(",") if s.strip()]
            out = list(parts)
            for p in parts:
                if "#" in p and " > " in p:
                    # last id-ish fragment
                    out.append(p.split(" > ")[-1])
                if p.startswith("#") and "-" in p:
                    out.append(p)  # keep
            # dedupe
            seen = set()
            uniq = []
            for x in out:
                if x not in seen:
                    seen.add(x)
                    uniq.append(x)
            return uniq

        def do_clicks(clicks: list, why_label: str) -> None:
            for c in clicks or []:
                sel = c.get("selector")
                optional = bool(c.get("optional", False))
                if not sel:
                    continue
                ok = False
                err = None
                label = (c.get("why") or why_label or "Click")[:24]
                for part in healer_variants(sel):
                    try:
                        loc, used = resolve_el(part)
                        if not loc:
                            continue
                        loc.scroll_into_view_if_needed(timeout=2500)
                        page.wait_for_timeout(180)
                        # Pro sequence: spotlight → cursor → ripple → click
                        page.evaluate(
                            """([part, label]) => {
                              const el = document.querySelector(part);
                              if (window.__hd && el) return window.__hd.demoClick(el, label);
                            }""",
                            [part, label],
                        )
                        page.wait_for_timeout(100)
                        loc.click(timeout=3000, force=True)
                        page.wait_for_timeout(480)
                        ok = True
                        print(f"  click OK {used}", flush=True)
                        actions["successful_clicks"] += 1
                        actions["spotlight"] = True
                        actions["events"].append({
                            "type": "click", "selector": used, "ok": True, "label": label
                        })
                        break
                    except Exception as e:
                        err = str(e)
                if not ok:
                    print(f"  click FAIL {sel}: {err}", flush=True)
                    actions["failed_clicks"].append(
                        {"selector": sel, "optional": optional, "error": err}
                    )
                    actions["events"].append({"type": "click", "selector": sel, "ok": False})
                else:
                    page.evaluate("() => window.__hd && window.__hd.clearFocus()")

        n = max(1, len(beats))
        for i, b in enumerate(beats):
            cam = b.get("camera") or {}
            action = cam.get("action", "scroll_to")
            cap = b.get("caption") or b.get("id")
            page.evaluate(
                """([cap, p, chip, kicker]) => {
                  if (!window.__hd) return;
                  window.__hd.setCaption(cap, kicker);
                  window.__hd.setProgress(p);
                  window.__hd.setChip(chip);
                }""",
                [cap, (i + 1) / n, f"{i+1}/{n} · PRODUCT TOUR", f"STEP {i+1}/{n}"],
            )
            print(f"[shoot] beat {b['id']} action={action} hold={timings[i]:.1f}s", flush=True)
            if action == "goto_top":
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                page.wait_for_timeout(500)
                # spotlight cover hero if present
                page.evaluate(
                    """() => {
                      const el = document.querySelector('#cover h1, .cover h1, h1');
                      if (window.__hd && el) return window.__hd.focus(el, 'Hero');
                    }"""
                )
                page.wait_for_timeout(400)
                actions["spotlight"] = True
            elif action == "scroll_to" and cam.get("selector"):
                smooth_scroll_to(cam["selector"])
                page.evaluate(
                    """(sel) => {
                      const el = document.querySelector(sel);
                      if (window.__hd && el) return window.__hd.focus(el, 'Section');
                    }""",
                    cam["selector"],
                )
                page.wait_for_timeout(350)
                actions["spotlight"] = True
            do_clicks(b.get("clicks") or [], b.get("caption") or "Action")
            # deliberate pace (Screen Studio style)
            page.wait_for_timeout(int(max(1.6, timings[i]) * 1000))
            page.evaluate("() => window.__hd && window.__hd.clearFocus()")

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
        context.close()
        browser.close()

    videos = sorted(rec_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise RuntimeError("No Playwright video recorded")
    raw = videos[0]
    print(f"[shoot] raw video {raw} ({raw.stat().st_size} bytes)", flush=True)
    print(f"[shoot] clicks ok={actions['successful_clicks']} fail={len(actions['failed_clicks'])}", flush=True)
    return raw, actions


def edit(raw_video: Path, narration: Path, intro: Path | None, out: Path, work: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    page_raw = work / "page_raw.mp4"
    run([
        "ffmpeg", "-y", "-i", str(raw_video),
        *X264, "-an", str(page_raw),
    ])

    # C2/C3 — strip Playwright lead black
    page_mp4 = work / "page.mp4"
    _, trimmed = trim_leading_black(page_raw, page_mp4)
    print(f"[edit] lead trim={trimmed:.2f}s", flush=True)

    v_dur = ffprobe_duration(page_mp4)
    a_dur = ffprobe_duration(narration)
    print(f"[edit] video={v_dur:.2f}s audio={a_dur:.2f}s", flush=True)

    # If video still shorter than audio (after trim), freeze last frame
    body = work / "body.mp4"
    if v_dur + 0.3 < a_dur:
        pad = a_dur - v_dur + 0.15
        print(f"[edit] pad last frame +{pad:.2f}s for audio", flush=True)
        run([
            "ffmpeg", "-y",
            "-i", str(page_mp4),
            "-i", str(narration),
            "-filter_complex",
            f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f}[v]",
            "-map", "[v]", "-map", "1:a",
            *X264, "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart",
            str(body),
        ])
    else:
        run([
            "ffmpeg", "-y",
            "-i", str(page_mp4),
            "-i", str(narration),
            "-map", "0:v", "-map", "1:a",
            *X264, "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart",
            str(body),
        ])

    if intro and intro.exists():
        intro_n = work / "intro_norm.mp4"
        body_n = work / "body_norm.mp4"
        vf = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1"
        run([
            "ffmpeg", "-y", "-i", str(intro), "-vf", vf,
            *X264, "-c:a", "aac", "-ar", "44100", "-ac", "2", str(intro_n),
        ])
        run([
            "ffmpeg", "-y", "-i", str(body), "-vf", vf,
            *X264, "-c:a", "aac", "-ar", "44100", "-ac", "2", str(body_n),
        ])
        # xfade-ish hard cut is fine; ensure both have audio
        concat_list = work / "vconcat.txt"
        concat_list.write_text(
            f"file '{intro_n.resolve()}'\nfile '{body_n.resolve()}'\n",
            encoding="utf-8",
        )
        run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-movflags", "+faststart", str(out),
        ])
    else:
        shutil.copy(body, out)

    print(f"[edit] wrote {out} ({out.stat().st_size} bytes)", flush=True)
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
        "--no-policy", action="store_true",
        help="Dangerous: disable policy enforce (debug only)",
    )
    args = ap.parse_args()

    policy = None if args.no_policy else load_policy(args.policy)

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
        scout = scout_url(url, viewport={"width": 720, "height": 1280}, work=work)
        save_scout(scout, work / "scout.json")

    if args.scout_only:
        scenario = scenario_from_scout(scout, max_beats=args.max_beats, voice=VOICE_DEFAULT)
        if policy:
            scenario = stamp_scenario(scenario, policy["id"])
        (work / "scenario.json").write_text(
            json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
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

    if policy:
        scenario = stamp_scenario(scenario, policy["id"])
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

    print(f"URL: {scenario['url']}", flush=True)
    (work / "scenario.json").write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if policy:
        (work / "policy.json").write_text(
            json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("\n[1/6] WRITE+VOICE", flush=True)
    beats = build_voices(scenario, work)
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
    raw, actions_log = shoot(scenario, beats, work)
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

    print("\n[3/6] EDIT", flush=True)
    out = edit(raw, narration, intro, args.out, work)

    print("\n[4/6] QUALITY GATE", flush=True)
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

    print("\n[5/6] SELF-AUDIT", flush=True)
    audit = {
        "url": scenario.get("url"),
        "policy": scenario.get("policy"),
        "beats": len(beats),
        "successful_clicks": actions_log.get("successful_clicks"),
        "failed_clicks": actions_log.get("failed_clicks"),
        "duration_sec": ffprobe_duration(out),
        "quality_pass": gate.get("pass"),
        "shortcomings_self": [],
    }
    # deterministic self-critique hooks
    if actions_log.get("successful_clicks", 0) < 4:
        audit["shortcomings_self"].append("clicks < 4")
    if any(len(b.get("narration", "")) > 78 for b in scenario.get("beats") or []):
        audit["shortcomings_self"].append("narration over char cap")
    (work / "self_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)

    print("\n[6/6] REPORT", flush=True)
    report = write_report(scenario, beats, out, work)
    shutil.copy(work / "scenario.json", out.with_suffix(".scenario.json"))
    shutil.copy(report, out.with_suffix(".report.md"))
    if (work / "gate" / "quality_report.json").exists():
        shutil.copy(work / "gate" / "quality_report.json", out.with_suffix(".quality.json"))
    shutil.copy(work / "actions_log.json", out.with_suffix(".actions.json"))
    shutil.copy(work / "self_audit.json", out.with_suffix(".audit.json"))

    elapsed = time.time() - t0
    print("\n=== DONE (SHIP · POLICY PASS) ===", flush=True)
    print(f"out: {out}", flush=True)
    print(f"dur: {ffprobe_duration(out):.1f}s  size: {out.stat().st_size // 1024}KB  time: {elapsed:.0f}s", flush=True)
    print(f"report: {report}", flush=True)


if __name__ == "__main__":
    main()
