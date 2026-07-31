#!/usr/bin/env python3
"""
Scout step — parse a live page into a shootable map for the Director.

Output scout.json:
  title, description, url, sections[], interactives[], nav[], stats
Each section has: id, selector, heading, deck, text_preview, interactives[]
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SCOUT_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el) return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  const cssPath = (el) => {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let cur = el;
    for (let d = 0; d < 5 && cur && cur.nodeType === 1 && cur !== document.body; d++) {
      if (cur.id) { parts.unshift('#' + CSS.escape(cur.id)); break; }
      let part = cur.tagName.toLowerCase();
      if (cur.classList && cur.classList.length) {
        const cls = [...cur.classList].slice(0, 2).map(c => '.' + CSS.escape(c)).join('');
        part += cls;
      }
      const parent = cur.parentElement;
      if (parent) {
        const sibs = [...parent.children].filter(x => x.tagName === cur.tagName);
        if (sibs.length > 1) part += `:nth-of-type(${sibs.indexOf(cur) + 1})`;
      }
      parts.unshift(part);
      cur = parent;
    }
    return parts.join(' > ');
  };

  const title = clean(document.title);
  const desc = clean(
    document.querySelector('meta[name="description"]')?.content ||
    document.querySelector('meta[property="og:description"]')?.content || ''
  );

  // Prefer explicit section chapters
  let sectionEls = [...document.querySelectorAll('section.chapter, section[id], main section[id]')];
  if (sectionEls.length < 2) {
    sectionEls = [...document.querySelectorAll('section[id], [data-ch], main > section')];
  }
  // Always include cover if present
  const cover = document.querySelector('#cover, .cover, header.hero, section.hero');
  if (cover && !sectionEls.includes(cover)) sectionEls.unshift(cover);

  // de-dupe
  const seen = new Set();
  sectionEls = sectionEls.filter(el => {
    const key = el.id || cssPath(el);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const interactivesOf = (root) => {
    const out = [];
    const sels = [
      'button.acc-head', '.acc-head', 'button[aria-expanded]',
      'button', 'a.btn', 'a.btn-solid', 'a.btn-line', '[data-cursor]',
      '.pillar', '.m-step', '.chan', '.node', 'summary',
      '[role="button"]', 'input[type="button"]', '.lib-card'
    ];
    const found = new Set();
    for (const sel of sels) {
      root.querySelectorAll(sel).forEach(el => {
        if (!visible(el) || found.has(el)) return;
        // skip pure nav chrome sometimes
        if (el.closest('.masthead, .mast-right, .chapter-rail, .to-top, .cursor')) return;
        found.add(el);
        const label = clean(el.innerText || el.getAttribute('aria-label') || el.title || '').slice(0, 80);
        const r = el.getBoundingClientRect();
        out.push({
          tag: el.tagName.toLowerCase(),
          selector: el.id ? ('#' + CSS.escape(el.id)) : cssPath(el),
          text: label,
          aria_expanded: el.getAttribute('aria-expanded'),
          role: el.getAttribute('role') || '',
          classes: [...(el.classList || [])].slice(0, 6),
          y: Math.round(r.top + window.scrollY),
          kind: el.matches('.acc-head, button.acc-head') ? 'accordion'
            : el.matches('.pillar, .m-step, .chan') ? 'card'
            : el.matches('.node') ? 'diagram'
            : el.matches('a.btn, a.btn-solid, a.btn-line, .btn') ? 'cta'
            : el.tagName === 'BUTTON' ? 'button'
            : el.tagName === 'A' ? 'link'
            : 'interactive'
        });
      });
    }
    // unique by selector, cap
    const u = [];
    const sk = new Set();
    for (const it of out) {
      if (sk.has(it.selector)) continue;
      sk.add(it.selector);
      u.push(it);
      if (u.length >= 24) break;
    }
    return u;
  };

  const sections = sectionEls.map((el, idx) => {
    const id = el.id || `sec_${idx}`;
    const heading = clean(
      el.querySelector('h1, h2, .ch-title, .cover h1')?.innerText || id
    );
    const deck = clean(
      el.querySelector('.ch-deck, .cover-sub, .deck, p')?.innerText || ''
    ).slice(0, 280);
    const text = clean(el.innerText || '').slice(0, 600);
    const selector = el.id ? ('#' + CSS.escape(el.id)) : cssPath(el);
    const inter = interactivesOf(el);
    const y = Math.round(el.getBoundingClientRect().top + window.scrollY);
    return {
      index: idx,
      id,
      selector,
      heading,
      deck,
      text_preview: text,
      y,
      height: Math.round(el.getBoundingClientRect().height),
      interactives: inter,
      has_accordion: inter.some(i => i.kind === 'accordion'),
      has_diagram: !!el.querySelector('svg, .svg-arch, canvas, .infograph-box')
    };
  }).filter(s => s.heading || s.text_preview);

  const globalInteractives = interactivesOf(document.body).slice(0, 40);

  const nav = [...document.querySelectorAll('.mast-right a[href^="#"], .chapter-rail a[href^="#"], nav a[href^="#"]')]
    .map(a => ({
      href: a.getAttribute('href'),
      text: clean(a.innerText || a.getAttribute('aria-label') || ''),
      selector: a.id ? ('#' + CSS.escape(a.id)) : cssPath(a)
    }))
    .filter(n => n.href && n.href.length > 1)
    .slice(0, 20);

  // expand-all control if any
  const expandBtn = document.querySelector('#accExpand, #accOpenAll, button#accExpand');
  const expand_selector = expandBtn ? (expandBtn.id ? '#' + CSS.escape(expandBtn.id) : cssPath(expandBtn)) : null;

  return {
    title,
    description: desc,
    url: location.href,
    lang: document.documentElement.lang || 'ko',
    theme: document.documentElement.getAttribute('data-theme') || '',
    viewport: { w: window.innerWidth, h: window.innerHeight, scrollHeight: document.documentElement.scrollHeight },
    expand_all_selector: expand_selector,
    section_count: sections.length,
    interactive_count: globalInteractives.length,
    sections,
    interactives: globalInteractives,
    nav
  };
}
"""


