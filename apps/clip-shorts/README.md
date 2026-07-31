# Clip Shorts — Helena Studio Edition

> 원본: `dtslib1979/dtslib-cloud-appstore/clip-shorts/`
> FFmpeg.wasm 0.11.0 기반 PWA 영상 편집기

## 기능
- 클립 선택 → 자동 3분 쇼츠 생성
- FFmpeg.wasm 인브라우저 처리 (서버 불필요)
- BGM + 볼륨 정규화
- 인트로/트랜지션/엔딩 효과
- PWA (홈 화면 설치 가능)

## Helena Studio 확장 예정
- [ ] 이미지+오디오 → 영상 클립 변환 (웹페이지 스크린샷 지원)
- [ ] TTS 더빙 트랙 직접 주입
- [ ] parksy-audio RVC 음성プリセット
- [ ] MCP `compose_page` → `export_video` 파이프

## 기술 스택
- @ffmpeg/ffmpeg 0.11.0 + @ffmpeg/core-st 0.11.0 (싱글스레드)
- Pure HTML/CSS/JS
- Service Worker (PWA)
