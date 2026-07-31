#!/usr/bin/env python3
"""
webpage_to_video.py — Markdown/HTML → Edge TTS + Playwright → MP4
proot Ubuntu 전용. S21 단독. 외부 API 0원.
"""

import sys, os, re, asyncio, subprocess, argparse, tempfile, threading
from pathlib import Path

# ── Markdown → 섹션 분할 ──
def parse_markdown(text: str) -> list:
    """Markdown 본문을 제목+본문 섹션 리스트로 분할"""
    lines = text.split('\n')
    sections = []
    current_title = ""
    current_body = []

    for line in lines:
        stripped = line.strip()
        # 헤딩 감지
        m = re.match(r'^#{1,3}\s+(.+)', stripped)
        if m:
            if current_body:
                body = ' '.join(current_body).strip()
                if len(body) > 20:
                    sections.append((current_title or "개요", body))
            current_title = m.group(1)
            current_body = []
            continue
        # 빈 줄 / 구분선 / 표 건너뛰기
        if not stripped or stripped.startswith('|') or stripped.startswith('---'):
            continue
        # 일반 텍스트
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', stripped)  # [text](url) → text
        clean = re.sub(r'[*_`>#]', '', clean)  # 마크다운 기호 제거
        if clean.strip():
            current_body.append(clean)

    if current_body:
        body = ' '.join(current_body).strip()
        if len(body) > 20:
            sections.append((current_title or "마무리", body))

    return sections


# ── HTML → 섹션 분할 ──
def parse_html(html: str) -> list:
    """HTML 본문을 h1~h3 + 본문 섹션으로 분할"""
    from html.parser import HTMLParser

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.sections = []
            self._cur_h = ""
            self._cur_body = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ('script','style','code','pre','nav','footer'): self._skip = True
            if tag in ('h1','h2','h3'):
                if self._cur_body:
                    b = ' '.join(self._cur_body).strip()
                    if len(b) > 20:
                        self.sections.append((self._cur_h or "개요", b))
                self._cur_h = ""; self._cur_body = []

        def handle_endtag(self, tag):
            if tag in ('script','style','code','pre','nav','footer'): self._skip = False

        def handle_data(self, data):
            if self._skip: return
            d = data.strip()
            if not d: return
            if self._last_tag() in ('h1','h2','h3'):
                self._cur_h = d
            else:
                self._cur_body.append(d)

        def _last_tag(self):
            return getattr(self, '_tag', '')

        def close(self):
            if self._cur_body:
                b = ' '.join(self._cur_body).strip()
                if len(b) > 20:
                    self.sections.append((self._cur_h or "마무리", b))
            super().close()

    class Parser2(HTMLParser):
        """태그를 추적하는 래퍼"""
        def __init__(self):
            super().__init__()
            self.sections = []
            self._h = ""
            self._b = []
            self._skip = False
            self._tag = ""

        def handle_starttag(self, tag, a):
            self._tag = tag
            if tag in ('script','style','code','pre','nav','footer'): self._skip = True
            if tag in ('h1','h2','h3'):
                if self._b:
                    b = ' '.join(self._b).strip()
                    if len(b) > 20: self.sections.append((self._h or "개요", b))
                self._h = ""; self._b = []

        def handle_endtag(self, tag):
            self._tag = tag
            if tag in ('script','style','code','pre','nav','footer'): self._skip = False

        def handle_data(self, d):
            if self._skip: return
            t = d.strip()
            if not t: return
            if self._tag in ('h1','h2','h3'): self._h = t
            else: self._b.append(t)

        def close(self):
            if self._b:
                b = ' '.join(self._b).strip()
                if len(b) > 20: self.sections.append((self._h or "마무리", b))
            super().close()

    p = Parser2()
    p.feed(html)
    p.close()
    return p.sections


# ── 템플릿 ──
TEMPLATE_DARK = '''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans KR','Apple SD Gothic Neo',system-ui,sans-serif;
  background:linear-gradient(180deg,#0f172a 0%,#1e1a3a 50%,#0f172a 100%);
  color:#e2e8f0;width:{width}px;min-height:{height}px;padding:60px 50px;
  display:flex;flex-direction:column;justify-content:center}}
.progress{{font-size:14px;color:{accent};margin-bottom:30px;letter-spacing:2px}}
h1{{font-size:38px;line-height:1.3;margin-bottom:40px;color:#f8fafc;font-weight:700}}
h1 .accent{{color:{accent}}}
p{{font-size:22px;line-height:1.8;margin-bottom:16px;color:#cbd5e1}}
.page-num{{position:fixed;bottom:40px;right:50px;font-size:14px;color:#475569}}
.bar{{position:fixed;bottom:50px;left:50px;right:50px;height:2px;background:#1e293b;border-radius:1px}}
.bar-fill{{height:100%;background:{accent};width:{pct}%;border-radius:1px}}
.logo{{position:fixed;top:40px;right:50px;font-size:12px;color:#475569;letter-spacing:1px}}
</style></head><body>
<div class="logo">HELENA STUDIO</div>
<div class="progress">SECTION {n} / {total}</div>
<h1><span class="accent">{title}</span></h1>
{body_html}
<div class="page-num">{n}/{total}</div>
<div class="bar"><div class="bar-fill"></div></div>
</body></html>'''


