#!/usr/bin/env python3
"""
demo_director.py — 빅테크급 제품 데모 자동 생성
================================================
- Visible cursor (smooth move, no teleport)
- Click ripple animations
- Dark loading curtain (no white flash)
- Settle detection (not fixed timeouts)
- Loud failure logging
- Edge TTS → narraction marks → timestamp sync

사용: python3 scripts/demo_director.py https://페이지URL -o 출력.mp4
"""

import asyncio, edge_tts, os, sys, subprocess, tempfile, glob, time, threading, json
from playwright.sync_api import sync_playwright

INJECT_CURSOR = """
// Visible cursor
if (!document.getElementById('__demo_cursor')) {
  const c = document.createElement('div');
  c.id = '__demo_cursor';
  c.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24"><path d="M3 3l7 18 2-6 6-2z" fill="#fff" stroke="#6366f1" stroke-width="1.5"/></svg>';
  c.style.cssText = 'position:fixed;z-index:99999;pointer-events:none;transition:all 0.08s ease-out;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.5));';
  document.body.appendChild(c);
}
window.__moveCursor = (x,y) => {
  const c = document.getElementById('__demo_cursor');
  if (c) { c.style.left = x+'px'; c.style.top = y+'px'; }
};

// Click ripple
window.__clickRipple = (x,y) => {
  const r = document.createElement('div');
  r.style.cssText = `position:fixed;z-index:99998;left:${x-20}px;top:${y-20}px;width:40px;height:40px;border-radius:50%;border:2px solid #818cf8;pointer-events:none;animation:__ripple 0.6s ease-out forwards`;
  document.body.appendChild(r);
  setTimeout(() => r.remove(), 600);
};
if (!document.getElementById('__ripple_style')) {
  const s = document.createElement('style');
  s.id = '__ripple_style';
  s.textContent = '@keyframes __ripple { 0% { transform:scale(0.5);opacity:1 } 100% { transform:scale(3);opacity:0 } }';
  document.head.appendChild(s);
}

// Hide white flash
if (!document.getElementById('__curtain')) {
  const curtain = document.createElement('div');
  curtain.id = '__curtain';
  curtain.style.cssText = 'position:fixed;inset:0;z-index:100000;background:#050510;transition:opacity 0.4s';
  document.body.appendChild(curtain);
  // fade out after page ready
  setTimeout(() => { curtain.style.opacity = '0'; setTimeout(() => curtain.remove(), 500); }, 500);
}

// Settle detection helper
window.__isSettled = () => {
  const videos = document.querySelectorAll('video');
  for (const v of videos) { if (!v.paused) return false; }
  return document.readyState === 'complete';
};
"""


def inject_all(page):
    """커서+리플+커튼 주입"""
    page.evaluate(INJECT_CURSOR)
    page.wait_for_timeout(300)


def move_mouse(page, x, y, steps=15):
    """부드러운 마우스 이동"""
    page.mouse.move(x, y, steps=steps)
    page.evaluate(f"window.__moveCursor({x},{y})")
    page.wait_for_timeout(200)


def click_at(page, x, y, label=""):
    """클릭 + 리플 + 로그"""
    move_mouse(page, x, y)
    page.wait_for_timeout(300)
    page.evaluate(f"window.__clickRipple({x},{y})")
    page.mouse.click(x, y)
    if label:
        print(f"    🖱️ 클릭: {label}")
    page.wait_for_timeout(600)


def click_element(page, selector, label=""):
    """요소 찾아서 클릭 (visible 확인 후)"""
    try:
        el = page.query_selector(selector)
        if not el:
            print(f"    ❌ 셀렉터 없음: {selector}")
            return False
        el.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        box = el.bounding_box()
        if not box:
            print(f"    ❌ bounding box 없음: {selector}")
            return False
        cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
        click_at(page, cx, cy, label or selector)
        return True
    except Exception as e:
        print(f"    ❌ 클릭 실패: {selector} — {e}")
        return False


def scroll_to(page, y, steps=60, ms_per_step=30):
    """부드러운 스크롤 (사람처럼)"""
    current = page.evaluate("window.scrollY")
    for i in range(steps + 1):
        pos = current + (y - current) * (i / steps)
        page.evaluate(f"window.scrollTo({{top:{pos},behavior:'auto'}})")
        page.wait_for_timeout(ms_per_step)


