#!/usr/bin/env python3
"""Pro intro card — HTML + Playwright screenshot + ffmpeg (CJK-safe)."""
from __future__ import annotations

import html
import subprocess
from pathlib import Path

CJK_FONT_STACK = (
    "'Noto Sans CJK KR', 'Noto Sans CJK', 'WenQuanYi Zen Hei', "
    "'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif"
)

INTRO_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @font-face {{
    font-family: 'NotoSansLocal';
    src: local('Noto Sans CJK KR'), local('Noto Sans CJK'), local('WenQuanYi Zen Hei');
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: {w}px; height: {h}px; overflow: hidden;
    background: #0a0908;
    color: #f4efe6;
    font-family: NotoSansLocal, {stack};
    -webkit-font-smoothing: antialiased;
  }}
  .stage {{
    width: 100%; height: 100%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 48px 40px;
    background:
      radial-gradient(ellipse 80% 50% at 70% 20%, rgba(61,184,168,.18), transparent 55%),
      radial-gradient(ellipse 50% 40% at 15% 85%, rgba(212,168,75,.08), transparent 50%),
      #0a0908;
  }}
  .kicker {{
    font-size: 13px; letter-spacing: .22em; text-transform: uppercase;
    color: #3db8a8; font-weight: 600; margin-bottom: 28px;
  }}
  .title {{
    font-size: 42px; font-weight: 700; text-align: center;
    line-height: 1.15; letter-spacing: -0.02em;
    max-width: 90%; word-break: keep-all;
  }}
  .sub {{
    margin-top: 22px; font-size: 18px; font-weight: 400;
    color: #b5a999; text-align: center; max-width: 88%;
    line-height: 1.45; word-break: keep-all;
    border-left: 2px solid #3db8a8; padding-left: 14px;
  }}
  .dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: #3db8a8; box-shadow: 0 0 14px #3db8a8;
    margin-bottom: 18px;
  }}
</style>
</head>
<body>
  <div class="stage">
    <div class="dot"></div>
    <div class="kicker">{kicker}</div>
    <div class="title">{title}</div>
    <div class="sub">{subtitle}</div>
  </div>
</body>
</html>
"""


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def make_intro_card(
    work: Path,
    title: str,
    subtitle: str,
    *,
    seconds: float = 2.2,
    width: int = 720,
    height: int = 1280,
    kicker: str = "Helena Director · Intro",
) -> Path:
    """Render CJK-safe intro via Chromium paint (not ffmpeg drawtext)."""
    work.mkdir(parents=True, exist_ok=True)
    html_path = work / "intro.html"
    png_path = work / "intro.png"
    out = work / "intro_card.mp4"

    doc = INTRO_HTML.format(
        w=width,
        h=height,
        stack=CJK_FONT_STACK,
        kicker=html.escape(kicker),
        title=html.escape(title or "Helena"),
        subtitle=html.escape((subtitle or "")[:180]),
    )
    html_path.write_text(doc, encoding="utf-8")
    html_path = html_path.resolve()
    png_path = png_path.resolve()
    out = out.resolve()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"],
        )
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
            color_scheme="dark",
            locale="ko-KR",
        )
        page = context.new_page()
        page.goto(html_path.as_uri(), wait_until="load", timeout=60_000)
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(300)
        page.screenshot(path=str(png_path), type="png")
        context.close()
        browser.close()

    if png_path.stat().st_size < 20_000:
        raise RuntimeError(f"Intro screenshot too small/empty: {png_path}")

    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(png_path),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(seconds),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart",
        str(out),
    ])
    print(f"[intro] {out} ({out.stat().st_size} bytes)", flush=True)
    return out
