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
X264 = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20"]


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


def shoot(scenario: dict, beats: list[dict], work: Path) -> Path:
    """
    Two-phase shoot (pro):
      1) Warm context — load & ready WITHOUT counting as final (still recorded
         but we trim black in edit). Maximize first-paint before tour.
      2) Tour with timed holds matching narration.
    """
    from playwright.sync_api import sync_playwright

    vp = scenario.get("viewport") or {"width": 720, "height": 1280}
    w, h = int(vp["width"]), int(vp["height"])
    url = scenario["url"]
    rec_dir = work / "record"
    if rec_dir.exists():
        shutil.rmtree(rec_dir)
    rec_dir.mkdir(parents=True)

    timings = [b["audio_sec"] + b.get("pad_sec", 0.4) for b in beats]
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
            # reduce blank: start with dark
            reduced_motion="reduce",
        )
        page = context.new_page()
        # seed dark blank
        page.set_content(
            "<!doctype html><html><body style='margin:0;background:#0a0908;width:100vw;height:100vh'></body></html>"
        )
        page.wait_for_timeout(150)

        _wait_page_ready(page, url)
        print("  page ready", flush=True)

        # settle frame for first keyframe (anti-black head)
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(800)

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
                    page.wait_for_timeout(700)
                    print(f"  expand via {sel}", flush=True)
                    break
            except Exception:
                pass

        def smooth_scroll_to(selector: str, steps: int = 16):
            try:
                page.wait_for_selector(selector, timeout=8000)
            except Exception:
                print(f"  ! missing selector {selector}", flush=True)
                return
            page.evaluate(
                """([sel, steps]) => {
                  const el = document.querySelector(sel);
                  if (!el) return;
                  const target = el.getBoundingClientRect().top + window.scrollY - 72;
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
            page.wait_for_timeout(400)

        def try_clicks(clicks: list):
            for c in clicks or []:
                sel = c.get("selector")
                optional = c.get("optional", True)
                if not sel:
                    continue
                ok = False
                for part in [s.strip() for s in sel.split(",")]:
                    try:
                        loc = page.locator(part).first
                        if loc.count() == 0:
                            continue
                        loc.scroll_into_view_if_needed(timeout=2000)
                        # accordion: click head even if expanded toggle
                        loc.click(timeout=2500, force=True)
                        page.wait_for_timeout(500)
                        ok = True
                        print(f"  click {part}", flush=True)
                        break
                    except Exception as e:
                        if not optional:
                            print(f"  click fail {part}: {e}", flush=True)
                if not ok and not optional:
                    print(f"  ! no click matched: {sel}", flush=True)

        for i, b in enumerate(beats):
            cam = b.get("camera") or {}
            action = cam.get("action", "scroll_to")
            print(f"[shoot] beat {b['id']} action={action} hold={timings[i]:.1f}s", flush=True)
            if action == "goto_top":
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                page.wait_for_timeout(500)
            elif action == "scroll_to" and cam.get("selector"):
                smooth_scroll_to(cam["selector"])
            try_clicks(b.get("clicks") or [])
            # hold for narration — min 1.2s visual settle
            page.wait_for_timeout(int(max(1.2, timings[i]) * 1000))

        page.wait_for_timeout(600)
        context.close()
        browser.close()

    videos = sorted(rec_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise RuntimeError("No Playwright video recorded")
    raw = videos[0]
    print(f"[shoot] raw video {raw} ({raw.stat().st_size} bytes)", flush=True)
    return raw


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
    ap.add_argument("--max-beats", type=int, default=7)
    args = ap.parse_args()

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
    print("=== Director Agent ===", flush=True)

    # ── 0) SCOUT ──────────────────────────────────────────
    scout = None
    do_scout = args.scout or args.scout_only or (args.url and not args.scenario)
    if do_scout:
        print("\n[0/5] SCOUT — parse page structure", flush=True)
        scout = scout_url(url, viewport={"width": 720, "height": 1280}, work=work)
        save_scout(scout, work / "scout.json")

    if args.scout_only:
        scenario = scenario_from_scout(scout, max_beats=args.max_beats, voice=VOICE_DEFAULT)
        (work / "scenario.json").write_text(
            json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # also export under scenarios/
        export = DIR / "scenarios" / f"{scenario['id']}_from_scout.json"
        export.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[scout-only] scenario → {work / 'scenario.json'}", flush=True)
        print(f"[scout-only] export  → {export}", flush=True)
        print(json.dumps({
            "sections": scout.get("section_count"),
            "interactives": scout.get("interactive_count"),
            "beats": len(scenario["beats"]),
            "title": scenario.get("title"),
        }, ensure_ascii=False, indent=2))
        return

    # load or build scenario
    if args.scenario:
        scenario = load_scenario(args.scenario, args.url or url)
        if scout:
            print("[scout] merge selectors into hand scenario", flush=True)
            scenario = merge_scenario_with_scout(scenario, scout)
    else:
        # URL-only path: scenario entirely from scout
        if not scout:
            scout = scout_url(url, work=work)
            save_scout(scout, work / "scout.json")
        scenario = scenario_from_scout(scout, max_beats=args.max_beats, voice=VOICE_DEFAULT)

    print(f"URL: {scenario['url']}", flush=True)
    (work / "scenario.json").write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n[1/5] WRITE+VOICE", flush=True)
    beats = build_voices(scenario, work)
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
            seconds=2.2,
            kicker="Director · Scout → Shoot",
        )
        intro_png = work / "intro.png"

    print("\n[2/5] SHOOT", flush=True)
    raw = shoot(scenario, beats, work)

    print("\n[3/5] EDIT", flush=True)
    out = edit(raw, narration, intro, args.out, work)

    print("\n[4/5] QUALITY GATE", flush=True)
    gate = gate_output(out, work=work / "gate", intro_png=intro_png)
    if not gate.get("pass"):
        print("QUALITY GATE FAILED — refuse to treat as shippable", flush=True)
        # still write report for debug
        write_report(scenario, beats, out, work)
        shutil.copy(work / "scenario.json", out.with_suffix(".scenario.json"))
        sys.exit(2)

    print("\n[5/5] REPORT", flush=True)
    report = write_report(scenario, beats, out, work)
    shutil.copy(work / "scenario.json", out.with_suffix(".scenario.json"))
    shutil.copy(report, out.with_suffix(".report.md"))
    if (work / "gate" / "quality_report.json").exists():
        shutil.copy(work / "gate" / "quality_report.json", out.with_suffix(".quality.json"))

    elapsed = time.time() - t0
    print("\n=== DONE (SHIP) ===", flush=True)
    print(f"out: {out}", flush=True)
    print(f"dur: {ffprobe_duration(out):.1f}s  size: {out.stat().st_size // 1024}KB  time: {elapsed:.0f}s", flush=True)
    print(f"report: {report}", flush=True)


if __name__ == "__main__":
    main()
