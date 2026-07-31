#!/usr/bin/env python3
"""
webpage_to_video.py — 웹페이지 → Edge TTS + 스크린샷 → MP4 영상
================================================================
S21 폰 단독 실행. PC/WSL 불필요. 외부 API 불필요.

사용:
  python3 scripts/webpage_to_video.py https://example.com/page.html
  python3 scripts/webpage_to_video.py page.html --voice ko-KR-InJoonNeural
  python3 scripts/webpage_to_video.py page.html --output /tmp/output.mp4

파이프:
  HTML → Playwright 스크린샷 (PNG) → Edge TTS (MP3) → FFmpeg (MP4) → 이어붙이기 → 최종 영상
"""

import sys, os, re, asyncio, subprocess, argparse, tempfile, textwrap
from pathlib import Path
from html.parser import HTMLParser


# ── HTML 텍스트 추출 ──────────────────────────────────────────────────────────

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sections = []  # [(heading_level, heading_text, body_text)]
        self.current_h = None
        self.current_body = []
        self.skip = False
        self._last_tag = None

    def handle_starttag(self, tag, attrs):
        self._last_tag = tag
        if tag in ('script', 'style', 'code', 'pre', 'nav', 'footer'):
            self.skip = True
        # 헤딩 감지 시 이전 섹션 저장
        if tag in ('h1', 'h2', 'h3', 'h4'):
            self._flush_section()
            self.current_h = (int(tag[1]), "")  # text will come in handle_data

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'code', 'pre', 'nav', 'footer'):
            self.skip = False
        if tag in ('h1', 'h2', 'h3', 'h4'):
            # heading text already captured
            pass

    def handle_data(self, data):
        if self.skip:
            return
        t = data.strip()
        if not t:
            return
        if self._last_tag in ('h1', 'h2', 'h3', 'h4') and self.current_h:
            level, _ = self.current_h
            self.current_h = (level, t)
        else:
            self.current_body.append(t)

    def _flush_section(self):
        body = ' '.join(self.current_body).strip()
        if self.current_h:
            level, heading = self.current_h
            self.sections.append((level, heading, body))
        elif body:
            self.sections.append((0, "", body))
        self.current_h = None
        self.current_body = []

    def close(self):
        self._flush_section()
        super().close()


def extract_sections(html: str) -> list:
    parser = TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.sections


# ── 스크린샷 (Playwright) ────────────────────────────────────────────────────

def html_to_screenshot(html: str, output: str, width: int = 720, height: int = 1280):
    """Playwright로 HTML → PNG 스크린샷 (threaded — asyncio 내부에서 호출 가능)"""
    from playwright.sync_api import sync_playwright
    import threading

    def _capture():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html, timeout=10000)
            page.screenshot(path=output, full_page=True)
            browser.close()

    t = threading.Thread(target=_capture)
    t.start()
    t.join()
    return output


# ── 섹션별 HTML 페이지 생성 ──────────────────────────────────────────────────

def build_section_html(heading: str, body: str, section_num: int, total: int,
                       bg_color: str = "#0f172a", text_color: str = "#e2e8f0",
                       accent: str = "#6366f1") -> str:
    """한 섹션을 아름다운 HTML 카드로 렌더링"""
    # body 텍스트를 읽기 좋게 분할
    body_paras = [p.strip() for p in body.split('. ') if p.strip()]
    body_html = '\n'.join(f'<p>{p}.</p>' for p in body_paras)

    return f'''<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', system-ui, sans-serif;
  background: {bg_color}; color: {text_color};
  width: 720px; min-height: 1280px; padding: 60px 50px;
  display: flex; flex-direction: column; justify-content: center;
}}
.progress {{ font-size: 14px; color: {accent}; margin-bottom: 30px;
  letter-spacing: 2px; text-transform: uppercase; }}
h1 {{ font-size: 38px; line-height: 1.3; margin-bottom: 40px;
  color: #f8fafc; font-weight: 700; }}
h1 .accent {{ color: {accent}; }}
p {{ font-size: 22px; line-height: 1.8; margin-bottom: 16px;
  color: #cbd5e1; }}
.page-num {{ position: fixed; bottom: 40px; right: 50px;
  font-size: 14px; color: #475569; }}
.bar {{ position: fixed; bottom: 50px; left: 50px; right: 50px;
  height: 2px; background: #1e293b; border-radius: 1px; }}
.bar-fill {{ height: 100%; background: {accent};
  width: {section_num/total*100:.0f}%; border-radius: 1px; transition: width 0.3s; }}
.logo {{ position: fixed; top: 40px; right: 50px;
  font-size: 12px; color: #475569; letter-spacing: 1px; }}
</style></head>
<body>
<div class="logo">HELENA STUDIO</div>
<div class="progress">SECTION {section_num} / {total}</div>
<h1><span class="accent">{heading}</span></h1>
{body_html}
<div class="page-num">{section_num}/{total}</div>
<div class="bar"><div class="bar-fill"></div></div>
</body></html>'''


# ── Edge TTS ──────────────────────────────────────────────────────────────────