def scout_url(url: str, viewport: dict | None = None, work: Path | None = None) -> dict[str, Any]:
    """Load URL in Playwright and return scout map."""
    from playwright.sync_api import sync_playwright

    vp = viewport or {"width": 720, "height": 1280}
    print(f"[scout] loading {url}", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": int(vp["width"]), "height": int(vp["height"])},
            device_scale_factor=1,
            color_scheme="dark",
            locale="ko-KR",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(1800)
        # hide cursor chrome for cleaner measure
        page.add_style_tag(content=".cursor,.cursor-dot{display:none!important}")
        data = page.evaluate(SCOUT_JS)
        # optional screenshot map
        if work is not None:
            work.mkdir(parents=True, exist_ok=True)
            shot = work / "scout_full.png"
            try:
                page.screenshot(path=str(shot), full_page=False)
                data["screenshot"] = str(shot)
            except Exception as e:
                data["screenshot_error"] = str(e)
        context.close()
        browser.close()

    data["url"] = url
    data["scouted_at"] = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    print(
        f"[scout] sections={data.get('section_count')} "
        f"interactives={data.get('interactive_count')} "
        f"title={data.get('title', '')[:40]}",
        flush=True,
    )
    return data


def _narrate_section(sec: dict, is_first: bool, is_last: bool, site_title: str) -> str:
    """Tutorial VO — short, specific, no filler template phrases."""
    h = (sec.get("heading") or sec.get("id") or "이 구간").strip()
    h = re.sub(r"\s+", " ", h)[:36]
    deck = (sec.get("deck") or "").strip()
    preview = (sec.get("text_preview") or "").strip()
    support = re.sub(r"\s+", " ", deck or preview)
    if support.startswith(h):
        support = support[len(h):].strip(" ·—-")
    support = support[:54]
    bits = []
    if is_first:
        bits.append(f"{site_title or '이 제품'} 투어를 시작합니다.")
    # prefer concrete heading as beat title spoken once
    title = h if h.endswith(("다", "요", ".")) else f"{h}."
    bits.append(title)
    if support:
        if not re.search(r"[.다요]$", support):
            support = support.rstrip("., ") + "."
        bits.append(support)
    if sec.get("has_diagram"):
        bits.append("핵심 노드를 짚어 봅니다.")
    elif sec.get("has_accordion"):
        bits.append("이 섹션을 펼칩니다.")
    if is_last:
        bits.append("투어를 마칩니다.")
    text = re.sub(r"\s+", " ", " ".join(bits)).strip()
    text = re.sub(r"\.\.+", ".", text)
    # policy max 78
    if len(text) > 78:
        text = text[:76].rstrip(" .,") + "."
    return text


def scenario_from_scout(
    scout: dict,
    *,
    max_beats: int = 7,
    voice: str = "ko-KR-SunHiNeural",
    tone: str = "editorial tutorial",
) -> dict:
    """Director: turn scout map into a shootable scenario with real selectors."""
    sections = list(scout.get("sections") or [])
    # Prefer non-tiny sections; keep cover + up to max_beats-1 content
    ranked = sorted(sections, key=lambda s: (-(s.get("height") or 0), s.get("index", 0)))
    # always try to keep document order for narrative
    sections = sections[: max(1, max_beats)]
    if len(sections) > max_beats:
        # cover + top content by height but restore order
        cover = [s for s in sections if s.get("id") in ("cover",) or "cover" in (s.get("selector") or "")]
        rest = [s for s in sections if s not in cover]
        rest = sorted(rest, key=lambda s: (-(s.get("height") or 0), s.get("index", 0)))[: max_beats - len(cover[:1])]
        pick = (cover[:1] + rest) if cover else rest[:max_beats]
        pick.sort(key=lambda s: s.get("index", 0))
        sections = pick

    site_title = (scout.get("title") or "웹사이트").split("—")[0].split("-")[0].strip()
    beats = []
    for i, sec in enumerate(sections):
        clicks = []
        # open accordion in this section first
        for it in sec.get("interactives") or []:
            if it.get("kind") == "accordion":
                clicks.append({"selector": it["selector"], "optional": True, "why": "open accordion"})
                break
        # one more interesting click: card / diagram / cta
        for kind in ("diagram", "card", "cta", "button"):
            for it in sec.get("interactives") or []:
                if it.get("kind") == kind and not any(c["selector"] == it["selector"] for c in clicks):
                    clicks.append({"selector": it["selector"], "optional": True, "why": f"demo {kind}"})
                    break
            if len(clicks) >= 2:
                break

        is_first = i == 0
        is_last = i == len(sections) - 1
        action = "goto_top" if is_first and i == 0 else "scroll_to"
        beat = {
            "id": f"b{i}_{sec.get('id', f'sec{i}')}"[:48],
            "narration": _narrate_section(sec, is_first, is_last, site_title),
            "camera": {
                "action": action if not (is_first and sec.get("id") == "cover") else "goto_top",
                "selector": sec.get("selector") or "body",
            },
            "clicks": clicks,
            "hold_after_ms": 500 if not is_last else 800,
            "scout_ref": {
                "section_id": sec.get("id"),
                "heading": sec.get("heading"),
                "has_diagram": sec.get("has_diagram"),
                "interactive_n": len(sec.get("interactives") or []),
            },
        }
        if beat["camera"]["action"] == "goto_top":
            beat["camera"].pop("selector", None)
            # still set selector for clarity
            beat["camera"]["selector"] = sec.get("selector") or "#cover"
            if sec.get("id") not in (None, "cover") and i > 0:
                beat["camera"]["action"] = "scroll_to"
        if i == 0 and sec.get("id") == "cover":
            beat["camera"] = {"action": "goto_top"}
        elif i == 0:
            beat["camera"] = {"action": "scroll_to", "selector": sec.get("selector") or "body"}
        beats.append(beat)

    if not beats:
        beats = [{
            "id": "b0_fallback",
            "narration": f"{site_title}를 소개합니다. 페이지를 따라가 보겠습니다.",
            "camera": {"action": "goto_top"},
            "clicks": [],
            "hold_after_ms": 600,
        }]

    # ensure each beat has required click when interactives exist
    for b, sec in zip(beats, sections):
        if not b.get("clicks") and (sec.get("interactives") or []):
            it = sec["interactives"][0]
            b["clicks"] = [{
                "selector": it["selector"],
                "optional": False,
                "why": f"force {it.get('kind')}",
            }]
        else:
            for c in b.get("clicks") or []:
                c["optional"] = False
        b["caption"] = re.sub(r"\s+", " ", (sec.get("heading") or b["id"]))[:48]
        b["hold_after_ms"] = 450

    scenario = {
        "id": re.sub(r"[^a-zA-Z0-9_-]+", "_", (scout.get("url") or "site").rstrip("/").split("/")[-1]) or "site",
        "url": scout.get("url"),
        "title": scout.get("title") or site_title,
        "logline": (scout.get("description") or "")[:160],
        "tone": tone,
        "lang": scout.get("lang") or "ko",
        "voice": voice,
        "policy": "tutorial_v1",
        "duration_target_sec": min(90, 8 * len(beats) + 10),
        "viewport": {
            "width": (scout.get("viewport") or {}).get("w") or 720,
            "height": (scout.get("viewport") or {}).get("h") or 1280,
        },
        "expand_all_selector": scout.get("expand_all_selector"),
        "beats": beats,
        "from_scout": True,
        "scout_stats": {
            "sections": scout.get("section_count"),
            "interactives": scout.get("interactive_count"),
        },
    }
    return scenario


def merge_scenario_with_scout(scenario: dict, scout: dict) -> dict:
    """Keep hand-written narrations when present; fix selectors from scout."""
    by_id = {s.get("id"): s for s in scout.get("sections") or []}
    # also index by heading fuzzy
    out_beats = []
    for b in scenario.get("beats") or []:
        cam = dict(b.get("camera") or {})
        sel = cam.get("selector") or ""
        sid = sel.lstrip("#") if sel.startswith("#") else ""
        sec = by_id.get(sid)
        if not sec and sid:
            # try id embedded in beat id
            for k, s in by_id.items():
                if k and k in (b.get("id") or ""):
                    sec = s
                    break
        if sec:
            cam["selector"] = sec.get("selector") or cam.get("selector")
            # inject accordion click if missing
            clicks = list(b.get("clicks") or [])
            if sec.get("has_accordion") and not any("acc" in (c.get("selector") or "") for c in clicks):
                for it in sec.get("interactives") or []:
                    if it.get("kind") == "accordion":
                        clicks.insert(0, {"selector": it["selector"], "optional": True})
                        break
            b = {**b, "camera": cam, "clicks": clicks, "scout_ref": {
                "section_id": sec.get("id"),
                "heading": sec.get("heading"),
            }}
        out_beats.append(b)
    scenario = {**scenario, "beats": out_beats}
    if scout.get("expand_all_selector"):
        scenario["expand_all_selector"] = scout["expand_all_selector"]
    scenario["scout_merged"] = True
    return scenario


def save_scout(scout: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scout, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[scout] wrote {path}", flush=True)
    return path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", type=Path, default=Path("out/scout.json"))
    ap.add_argument("--scenario-out", type=Path, default=None)
    args = ap.parse_args()
    sc = scout_url(args.url, work=args.out.parent)
    save_scout(sc, args.out)
    if args.scenario_out:
        scen = scenario_from_scout(sc)
        args.scenario_out.write_text(json.dumps(scen, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[scout] scenario → {args.scenario_out}")
