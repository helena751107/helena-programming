# Director Agent — Perfect Ship (만점 강제)

**URL → 제품 투어 영상.**  
에이전트가 세션마다 마음대로 품질 땜빵하는 것 **금지**.

> **영상 3트랙 중 V2 (Grok 구독 파이프).**  
> V1 = PPT 수준 0원 · V2 = 이 Director · V3 = ComfyUI 프로 마감.  
> 전문: `_notebook/58-video-three-tracks_Grok.md`

## 유일한 진입점

```bash
cd helena-programming/director

# ✅ CANONICAL — 만점 사다리 전체
python3 perfect_ship.py \
  --scenario scenarios/helena_phone.json \
  --out out/helena_phone.mp4

# 동일 (alias)
python3 run_director.py --process perfect_ship_v1 \
  --scenario scenarios/helena_phone.json \
  --out out/helena_phone.mp4

# 이미 렌더된 work/ 만 재검증
python3 perfect_ship.py --verify-only \
  --scenario scenarios/helena_phone.json \
  --out out/helena_phone_pro_v6.mp4
```

**SHIP 배지 없이 텔레그램 전송 금지.**

---

## 권위 순서 (하드)

```
process/perfect_ship_v1.json     →  만점 사다리 (L0–L9)
directing/product_tour_v1.json  →  연출 5막·빛·커서
policy/tutorial_v1.json          →  ship 금지 조건
enforce.py + perfect_ship.py     →  결정론 게이트
scenarios/*.json                 →  대본만
run_director.py                  →  연주
vision_qa.py                     →  프레임 점수
```

---

## 사다리 (코드화)

| Stage | 이름 | 실패 exit |
|-------|------|-----------|
| L0 | Scout | 3 |
| L1 | Directing + policy stamp | 3 |
| L2 | TTS humanize + multi-click pad | 3 |
| L3 | 5-act shoot · overlay v4 · cursor_on_primary · **all declared clicks** | 4 |
| L4 | Visual proof gold/teal | 4 |
| L5 | Edit mp4 | 2 |
| L6 | Quality G1–G7 | 2 |
| L7 | Vision QA ≥ **100** | 5 |
| L8 | perfect_ship verify | 6 |
| L9 | SHIP (TG 허용) | 0 |

게이트 실패 시 → `process/perfect_ship_v1.json` 의 **remediation_map** 키만 패치 → 사다리 재실행.  
새 임시 스크립트·즉흥 순서 **금지**.

---

## Anti-patterns (강제 차단)

| ID | 증상 | 코드 고정 |
|----|------|-----------|
| AP1 | 커서 메트릭 주차 | overlay v4 + `cursor_on_primary` |
| AP2 | 클릭 숫자만 SHIP | `require_visual_proof` |
| AP3 | 2차 클릭 드롭 | `require_all_declared_clicks` + multi pad |
| AP4 | 결과 프레임 없음 | act result hold + hold re-lock |
| AP5 | 세션마다 다른 순서 | 이 process만 허용 |
| AP6 | VQA만 만점·사람 프레임 실패 | process report + proof |

---

## 파일

| 경로 | 역할 |
|------|------|
| **`perfect_ship.py`** | **만점 진입점** |
| **`process/perfect_ship_v1.json`** | **사다리 정의** |
| `directing/product_tour_v1.json` | 5막 연출 |
| `policy/tutorial_v1.json` | require 전부 |
| `enforce.py` | 결정론 거부 |
| `overlays.js` v4 | cursor-lock · zoom |
| `run_director.py` | 연주 + process stamp |
| `vision_qa.py` | 프레임 점수 |
| `QUALITY.md` | 체크리스트 문서 |

---

## 에이전트 규칙 (필수)

1. 만점 올리기 = `python3 perfect_ship.py` 만 실행.
2. FAIL 시 `.process.json` 의 remediation_ids 만 보고 해당 코드 수정.
3. SHIP 없이 TG 보내지 말 것.
4. policy/process/directing JSON 예외 처리 금지.
