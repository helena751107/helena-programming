#!/usr/bin/env python3
"""
Director Agent — URL → scripted tour video (Writer + Director + Camera + Voice + Edit)

Usage:
  python3 run_director.py --scenario scenarios/helena_phone.json
  python3 run_director.py --url https://example.com --out out/demo.mp4

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

DIR = Path(__file__).resolve().parent
DEFAULT_OUT = DIR / "out" / "director_out.mp4"
VOICE_DEFAULT = "ko-KR-SunHiNeural"


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


async def tts_beat(text: str, voice: str, dest: Path) -> float:
    import edge_tts
    dest.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(dest))
    if dest.stat().st_size < 100:
        raise RuntimeError(f"TTS empty: {dest}")
    return ffprobe_duration(dest)


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
    """Concat per-beat mp3 with short silence pads using ffmpeg."""
    voice_dir = work / "voice"
    list_file = work / "audio_concat.txt"
    silence = work / "silence_200ms.mp3"
    # 0.2s silence generator
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", "0.2", "-q:a", "9", "-acodec", "libmp3lame", str(silence),
    ])
    lines = []
    for i, b in enumerate(beats):
        lines.append(f"file '{Path(b['voice_path']).resolve()}'")
        # pad silence proportional to hold (min 1 chunk)
        n = max(1, int(round(b.get("pad_sec", 0.4) / 0.2)))
        for _ in range(n):
            lines.append(f"file '{silence.resolve()}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = work / "narration.mp3"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(out),
    ])
    return out


def make_intro_card(work: Path, title: str, subtitle: str, seconds: float = 2.5) -> Path:
    """Simple branded title card (no external assets)."""
    out = work / "intro_card.mp4"
    # escape for drawtext
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    # Use Korean-capable font if present
    font_candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font = next((f for f in font_candidates if Path(f).exists()), None)
    font_opt = f":fontfile={font}" if font else ""

    vf = (
        f"drawtext=text='{esc(title)}'{font_opt}:fontsize=42:fontcolor=0xF4EFE6:"
        f"x=(w-text_w)/2:y=(h/2)-40,"
        f"drawtext=text='{esc(subtitle)}'{font_opt}:fontsize=22:fontcolor=0x3DB8A8:"
        f"x=(w-text_w)/2:y=(h/2)+20"
    )
    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0A0908:s=720x1280:d={seconds}",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", vf,
        "-t", str(seconds),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "aac", "-shortest",
        str(out),
    ])
    return out


def shoot(scenario: dict, beats: list[dict], work: Path) -> Path:
    from playwright.sync_api import sync_playwright

    vp = scenario.get("viewport") or {"width": 720, "height": 1280}
    url = scenario["url"]
    rec_dir = work / "record"
    if rec_dir.exists():
        shutil.rmtree(rec_dir)
    rec_dir.mkdir(parents=True)

    # Precompute per-beat on-screen times (audio + pad)
    timings = []
    for b in beats:
        timings.append(b["audio_sec"] + b.get("pad_sec", 0.4))

    print(f"[shoot] open {url}", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--hide-scrollbars",
            ],
        )
        context = browser.new_context(
            viewport={"width": int(vp["width"]), "height": int(vp["height"])},
            device_scale_factor=1,
            record_video_dir=str(rec_dir),
            record_video_size={"width": int(vp["width"]), "height": int(vp["height"])},
            color_scheme="dark",
            locale="ko-KR",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(2000)
        # hide custom cursor if any
        page.add_style_tag(content="""
          .cursor,.cursor-dot{display:none!important}
          body{cursor:auto!important}
          html{scroll-behavior:auto!important}
        """)
        # expand all chapters if toolbar exists
        for sel in ("#accExpand", "button:has-text('Expand')", "button:has-text('펼치')"):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=2000)
                    page.wait_for_timeout(600)
                    break
            except Exception:
                pass

        def smooth_scroll_to(selector: str, steps: int = 12):
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
            page.wait_for_timeout(350)

        def try_clicks(clicks: list):
            for c in clicks or []:
                sel = c.get("selector")
                optional = c.get("optional", True)
                if not sel:
                    continue
                # try comma-separated selectors
                ok = False
                for part in [s.strip() for s in sel.split(",")]:
                    try:
                        loc = page.locator(part).first
                        if loc.count() == 0:
                            continue
                        loc.scroll_into_view_if_needed(timeout=2000)
                        loc.click(timeout=2500, force=True)
                        page.wait_for_timeout(450)
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
                page.evaluate("window.scrollTo(0,0)")
                page.wait_for_timeout(400)
            elif action == "scroll_to" and cam.get("selector"):
                smooth_scroll_to(cam["selector"])
            try_clicks(b.get("clicks") or [])
            # hold for narration length
            page.wait_for_timeout(int(timings[i] * 1000))

        page.wait_for_timeout(500)
        context.close()
        browser.close()

    videos = list(rec_dir.glob("*.webm"))
    if not videos:
        raise RuntimeError("No Playwright video recorded")
    # newest / only
    videos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    raw = videos[0]
    print(f"[shoot] raw video {raw} ({raw.stat().st_size} bytes)", flush=True)
    return raw


def edit(raw_video: Path, narration: Path, intro: Path | None, out: Path, work: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    # re-encode page video to mp4
    page_mp4 = work / "page.mp4"
    run([
        "ffmpeg", "-y", "-i", str(raw_video),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "28",
        "-an",
        str(page_mp4),
    ])
    v_dur = ffprobe_duration(page_mp4)
    a_dur = ffprobe_duration(narration)
    print(f"[edit] video={v_dur:.2f}s audio={a_dur:.2f}s", flush=True)

    # mux page + narration (shortest)
    body = work / "body.mp4"
    run([
        "ffmpeg", "-y",
        "-i", str(page_mp4),
        "-i", str(narration),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(body),
    ])

    if intro and intro.exists():
        # scale intro to same size and concat
        intro_n = work / "intro_norm.mp4"
        run([
            "ffmpeg", "-y", "-i", str(intro),
            "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "28",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            str(intro_n),
        ])
        body_n = work / "body_norm.mp4"
        run([
            "ffmpeg", "-y", "-i", str(body),
            "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "28",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            str(body_n),
        ])
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
    args = ap.parse_args()

    scenario = load_scenario(args.scenario, args.url)
    work = args.work or (DIR / "out" / f"work_{scenario.get('id', 'run')}")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    # save scenario snapshot
    (work / "scenario.json").write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    t0 = time.time()
    print("=== Director Agent ===", flush=True)
    print(f"URL: {scenario['url']}", flush=True)

    print("\n[1/4] WRITE+VOICE", flush=True)
    beats = build_voices(scenario, work)
    narration = concat_audio(beats, work)
    print(f"narration total {ffprobe_duration(narration):.1f}s", flush=True)

    intro = None
    if not args.skip_intro:
        print("\n[1b] INTRO CARD", flush=True)
        intro = make_intro_card(
            work,
            scenario.get("title") or "Helena",
            scenario.get("logline") or scenario.get("url", "")[:48],
            2.4,
        )

    print("\n[2/4] SHOOT", flush=True)
    raw = shoot(scenario, beats, work)

    print("\n[3/4] EDIT", flush=True)
    out = edit(raw, narration, intro, args.out, work)

    print("\n[4/4] REPORT", flush=True)
    report = write_report(scenario, beats, out, work)
    # copy scenario next to out
    shutil.copy(work / "scenario.json", out.with_suffix(".scenario.json"))
    shutil.copy(report, out.with_suffix(".report.md"))

    elapsed = time.time() - t0
    print("\n=== DONE ===", flush=True)
    print(f"out: {out}", flush=True)
    print(f"dur: {ffprobe_duration(out):.1f}s  size: {out.stat().st_size // 1024}KB  time: {elapsed:.0f}s", flush=True)
    print(f"report: {report}", flush=True)


if __name__ == "__main__":
    main()