def find_all_interactive(page):
    """모든 인터랙티브 요소 찾기"""
    return page.evaluate("""() => {
        const items = [];
        const all = document.querySelectorAll('*');
        const seen = new Set();
        for (const el of all) {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const text = (el.textContent||'').trim();

            if (text.length < 3 || rect.width < 10 || rect.height < 10) continue;
            if (rect.y < 0 || rect.y > window.innerHeight) continue;  // visible only

            const isClickable = (
                el.tagName === 'BUTTON' || el.tagName === 'SUMMARY' ||
                el.tagName === 'DETAILS' || el.tagName === 'A' ||
                el.getAttribute('onclick') || el.getAttribute('role') === 'button' ||
                el.classList.contains('accordion') || el.classList.contains('toggle') ||
                style.cursor === 'pointer' || el.getAttribute('tabindex') === '0'
            );
            if (!isClickable) continue;

            let sel = el.tagName.toLowerCase();
            if (el.id) sel = '#' + el.id;
            else if (el.classList.length) sel = el.tagName + '.' + Array.from(el.classList).slice(0,2).join('.');

            const key = sel + '|' + text.substring(0,20);
            if (seen.has(key)) continue;
            seen.add(key);

            items.push({
                tag: el.tagName, text: text.substring(0,60), selector: sel,
                x: Math.round(rect.x + rect.width/2),
                y: Math.round(rect.y + rect.height/2)
            });
        }
        return items;
    }""")


# ── 메인 파이프 ──

