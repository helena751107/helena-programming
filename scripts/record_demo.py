#!/usr/bin/env python3
"""
record_demo.py — Playwright recordVideo로 인터랙티브 튜토리얼 영상 제작
==========================================================================
make_page.py로 생성한 HTML을 Playwright가 직접 조작하며 녹화.
아코디언·네비게이션·TTS·스크롤 등 모든 동적 요소가 영상에 담긴다.

사용: python3 scripts/record_demo.py 문서.md
"""

import os, sys, time, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from make_page import parse_markdown_full, group_sections, generate_html


def record_demo(source: str, output: str = None, width=720, height=1280):
    from playwright.sync_api import sync_playwright

    # 1. HTML 생성
    text = Path(source).read_text(encoding="utf-8", errors="replace")
    blocks = parse_markdown_full(text)
    sections = group_sections(blocks)
    sections = sections[:8]
    if not sections: print("❌ 섹션 없음"); return
    title = sections[0]["title"] if sections else Path(source).stem
    html = generate_html(sections, title)

    html_path = f"/tmp/_demo_{os.getpid()}.html"
    Path(html_path).write_text(html, encoding="utf-8")
    print(f"🌐 {len(sections)}섹션 HTML → {html_path}")

    # 2. Playwright recordVideo
    video_dir = "/tmp/"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=video_dir,
            record_video_size={"width": width, "height": height}
        )
        page = context.new_page()

        print("🎬 녹화 시작...")
        page.goto(f"file://{html_path}", timeout=30000)
        # 페이지 완전 로딩 대기 (Mermaid, fonts)
        page.wait_for_timeout(4000)

        # ── 씬 1: 전체 페이지 훑기 (3초) ──
        print("  📸 씬1: 첫 페이지")
        page.wait_for_timeout(2000)

        # ── 씬 2: 아코디언 열기 ──
        print("  🖱️ 씬2: 아코디언 클릭")
        accordions = page.query_selector_all('.accordion-header')
        for i, acc in enumerate(accordions[:2]):
            try:
                acc.click()
                page.wait_for_timeout(1000)
            except Exception as e:
                print(f"    ⚠️ {e}")

        # ── 씬 3: 네비게이션 닷으로 섹션 이동 ──
        print("  🔘 씬3: 네비게이션")
        dots = page.query_selector_all('.nav-dot')
        for i in [1, 3, 5]:
            if i < len(dots):
                try:
                    dots[i].click()
                    page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"    ⚠️ {e}")

        # ── 씬 4: Play All (TTS 켜고 몇 초 후 정지) ──
        print("  🔊 씬4: Play All → TTS → Stop")
        play_btn = page.query_selector('#playBtn')
        if play_btn:
            play_btn.click()
            page.wait_for_timeout(6000)
            try:
                play_btn.click()  # Stop
            except:
                pass
            page.wait_for_timeout(1000)

        # ── 씬 5: 마지막 섹션까지 스크롤 ──
        print("  📜 씬5: 마지막 섹션")
        last_dot = page.query_selector_all('.nav-dot')
        if last_dot:
            try:
                last_dot[-1].click()
            except:
                pass
        page.wait_for_timeout(3000)

        # 종료
        context.close()
        browser.close()

    # 비디오 찾기
    import glob
    videos = sorted(glob.glob(f"{video_dir}/*.webm"), key=os.path.getctime)
    if not videos:
        print("❌ 녹화 파일 없음"); return None

    latest = videos[-1]
    out = output or f"/tmp/{Path(source).stem}_demo.webm"
    if latest != out:
        os.rename(latest, out)

    size_mb = os.path.getsize(out) / (1024*1024)
    print(f"\n✅ {out}")
    print(f"   📦 {size_mb:.1f}MB · 🎬 {len(sections)}섹션 인터랙티브 데모")
    print(f"   🖱️ 아코디언 · 네비닷 · Play All · 스크롤 전부 녹화됨")

    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Playwright recordVideo → 인터랙티브 튜토리얼 MP4")
    ap.add_argument("source", help=".md 파일")
    ap.add_argument("--output", "-o")
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    args = ap.parse_args()
    record_demo(args.source, args.output, args.width, args.height)
