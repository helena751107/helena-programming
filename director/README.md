# Director Agent

**URL → 소개 영상** 파이프. Grok/에이전트가 작가·디렉터, 폰 proot이 카메라·성우·편집.

```bash
cd helena-programming/director
python3 run_director.py --scenario scenarios/helena_phone.json
# or
python3 run_director.py --url https://helena751107.github.io/helena_phone/ --out out/demo.mp4
```

## Pipeline

1. **Voice** — edge-tts per beat  
2. **Intro** — ffmpeg title card  
3. **Shoot** — Playwright: scroll / click / hold timed to narration  
4. **Edit** — ffmpeg mux + concat  
5. **Report** — script.md + report.md  

## Scenario schema

See `scenarios/helena_phone.json`. Key fields: `url`, `voice`, `viewport`, `beats[]` with `narration`, `camera`, `clicks`.