def make_section_html(title: str, body: str, n: int, total: int,
                      template: str = "dark", width=720, height=1280) -> str:
    """섹션 데이터 → 렌더링용 HTML 생성"""
    paras = [p.strip() for p in body.replace('\n','.').split('.') if len(p.strip()) > 3]
    body_html = '\n'.join(f'<p>{p}.</p>' for p in paras[:12])

    accent = "#6366f1"
    return TEMPLATE_DARK.format(
        title=title, body_html=body_html, n=n, total=total,
        pct=int(n/total*100), accent=accent, width=width, height=height
    )


# ── Playwright 스크린샷 (threaded) ──
def screenshot(html: str, path: str, width=720, height=1280):
    from playwright.sync_api import sync_playwright
    def _run():
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page(viewport={"width": width, "height": height})
            page.set_content(html, timeout=15000)
            page.screenshot(path=path, full_page=True)
            b.close()
    t = threading.Thread(target=_run); t.start(); t.join()
    return path


# ── Edge TTS ──
async def tts(text: str, voice: str, path: str, rate="+5%"):
    import edge_tts
    t = text[:3000]
    comm = edge_tts.Communicate(t, voice, rate=rate)
    await comm.save(path)
    return path


# ── FFmpeg: 이미지+오디오→클립 ──
def frame_to_clip(image: str, audio: str, output: str):
    dur = float(subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","csv=p=0",audio], capture_output=True, text=True
    ).stdout.strip() or 10)
    subprocess.run([
        "ffmpeg","-y","-loop","1","-i",image,"-i",audio,
        "-c:v","libx264","-tune","stillimage",
        "-c:a","aac","-b:a","192k","-pix_fmt","yuv420p",
        "-t",str(dur),"-shortest",output
    ], capture_output=True, check=True)
    return output


# ── FFmpeg: 클립 이어붙이기 ──
def concat_clips(files: list, output: str):
    lst = os.path.join(os.path.dirname(output), "concat.txt")
    with open(lst,"w") as f:
        for fp in files: f.write(f"file '{fp}'\n")
    subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0","-i",lst,"-c","copy",output
    ], capture_output=True, check=True)
    return output


# ── 메인 ──
async def main(source: str, voice="ko-KR-SunHiNeural", rate="+5%",
               output=None, width=720, height=1280):
    # 1. 소스 읽기
    if source.startswith("http"):
        import urllib.request
        with urllib.request.urlopen(source) as r:
            text = r.read().decode("utf-8", errors="replace")
    else:
        text = Path(source).read_text(encoding="utf-8", errors="replace")

    # 2. 포맷 감지 → 섹션 분할
    if source.endswith('.md') or source.endswith('.MD'):
        sections = parse_markdown(text)
    elif text.strip().startswith('<'):
        sections = parse_html(text)
    else:
        sections = parse_markdown(text)  # fallback

    if not sections:
        print("❌ 섹션 추출 실패"); return None

    sections = sections[:8]  # 최대 8섹션
    print(f"📝 {len(sections)}섹션")

    # 3. 각 섹션 → 스크린샷 + TTS → 클립
    work = tempfile.mkdtemp(prefix="hstudio_")
    clips = []

    for i, (title, body) in enumerate(sections, 1):
        print(f"  🎬 [{i}/{len(sections)}] {title[:40]}")

        # 스크린샷
        html = make_section_html(title, body, i, len(sections), width=width, height=height)
        png = os.path.join(work, f"f{i:03d}.png")
        screenshot(html, png, width, height)
        print(f"     📸 {os.path.getsize(png)//1024}KB")

        # TTS
        mp3 = os.path.join(work, f"a{i:03d}.mp3")
        await tts(f"{title}. {body}", voice, mp3, rate)
        print(f"     🔊 {os.path.getsize(mp3)//1024}KB")

        # 클립
        clip = os.path.join(work, f"c{i:03d}.mp4")
        frame_to_clip(png, mp3, clip)
        print(f"     🎥 {os.path.getsize(clip)//1024}KB")
        clips.append(clip)

    # 4. 이어붙이기
    if not output:
        base = Path(source).stem
        output = f"/tmp/{base}.mp4"

    print(f"\n🔗 {len(clips)}클립 이어붙이기...")
    concat_clips(clips, output)

    size_mb = os.path.getsize(output)/(1024*1024)
    dur = float(subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","csv=p=0",output], capture_output=True, text=True
    ).stdout.strip() or 0)

    print(f"\n✅ {output}")
    print(f"   📦 {size_mb:.1f}MB · ⏱ {dur/60:.1f}분 · 🎬 {len(clips)}섹션")
    return output


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Markdown/HTML → Edge TTS + Playwright → MP4")
    ap.add_argument("source", help="URL / .md / .html")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural")
    ap.add_argument("--rate", default="+5%")
    ap.add_argument("--output","-o")
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    args = ap.parse_args()
    asyncio.run(main(args.source, args.voice, args.rate, args.output, args.width, args.height))
