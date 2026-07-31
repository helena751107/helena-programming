#!/usr/bin/env python3
"""
demo_director.py — 자동 씬연출+TTS동기화+클릭+스크롤 데모 녹화
==================================================================
1. 페이지 분석 → 헤딩·아코디언·버튼 자동 감지
2. 각 요소에 맞는 TTS 내레이션 생성 + 길이 측정
3. Playwright recordVideo로 TTS 길이에 맞춰 스크롤·클릭 연출
4. TTS 오디오 믹스 → 최종 MP4
"""

import asyncio, edge_tts, os, sys, subprocess, tempfile, glob, time, threading
from playwright.sync_api import sync_playwright


# ── 1단계: 페이지 분석 (sync) ──
def analyze_page(url: str, width=390, height=844):
    """Playwright로 페이지 열고 헤딩·클릭요소 찾기"""
    result = {"total_h": 0, "headings": [], "clickables": [], "text": ""}

    def _run():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)

            result["total_h"] = page.evaluate("document.body.scrollHeight")
            result["text"] = page.evaluate("document.body.innerText") or ""

            # 헤딩
            result["headings"] = page.evaluate("""() => {
                const hs = document.querySelectorAll('h1,h2,h3,[class*=title],[class*=heading],[class*=hero]');
                return Array.from(hs).map(h => ({
                    tag: h.tagName, text: (h.textContent||'').trim().substring(0,100),
                    y: Math.max(0, h.getBoundingClientRect().top + window.scrollY - 100)
                })).filter(h => h.text.length > 3);
            }""")

            # 클릭 가능 요소
            result["clickables"] = page.evaluate("""() => {
                const els = document.querySelectorAll(
                    'details,summary,[class*=accordion],[class*=toggle],[class*=collapse],' +
                    'button:not([type=submit]),[class*=nav-dot],a[href^="#"]'
                );
                return Array.from(els).map(e => {
                    let sel = e.tagName.toLowerCase();
                    if (e.className && typeof e.className === 'string') {
                        sel = e.className.split(' ')[0];
                    }
                    if (e.id) sel = '#' + e.id;
                    return {
                        tag: e.tagName, text: (e.textContent||'').trim().substring(0,50),
                        y: e.getBoundingClientRect().top + window.scrollY,
                        selector: sel
                    };
                }).filter(c => c.text.length > 0);
            }""")

            browser.close()

    t = threading.Thread(target=_run); t.start(); t.join()
    return result


# ── 2단계: TTS 생성 (async) ──
async def generate_scenes(page_data: dict, workdir: str) -> list:
    """페이지 분석 → 씬 구성 + TTS 생성"""
    scenes = []
    headings = page_data["headings"]
    clickables = page_data["clickables"]
    total_h = page_data["total_h"]
    text = page_data["text"]

    # 페이지 제목 추출
    title = headings[0]["text"] if headings else "페이지"

    # 씬1: 인트로
    scenes.append({
        "narration": f"안녕하세요. {title} 페이지를 지금부터 둘러보겠습니다.",
        "actions": [{"type": "scroll", "y": 0}, {"type": "wait", "ms": 500}]
    })

    # 헤딩 기반 씬
    used_clickables = set()
    for i, h in enumerate(headings[:8]):
        y = max(0, h["y"] - 80)

        # 이 섹션 근처 아코디언/버튼 찾기
        nearby_click = None
        for c in clickables:
            cid = f"{c['y']}_{c['text']}"
            if cid in used_clickables: continue
            if abs(c["y"] - h["y"]) < 500 and c["tag"] in ("SUMMARY", "DETAILS"):
                nearby_click = c
                used_clickables.add(cid)
                break

        actions = [{"type": "smooth_scroll", "y": y, "step_ms": 40}, {"type": "wait", "ms": 200}]

        if nearby_click:
            narration = f"{h['text']}. 여기를 클릭해서 펼쳐보겠습니다."
            actions.append({"type": "click", "selector": nearby_click["selector"]})
            actions.append({"type": "wait", "ms": 600})
        else:
            narration = h["text"]

        scenes.append({"narration": narration, "actions": actions})

    # 마지막 씬: 끝까지
    scenes.append({
        "narration": "이상으로 페이지 소개를 마치겠습니다.",
        "actions": [
            {"type": "smooth_scroll", "y": max(0, total_h - 844), "step_ms": 50},
            {"type": "wait", "ms": 1500}
        ]
    })

    # TTS 생성 + 길이 측정
    print("🔊 TTS 생성 중...")
    for i, s in enumerate(scenes):
        mp3 = os.path.join(workdir, f"s{i:03d}.mp3")
        comm = edge_tts.Communicate(s["narration"][:3000], "ko-KR-SunHiNeural", rate="+8%")
        await comm.save(mp3)
        dur = float(subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",mp3],
            capture_output=True, text=True
        ).stdout.strip() or 5)
        s["tts_file"] = mp3
        s["tts_dur"] = dur
        print(f"  🎙️ 씬{i+1}: {dur:.1f}초 — {s['narration'][:55]}")

    return scenes