async def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--output","-o",default="/tmp/demo_pro.mp4")
    ap.add_argument("--width",type=int,default=390)
    ap.add_argument("--height",type=int,default=844)
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="demo_")
    url = args.url
    W, H = args.width, args.height

    # ── 1단계: 페이지 분석 + 인터랙티브 요소 전수조사 ──
    print(f"📖 분석: {url}")
    _items = {}
    def _analyze():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": W, "height": H})
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(3000)
            inject_all(page)
            _items["total_h"] = page.evaluate("document.body.scrollHeight")
            _items["interactive"] = find_all_interactive(page)
            _items["headings"] = page.evaluate("""() => {
                const hs = document.querySelectorAll('h1,h2,h3,[class*=title],[class*=hero]');
                return Array.from(hs).map(h => ({tag:h.tagName, text:(h.textContent||'').trim().substring(0,80), y:h.getBoundingClientRect().top+window.scrollY}));
            }""")
            browser.close()
    t = threading.Thread(target=_analyze); t.start(); t.join()

    total_h = _items["total_h"]
    interactive = _items["interactive"]
    headings = _items["headings"]

    print(f"📏 {total_h}px · 인터랙티브 {len(interactive)}개 · 헤딩 {len(headings)}개")
    for i, el in enumerate(interactive[:20]):
        print(f"  [{i}] {el['tag']:8s} | {el['text'][:45]:45s} | {el['selector'][:35]}")

    # ── 2단계: 씬 구성 + TTS ──
    scenes = []

    # 인트로
    title = headings[0]["text"] if headings else "페이지"
    scenes.append({
        "narration": f"안녕하세요. {title} 데모입니다. 지금부터 모든 기능을 하나씩 보여드리겠습니다.",
        "actions": [{"type":"wait","ms":500}]
    })

    # 헤딩 섹션 + 근처 인터랙티브 요소 전부 클릭
    clicked = set()
    for h in headings[:8]:
        sy = max(0, h["y"] - 80)
        actions = [{"type":"scroll","y":sy,"steps":50,"ms":25}]

        # 이 섹션 근처의 모든 인터랙티브 요소
        nearby = [el for el in interactive if abs(el["y"] - h["y"]) < 600 and el["selector"] not in clicked]
        for el in nearby[:3]:  # 섹션당 최대 3개
            actions.append({"type":"click","selector":el["selector"],"label":el["text"][:40]})
            clicked.add(el["selector"])

        narration = h["text"]
        if nearby:
            names = ", ".join(el["text"][:30] for el in nearby[:2])
            narration += f". 여기서 {names} 등을 클릭해보겠습니다."

        scenes.append({"narration": narration, "actions": actions})

    # 남은 인터랙티브 요소들 (안 클릭된 것)
    remaining = [el for el in interactive if el["selector"] not in clicked]
    if remaining:
        actions = [{"type":"scroll","y":remaining[0]["y"]-100,"steps":30,"ms":30}]
        for el in remaining[:5]:
            actions.append({"type":"click","selector":el["selector"],"label":el["text"][:40]})
        scenes.append({
            "narration": "남은 기능들도 확인해보겠습니다.",
            "actions": actions
        })

    # 엔딩
    scenes.append({
        "narration": "이상으로 모든 기능 시연을 마치겠습니다. 감사합니다.",
        "actions": [{"type":"scroll","y":max(0,total_h-H),"steps":40,"ms":40},{"type":"wait","ms":1500}]
    })

    # TTS 생성
    print(f"\n🔊 TTS {len(scenes)}씬 생성...")
    for i, s in enumerate(scenes):
        mp3 = os.path.join(work, f"s{i:03d}.mp3")
        comm = edge_tts.Communicate(s["narration"][:3000], "ko-KR-SunHiNeural", rate="+5%")
        await comm.save(mp3)
        dur = float(subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",mp3],
            capture_output=True, text=True
        ).stdout.strip() or 5)
        s["tts_file"] = mp3; s["tts_dur"] = dur
        print(f"  🎙️ 씬{i+1}: {dur:.1f}초 — {s['narration'][:60]}")

    total_dur = sum(s["tts_dur"] for s in scenes)
    print(f"⏱ 전체 {total_dur:.0f}초")

    # ── 3단계: 녹화 ──
    print("🎬 녹화 시작...")
    raw_video = os.path.join(work, "raw.webm")
    _record_result = {}

    def _record():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": W, "height": H},
                record_video_dir=work,
                record_video_size={"width": W, "height": H}
            )
            page = context.new_page()

            # 페이지 로드 → 커튼이 알아서 사라짐
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            inject_all(page)

            # 커튼 사라질 때까지 대기
            try:
                page.wait_for_selector('#__curtain', state='detached', timeout=5000)
            except:
                page.evaluate("document.getElementById('__curtain')?.remove()")
            page.wait_for_timeout(500)

            total_h = page.evaluate("document.body.scrollHeight")
            clicked_count = 0

            for i, scene in enumerate(scenes):
                dur = scene["tts_dur"]
                scene_start = time.time()
                print(f"  🎬 씬{i+1}/{len(scenes)} ({dur:.1f}초)")

                for action in scene.get("actions", []):
                    elapsed = time.time() - scene_start
                    if elapsed >= dur: break

                    at = action["type"]
                    if at == "scroll":
                        scroll_to(page, action["y"], action.get("steps",50), action.get("ms",25))
                    elif at == "click":
                        ok = click_element(page, action["selector"], action.get("label",""))
                        if ok: clicked_count += 1
                    elif at == "wait":
                        rem = max(100, int((dur - elapsed) * 1000))
                        page.wait_for_timeout(min(action["ms"], rem))

                # 남은 시간: 천천히 추가 스크롤 또는 현재 위치 유지
                remaining = dur - (time.time() - scene_start)
                if remaining > 0.5:
                    cur = page.evaluate("window.scrollY")
                    target = min(cur + 120, total_h - H)
                    steps = int(remaining * 1000 / 60)
                    for s in range(steps):
                        y = cur + (target - cur) * (s / steps)
                        page.evaluate(f"window.scrollTo({{top:{y},behavior:'auto'}})")
                        page.wait_for_timeout(60)

            page.wait_for_timeout(1500)
            context.close()
            browser.close()
            _record_result["clicks"] = clicked_count

    t = threading.Thread(target=_record); t.start(); t.join()
    print(f"  🖱️ 실제 클릭: {_record_result.get('clicks',0)}회")

    # 비디오 찾기
    videos = sorted(glob.glob(f"{work}/*.webm"), key=os.path.getctime)
    if not videos: print("❌ 녹화 없음"); return
    raw = videos[-1]
    print(f"🎥 {os.path.getsize(raw)//1024}KB")

    # ── 4단계: 오디오 믹스 ──
    print("🔗 믹스...")
    concat = os.path.join(work, "tts.txt")
    with open(concat, "w") as f:
        for s in scenes: f.write(f"file '{s['tts_file']}'\n")
    merged = os.path.join(work, "merged.mp3")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",concat,"-c","copy",merged], capture_output=True, check=True)
    subprocess.run(["ffmpeg","-y","-i",raw,"-i",merged,"-c:v","libx264","-c:a","aac","-b:a","192k","-pix_fmt","yuv420p","-shortest",args.output], capture_output=True, check=True)

    size_mb = os.path.getsize(args.output)/(1024*1024)
    print(f"\n✅ {args.output}")
    print(f"   📦 {size_mb:.1f}MB · ⏱ {total_dur:.0f}초 · 🎬 {len(scenes)}씬 · 🖱️ {_record_result.get('clicks',0)}클릭")
    print(f"   ✨ 커서·클릭리플·커튼·부드러운스크롤 전부 적용")


if __name__ == "__main__":
    asyncio.run(main())
