# Director Agent — forced tutorial pipeline

**URL → 하이테크 튜토리얼 영상.**  
LLM 마음대로 연출 금지. **policy + schema + deterministic enforce** 가 강제한다.

## MCP가 필요한가?

**필수는 아님.**  
강제는 MCP가 아니라 다음 3단으로 한다:

1. `policy/tutorial_v1.json` — 무엇을 반드시 할지 (클릭 수, 캡션, 커서, 블랙 한도…)
2. `schema/scenario.schema.json` + `enforce.py` — 시나리오/액션로그/품질 실패 시 **exit ≠ 0**
3. `run_director.py` 단일 진입점 — ship 전 게이트 통과 없으면 산출물 “공식” 취급 금지

MCP는 **나중에** Claude/다른 에이전트에게 `director.run` 툴만 노출할 때 얹으면 된다.  
지금 단계에서 MCP만 만들면 또 말만 하고 파이프는 안 굳는다.

```bash
cd helena-programming/director

# 기본 = tutorial_v1 강제
python3 run_director.py --url https://helena751107.github.io/helena_phone/ \
  --out out/demo.mp4

# 정책 파일만 검사
python3 -c "from enforce import load_policy; print(load_policy('tutorial_v1')['id'])"
```

## Pipeline

0. Scout → `scout.json`  
1. Scenario stamp (`policy: tutorial_v1`) + **enforce pre_shoot**  
2. Voice (edge-tts)  
3. Intro HTML/CJK  
4. Shoot + overlays (커서·캡션·프로그레스) + `actions_log.json`  
5. **enforce post_shoot** (min clicks 등)  
6. Edit (black trim)  
7. Quality + **enforce pre_ship**  
8. Self-audit JSON  

실패 시 exit: `3` pre_shoot · `4` post_shoot · `2` quality/pre_ship  

## Files

| 파일 | 역할 |
|------|------|
| `policy/tutorial_v1.json` | 강제 규칙 |
| `enforce.py` | 결정론 게이트 |
| `overlays.js` | 튜토리얼 UI 오버레이 |
| `QUALITY.md` | 만점 체크리스트 |
| `../_notebook/48-director-video-recurrence_Grok.md` | 재발일지 |
