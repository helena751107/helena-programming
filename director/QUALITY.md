# Director Quality — Perfect Ship 체크리스트

**진입점:** `python3 perfect_ship.py`  
**프로세스:** `process/perfect_ship_v1.json`  
**정책:** `policy/tutorial_v1.json` (v2)

렌더 산출물은 아래를 **전부 PASS**해야 SHIP / 텔레그램 가능.

## Process ladder

| # | Stage | Fail |
|---|-------|------|
| L0 | Scout | scout.json 없음 |
| L1 | Directing | `product_tour_v1` / `tutorial_v1` 미스탬프 |
| L2 | Voice | `tts_humanize` false · multi-click pad 없음 |
| L3 | Shoot | phases≠5 · overlay&lt;4 · cursor_on_primary false · clicks_done &lt; declared |
| L4 | Proof | visual_proof 미달 |
| L5 | Edit | mp4 없음/과소 |
| L6 | Quality G1–G7 | quality.pass false |
| L7 | Vision QA | score &lt; **100** 또는 V1/V4 hard fail |
| L8 | Process verify | perfect_ship.py ladder fail |
| L9 | SHIP | 위 전부 PASS |

## Quality gates (G1–G7)

| # | Gate | Fail 조건 |
|---|------|-----------|
| G1 | Intro CJK | 토푸(□) |
| G2 | Lead black | 선두 연속 검정 과다 |
| G3 | Has motion UI | 중간 프레임 단색 |
| G4 | Duration | 12s–150s 밖 |
| G5 | Audio | 오디오 없음 |
| G6 | Scenario | beat/camera 부족 |
| G7 | Overlay accents | gold+teal 샘플 부족 |

## 금지 (가짜 SHIP)

- successful_clicks만 세고 화면 효과 없음  
- expand-all 후 아코디언 무변화  
- 클릭 직후 clearFocus로 링 1초 소멸  
- 커서 메트릭 그리드 주차  
- declared click 중 일부 스킵  
- 사다리 무시하고 세션 즉흥 패치  

## 산출 사이드카

```
out/NAME.mp4
out/NAME.actions.json
out/NAME.quality.json
out/NAME.vision_qa.json
out/NAME.process.json    ← perfect_ship 리포트 (필수)
out/NAME.process.md
out/NAME.audit.json
```

재발·솔루션 문서: `_notebook/48` … `55` · **`56-director-perfect-ship-process_Grok.md`**
