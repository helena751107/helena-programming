# Webpage → Video Pipeline

> Helena Studio의 핵심 파이프라인: 웹페이지를 영상으로 변환하는 풀스택

## 개요

```
웹페이지(Mermaid+HTML) → 스크린샷(PNG) → TTS더빙(MP3) → 영상클립(MP4) → clip-shorts → 최종영상
```

## 단계별 상세

### ① 웹페이지 생성 (온디바이스 / 웹MCP)
- Mermaid → SVG 다이어그램
- HTML/CSS 템플릿에 합성
- parksy-image 도면·웹툰 자산 삽입

### ② 스크린샷 (Playwright / Puppeteer)
```bash
# WSL/PC:
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    page.goto('https://helena751107.github.io/helena-programming/web/public/')
    page.screenshot(path='page.png', full_page=True)
"
```

### ③ TTS 더빙 (parksy-audio)
```python
# parksy-audio RVC 음성 클론
from mcp_server import HelenaMCP
server = HelenaMCP()
result = await server.handle_request('tools/call', {
    'name': 'voice_dub',
    'arguments': {'text': '안녕하세요, 헬레나 스튜디오입니다.', 'voice': 'parksy'}
})
# → voice.wav
```

### ④ 이미지+오디오 → 영상 클립 (FFmpeg.wasm)
```bash
# FFmpeg (인브라우저 or CLI):
ffmpeg -loop 1 -i page.png -i voice.mp3 \
  -c:v libx264 -tune stillimage \
  -c:a aac -b:a 192k \
  -pix_fmt yuv420p -shortest \
  clip_001.mp4
```

### ⑤ 클립 이어붙이기 (clip-shorts PWA)
- clip_001.mp4, clip_002.mp4, ... 업로드
- BGM 추가
- 인트로/엔딩 효과
- 최종 3분 쇼츠 다운로드

## 구현 상태

| 단계 | 상태 | 위치 |
|------|------|------|
| ① 웹페이지 생성 | 🟡 구조만 | `mcp/mcp_server.py` render_diagram |
| ② 스크린샷 | 🟢 보유 | `helena_phone/tistory-naver/session_post.py` |
| ③ TTS 더빙 | 🟢 보유 | `dtslib1979/parksy-audio/` phone_rvc.py |
| ④ 이미지→영상 | 🔴 미구현 | clip-shorts에 추가 예정 |
| ⑤ 클립 이어붙이기 | 🟢 보유 | `apps/clip-shorts/` (FFmpeg.wasm PWA) |

## 기술 의존성

- **FFmpeg.wasm 0.11.0** — 인브라우저 영상 처리
- **Playwright** — 웹페이지 스크린샷 (WSL/PC)
- **parksy-audio RVC** — 음성 클론 더빙
- **GitHub Pages** — 웹페이지 호스팅
- **Vercel** — MCP API 엔드포인트
