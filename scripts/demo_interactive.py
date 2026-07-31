#!/usr/bin/env python3
"""
demo_interactive.py — 인터랙티브 페이지를 Playwright로 클릭 연출 → MP4
========================================================================
make_page.py로 생성한 HTML을 Playwright가 실제로 열고,
섹션별로 넘기며 스크린샷 → Edge TTS → FFmpeg → 시연 영상.

사용: python3 scripts/demo_interactive.py 문서.md
"""

import os, sys, asyncio, subprocess, tempfile, threading, time, json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from make_page import parse_markdown_full, group_sections
from webpage_to_video import tts, frame_to_clip, concat_clips


def capture_section_html(html_path: str, section_idx: int, output_png: str,
                         width=720, height=1280):
    """Playwright로 HTML 열고 특정 섹션으로 이동 후 스크린샷"""
    from playwright.sync_api import sync_playwright

    def _run():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"file://{html_path}", timeout=15000)
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(2000)

            # 해당 섹션으로 스크롤
            slides = page.query_selector_all('.slide')
            if section_idx < len(slides):
                slides[section_idx].scroll_into_view_if_needed()
            page.wait_for_timeout(800)

            # 전체 페이지 스크린샷
            page.screenshot(path=output_png, full_page=False)
            browser.close()

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    return output_png


async def main(source: str, voice="ko-KR-SunHiNeural", output=None):
    # 1. 마크다운 → 섹션 데이터
    text = Path(source).read_text(encoding="utf-8", errors="replace")
    blocks = parse_markdown_full(text)
    sections = group_sections(blocks)
    sections = sections[:8]

    if not sections:
        print("❌ 섹션 없음"); return

    print(f"📝 {len(sections)}섹션")

    # 2. 인터랙티브 HTML 생성
    from make_page import generate_html
    title = sections[0]["title"] if sections else Path(source).stem
    html_content = generate_html(sections, title)

    html_path = os.path.join(tempfile.mkdtemp(prefix="hdemo_"), "page.html")
    Path(html_path).write_text(html_content, encoding="utf-8")
    print(f"🌐 HTML: {html_path}")

    # 3. 각 섹션 Playwright 캡처 + TTS → 클립
    work = tempfile.mkdtemp(prefix="hclip_")
    clips = []

    for i, sec in enumerate(sections):
        print(f"  🎬 [{i+1}/{len(sections)}] {sec['title'][:40]}")

        # Playwright로 해당 섹션 캡처
        png = os.path.join(work, f"s{i:03d}.png")
        capture_section_html(html_path, i, png)
        print(f"     📸 {os.path.getsize(png)//1024}KB")

        # TTS 텍스트 구성
        tts_text = sec["title"]
        for b in sec["blocks"]:
            if b["type"] == "p":
                tts_text += ". " + b["content"][:300]
            elif b["type"] == "list":
                tts_text += ". " + ". ".join(b["content"][:3])
        tts_text = tts_text[:2000]

        mp3 = os.path.join(work, f"a{i:03d}.mp3")
        await tts(tts_text, voice, mp3)
        print(f"     🔊 {os.path.getsize(mp3)//1024}KB")

        clip = os.path.join(work, f"c{i:03d}.mp4")
        frame_to_clip(png, mp3, clip)
        print(f"     🎥 {os.path.getsize(clip)//1024}KB")
        clips.append(clip)

    # 4. 이어붙이기
    if not output:
        output = f"/tmp/{Path(source).stem}_demo.mp4"

    print(f"\n🔗 {len(clips)}클립 이어붙이기...")
    concat_clips(clips, output)

    size_mb = os.path.getsize(output) / (1024 * 1024)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", output], capture_output=True, text=True
    ).stdout.strip() or 0)

    print(f"\n✅ {output}")
    print(f"   📦 {size_mb:.1f}MB · ⏱ {dur/60:.1f}분 · 🎬 {len(clips)}섹션")
    return output


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural")
    ap.add_argument("--output", "-o")
    args = ap.parse_args()
    asyncio.run(main(args.source, args.voice, args.output))
