# Director Agent

**URL → 소개 영상** 파이프.  
Scout가 페이지를 파싱하고, Writer/Director가 시나리오를 짜고, 폰 proot이 카메라·성우·편집.

```bash
cd helena-programming/director

# 1) Scout only — 구조 지도 + 자동 시나리오
python3 run_director.py --url https://helena751107.github.io/helena_phone/ --scout-only

# 2) URL only — scout → auto scenario → full render
python3 run_director.py --url https://helena751107.github.io/helena_phone/ --out out/demo.mp4

# 3) Hand scenario + scout merge (selectors/clicks 보정)
python3 run_director.py --scenario scenarios/helena_phone.json --scout
```

## Pipeline

0. **Scout** — Playwright로 섹션·헤딩·아코디언·버튼·다이어그램 셀렉터 파싱 → `scout.json`  
1. **Write/Direct** — scout → `scenario.json` (또는 손시나리오에 셀렉터 머지)  
2. **Voice** — edge-tts per beat  
3. **Shoot** — 스크롤·클릭·hold (나레이션 길이 동기)  
4. **Edit** — ffmpeg intro + mux  
5. **Report** — script.md + report.md  

## Why Scout

손시나리오는 셀렉터가 빗나가면 스크롤만 하고 끝난다.  
Scout가 실제 DOM에서 `heading / deck / accordion / cta` 를 읽어 오면 연출이 자연스러워진다.

## Scenario schema

See `scenarios/helena_phone.json`. Key fields: `url`, `voice`, `viewport`, `beats[]` with `narration`, `camera`, `clicks`.