# ── 3단계: 녹화 (sync) ──
def record_scenes(url: str, scenes: list, output_dir: str, width=390, height=844):
    """TTS 길이에 맞춰 Playwright로 연출하며 녹화"""
    raw_video = os.path.join(output_dir, "raw.webm")

    def _run():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": width, "height": height},
                record_video_dir=output_dir,
                record_video_size={"width": width, "height": height}
            )
            page = context.new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)

            total_h = page.evaluate("document.body.scrollHeight")

            for i, scene in enumerate(scenes):
                dur = scene["tts_dur"]
                print(f"  🎬 씬{i+1}/{len(scenes)} ({dur:.1f}초)")
                start = time.time()

                for action in scene.get("actions", []):
                    elapsed = time.time() - start
                    if elapsed >= dur: break

                    atype = action["type"]
                    if atype == "scroll":
                        page.evaluate(f"window.scrollTo({{top:{min(action['y'],total_h-height)},behavior:'smooth'}})")
                    elif atype == "click":
                        try:
                            sel = action["selector"]
                            el = page.query_selector(sel)
                            if el:
                                el.click()
                                page.wait_for_timeout(400)
                        except: pass
                    elif atype == "wait":
                        page.wait_for_timeout(min(action["ms"], int((dur - elapsed)*1000)))
                    elif atype == "smooth_scroll":
                        target = min(action["y"], total_h - height)
                        current = page.evaluate("window.scrollY")
                        steps = 50
                        step_ms = int(action.get("step_ms", 50))
                        for s in range(steps):
                            y = current + (target - current) * (s / steps)
                            page.evaluate(f"window.scrollTo({{top:{y},behavior:'auto'}})")
                            page.wait_for_timeout(step_ms)

                # 남은 시간 자연스럽게 채우기
                remaining = dur - (time.time() - start)
                if remaining > 0.3:
                    current_y = page.evaluate("window.scrollY")
                    target_y = min(current_y + 150, total_h - height)
                    steps = max(1, int(remaining * 1000 / 60))
                    for s in range(steps):
                        y = current_y + (target_y - current_y) * (s / steps)
                        page.evaluate(f"window.scrollTo({{top:{y},behavior:'auto'}})")
                        page.wait_for_timeout(60)

            page.wait_for_timeout(1000)
            context.close()
            browser.close()

    t = threading.Thread(target=_run); t.start(); t.join()

    # 녹화 파일 찾기
    videos = sorted(glob.glob(f"{output_dir}/*.webm"), key=os.path.getctime)
    return videos[-1] if videos else None


# ── 4단계: 오디오 믹스 ──
def mix_audio(scenes: list, video_path: str, output: str):
    """TTS 파일들 이어붙여서 비디오에 믹스"""
    concat_list = os.path.join(os.path.dirname(output), "tts_list.txt")
    with open(concat_list, "w") as f:
        for s in scenes:
            f.write(f"file '{s['tts_file']}'\n")

    merged = os.path.join(os.path.dirname(output), "merged.mp3")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",concat_list,
                    "-c","copy",merged], capture_output=True, check=True)

    subprocess.run(["ffmpeg","-y","-i",video_path,"-i",merged,
                    "-c:v","libx264","-c:a","aac","-b:a","192k",
                    "-pix_fmt","yuv420p","-shortest",output],
                   capture_output=True, check=True)
    return output


# ── 메인 ──
async def main():
    import argparse
    ap = argparse.ArgumentParser(description="자동 페이지 데모 녹화")
    ap.add_argument("url")
    ap.add_argument("--output","-o",default="/tmp/demo_directed.mp4")
    ap.add_argument("--width",type=int,default=390)
    ap.add_argument("--height",type=int,default=844)
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="demo_")

    print(f"📖 {args.url}")
    page_data = analyze_page(args.url, args.width, args.height)
    print(f"📏 {page_data['total_h']}px · 제목 {len(page_data['headings'])}개 · 클릭요소 {len(page_data['clickables'])}개")

    scenes = await generate_scenes(page_data, work)
    total_dur = sum(s["tts_dur"] for s in scenes)
    print(f"\n⏱ 전체 {total_dur:.0f}초 · {len(scenes)}씬")

    print("🎬 녹화...")
    raw = record_scenes(args.url, scenes, work, args.width, args.height)
    if not raw: print("❌ 녹화 실패"); return
    print(f"🎥 {os.path.getsize(raw)//1024}KB")

    print("🔗 오디오 믹스...")
    final = mix_audio(scenes, raw, args.output)

    size_mb = os.path.getsize(final)/(1024*1024)
    print(f"\n✅ {final}")
    print(f"   📦 {size_mb:.1f}MB · ⏱ {total_dur:.0f}초 · 🎬 {len(scenes)}씬")


if __name__ == "__main__":
    asyncio.run(main())