async def text_to_speech(text: str, voice: str, output: str, rate: str = "+5%"):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate)
    await comm.save(output)
    return output


# ── 이미지+오디오 → 영상 클립 (FFmpeg) ────────────────────────────────────────

def image_audio_to_video(image: str, audio: str, output: str):
    """PNG + MP3 → MP4 (still image video)"""
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio], capture_output=True, text=True
    ).stdout.strip() or 10)

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", image,
        "-i", audio,
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(dur),
        "-shortest", output
    ], capture_output=True, check=True)

    return output


# ── 영상 클립 이어붙이기 ──────────────────────────────────────────────────────

def concat_videos(files: list, output: str):
    """FFmpeg concat demuxer — 무손실 영상 이어붙이기"""
    concat_list = os.path.join(os.path.dirname(output), "concat_video_list.txt")
    with open(concat_list, "w") as f:
        for fp in files:
            f.write(f"file '{fp}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy", output
    ], capture_output=True, check=True)

    return output


# ── 메인 파이프 ──────────────────────────────────────────────────────────────

async def webpage_to_video(source: str, voice: str = "ko-KR-SunHiNeural",
                            rate: str = "+5%", output: str = None,
                            width: int = 720, height: int = 1280):
    """웹페이지 → Edge TTS + 스크린샷 → MP4 영상"""

    # 1. HTML 가져오기
    print(f"📄 소스: {source}")
    if source.startswith("http"):
        import urllib.request
        with urllib.request.urlopen(source) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    else:
        html = Path(source).read_text(encoding="utf-8", errors="replace")

    # 2. 섹션 분할
    sections = extract_sections(html)
    if not sections:
        # 헤딩 없으면 본문 전체를 하나로
        from html.parser import HTMLParser
        class SimpleExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = False
            def handle_starttag(self, tag, a):
                if tag in ('script','style','code','pre'): self.skip = True
            def handle_endtag(self, tag):
                if tag in ('script','style','code','pre'): self.skip = False
            def handle_data(self, d):
                if not self.skip and d.strip(): self.text.append(d.strip())
        ex = SimpleExtractor(); ex.feed(html); ex.close()
        full = '\n'.join(ex.text)
        sections = [(0, Path(source).stem, full)]

    print(f"📝 섹션: {len(sections)}개")

    # 3. 각 섹션 → HTML 페이지 → 스크린샷 + TTS → MP4 클립
    workdir = tempfile.mkdtemp(prefix="helena_video_")
    clips = []

    for i, (level, heading, body) in enumerate(sections, 1):
        title = heading or f"Section {i}"
        text_for_tts = f"{title}. {body}" if heading else body
        if len(text_for_tts.strip()) < 10:
            continue

        print(f"  🎬 [{i}/{len(sections)}] {title[:50]}")

        # 3a. HTML 페이지 생성 + 스크린샷
        section_html = build_section_html(title, body, i, len(sections))
        png_path = os.path.join(workdir, f"frame_{i:03d}.png")
        html_to_screenshot(section_html, png_path, width, height)
        print(f"     📸 스크린샷: {os.path.getsize(png_path)//1024}KB")

        # 3b. Edge TTS
        mp3_path = os.path.join(workdir, f"audio_{i:03d}.mp3")
        await text_to_speech(text_for_tts, voice, mp3_path, rate)
        print(f"     🔊 TTS: {os.path.getsize(mp3_path)//1024}KB")

        # 3c. 이미지+오디오 → 영상 클립
        clip_path = os.path.join(workdir, f"clip_{i:03d}.mp4")
        image_audio_to_video(png_path, mp3_path, clip_path)
        print(f"     🎥 클립: {os.path.getsize(clip_path)//1024}KB")
        clips.append(clip_path)

    if not clips:
        print("❌ 생성된 클립이 없습니다")
        return None

    # 4. 모든 클립 이어붙이기
    if output is None:
        base = Path(source).stem if not source.startswith("http") else "video"
        output = f"/tmp/{base}.mp4"

    print(f"\n🔗 {len(clips)}개 클립 이어붙이는 중...")
    concat_videos(clips, output)

    # 5. 결과
    size_mb = os.path.getsize(output) / (1024 * 1024)
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", output], capture_output=True, text=True
    ).stdout.strip() or 0)

    print(f"\n✅ 완료! {output}")
    print(f"   📦 {size_mb:.1f}MB · ⏱ {duration/60:.1f}분 · 🎬 {len(clips)}클립")
    print(f"   🗣️ {voice}")
    print(f"   📱 S21 단독 · 0원")

    return output


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="웹페이지 → TTS + 스크린샷 → MP4 영상")
    parser.add_argument("source", help="URL 또는 HTML/MD 파일")
    parser.add_argument("--voice", default="ko-KR-SunHiNeural")
    parser.add_argument("--rate", default="+5%")
    parser.add_argument("--output", "-o")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    args = parser.parse_args()
    asyncio.run(webpage_to_video(
        args.source, args.voice, args.rate,
        args.output, args.width, args.height
    ))


if __name__ == "__main__":
    main()
