#!/usr/bin/env python3
"""
Scout v2 — Planner-grade page map for Director.

Community stack (Playwright official + MCP agents):
  1) ARIA snapshot (accessibility tree YAML)  — structure, not CSS soup
  2) getByRole(+name) live verify              — Generator pattern
  3) CSS path fallback                         — shoot / Healer variants
  4) demo_score ranking                        — Arcade/Storylane "one focus per step"

Maps to Playwright Agents:
  Scout  ≈ Planner  (explore → map / plan)
  Shoot  ≈ Generator (execute with verified locators)
  enforce/healer ≈ Healer (retry simpler selectors)

CLI:
  python3 scout.py --url URL --out out/scout.json --scenario-out out/scen.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ── DOM pass (v1 fallback — site-agnostic CSS paths) ─────────────
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

  let sectionEls = [...document.querySelectorAll('section.chapter, section[id], main section[id]')];
  if (sectionEls.length < 2) {
    sectionEls = [...document.querySelectorAll('section[id], [data-ch], main > section')];
  }
  const cover = document.querySelector('#cover, .cover, header.hero, section.hero');
  if (cover && !sectionEls.includes(cover)) sectionEls.unshift(cover);

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
      '[role="button"]', 'input[type="button"]', '.lib-card', '.wc-item'
    ];
    const found = new Set();
    for (const sel of sels) {
      root.querySelectorAll(sel).forEach(el => {
        if (!visible(el) || found.has(el)) return;
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
            : el.matches('.wc-item') ? 'workcenter'
            : el.matches('.pillar, .m-step, .chan') ? 'card'
            : el.matches('.node') ? 'diagram'
            : el.matches('a.btn, a.btn-solid, a.btn-line, .btn') ? 'cta'
            : el.tagName === 'BUTTON' ? 'button'
            : el.tagName === 'A' ? 'link'
            : 'interactive'
        });
      });
    }
    const u = [];
    const sk = new Set();
    for (const it of out) {
      if (sk.has(it.selector)) continue;
      sk.add(it.selector);
      u.push(it);
      if (u.length >= 32) break;
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

  const globalInteractives = interactivesOf(document.body).slice(0, 48);

  const nav = [...document.querySelectorAll('.mast-right a[href^="#"], .chapter-rail a[href^="#"], nav a[href^="#"]')]
    .map(a => ({
      href: a.getAttribute('href'),
      text: clean(a.innerText || a.getAttribute('aria-label') || ''),
      selector: a.id ? ('#' + CSS.escape(a.id)) : cssPath(a)
    }))
    .filter(n => n.href && n.href.length > 1)
    .slice(0, 20);

  const expandBtn = document.querySelector('#accExpand, #accOpenAll, button#accExpand');
  const collapseBtn = document.querySelector('#accCollapse, #accCloseAll, button#accCollapse');
  const expand_selector = expandBtn ? (expandBtn.id ? '#' + CSS.escape(expandBtn.id) : cssPath(expandBtn)) : null;
  const collapse_selector = collapseBtn ? (collapseBtn.id ? '#' + CSS.escape(collapseBtn.id) : cssPath(collapseBtn)) : null;

  return {
    title,
    description: desc,
    url: location.href,
    lang: document.documentElement.lang || 'ko',
    theme: document.documentElement.getAttribute('data-theme') || '',
    viewport: { w: window.innerWidth, h: window.innerHeight, scrollHeight: document.documentElement.scrollHeight },
    expand_all_selector: expand_selector,
    collapse_all_selector: collapse_selector,
    section_count: sections.length,
    interactive_count: globalInteractives.length,
    sections,
    interactives: globalInteractives,
    nav
  };
}
"""


# ── ARIA snapshot parse (Planner / MCP pattern) ──────────────────

_ARIA_ITEM = re.compile(
    r"""^(\s*)-\s+
        (heading|button|link|tab|checkbox|radio|textbox|searchbox|
         combobox|listbox|menuitem|switch|option|img|article|
         banner|contentinfo|navigation|main|region|list|listitem|
         paragraph|blockquote|text|strong|emphasis|code|term|definition)
        (?:\s+"((?:\\.|[^"\\])*)")?
        (?:\s*\[([^\]]*)\])?
        :?\s*(.*)?$
    """,
    re.VERBOSE | re.IGNORECASE,
)

_ROLE_DEMO = {
    "button": 90,
    "link": 70,
    "tab": 85,
    "checkbox": 60,
    "switch": 65,
    "menuitem": 55,
    "option": 75,
    "listbox": 50,
    "searchbox": 40,
    "textbox": 35,
    "heading": 20,
    "img": 30,
}


def parse_aria_snapshot(yaml_text: str) -> list[dict]:
    """Parse Playwright aria_snapshot YAML into flat role nodes."""
    nodes: list[dict] = []
    if not yaml_text:
        return nodes
    for line in yaml_text.splitlines():
        m = _ARIA_ITEM.match(line.rstrip())
        if not m:
            continue
        indent, role, name, attrs, rest = m.groups()
        role = (role or "").lower()
        name = (name or "").replace('\\"', '"').strip()
        depth = len(indent or "") // 2
        meta: dict[str, Any] = {}
        if attrs:
            for part in attrs.split(","):
                part = part.strip()
                if part.startswith("level="):
                    try:
                        meta["level"] = int(part.split("=", 1)[1])
                    except ValueError:
                        pass
                elif part in ("checked", "disabled", "expanded", "selected"):
                    meta[part] = True
                elif part.startswith("expanded=") or part.startswith("checked="):
                    k, _, v = part.partition("=")
                    meta[k] = v.strip()
        # nested /url on same line rare; rest may be empty
        nodes.append({
            "role": role,
            "name": name,
            "depth": depth,
            "attrs": meta,
            "rest": (rest or "").strip(),
        })
    return nodes


def _short_name(name: str, n: int = 48) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    return name[:n]


def _demo_score(node: dict) -> int:
    role = node.get("role") or ""
    name = (node.get("name") or "").lower()
    score = _ROLE_DEMO.get(role, 10)
    # boost tutorial-worthy labels
    for kw, bonus in (
        ("expand", 25), ("collapse", 10), ("install", 30), ("dual", 15),
        ("track", 12), ("system", 12), ("agent", 12), ("center", 12),
        ("funnel", 12), ("공장", 10), ("워크", 10), ("install", 20),
        ("open", 8), ("메뉴", -40), ("테마", -40), ("맨 위", -50),
        ("theme", -40), ("github", -5),
    ):
        if kw in name:
            score += bonus
    # numbered accordion heads "01 …"
    if re.match(r"^\d{2}\b", name) or re.match(r"^[①-⑨]", name):
        score += 20
    if len(name) < 2:
        score -= 30
    return score


def aria_to_interactives(nodes: list[dict]) -> list[dict]:
    """Convert aria nodes → interactive candidates with role locators."""
    out = []
    for n in nodes:
        role = n.get("role")
        name = n.get("name") or ""
        if role not in (
            "button", "link", "tab", "checkbox", "switch",
            "menuitem", "option", "searchbox",
        ):
            continue
        if not name.strip():
            continue
        score = _demo_score(n)
        if score < 15:
            continue
        kind = "button"
        low = name.lower()
        if role == "link":
            kind = "cta" if any(k in low for k in ("install", "explore", "start", "시작", "설치")) else "link"
        elif re.match(r"^\d{2}\b", name) or "track" in low or "dual" in low or "system" in low:
            kind = "accordion"
        elif re.match(r"^[①-⑨]", name) or "가동" in name or "준비" in name or "수동" in name:
            kind = "workcenter"
        elif role == "tab":
            kind = "tab"
        elif "expand" in low:
            kind = "expand"
        elif "collapse" in low:
            kind = "collapse"

        out.append({
            "role": role,
            "name": _short_name(name, 80),
            "name_full": name,
            "kind": kind,
            "demo_score": score,
            # Playwright-style locator descriptor (Generator pattern)
            "locator": {"by": "role", "role": role, "name": _short_name(name, 60)},
            "selector": None,  # filled after live resolve
            "source": "aria",
        })
    # sort by demo score
    out.sort(key=lambda x: -x["demo_score"])
    # dedupe by role+name
    seen = set()
    uniq = []
    for it in out:
        key = (it["role"], it["name"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq


def aria_to_sections(nodes: list[dict]) -> list[dict]:
    """Headings as section anchors from accessibility tree."""
    sections = []
    for i, n in enumerate(nodes):
        if n.get("role") != "heading":
            continue
        name = n.get("name") or ""
        if not name.strip():
            continue
        level = (n.get("attrs") or {}).get("level") or 2
        # find following paragraph as deck
        deck = ""
        for m in nodes[i + 1: i + 6]:
            if m.get("role") == "paragraph" and m.get("name"):
                deck = m["name"]
                break
            if m.get("role") == "heading":
                break
        sections.append({
            "heading": _short_name(name, 60),
            "level": level,
            "deck": _short_name(deck, 200),
            "source": "aria",
        })
    return sections


def live_verify_role(page, role: str, name: str) -> dict | None:
    """
    Generator pattern: verify locator works on live page before shipping.
    Returns {ok, count, selector_hint, box} or None.
    """
    try:
        # exact first, then substring
        loc = page.get_by_role(role, name=name)
        n = loc.count()
        if n == 0 and len(name) > 12:
            # partial: first meaningful token(s)
            token = name.split()[0] if name.split() else name[:8]
            if len(token) >= 2:
                loc = page.get_by_role(role, name=re.compile(re.escape(token), re.I))
                n = loc.count()
        if n == 0:
            return {"ok": False, "count": 0, "role": role, "name": name}
        first = loc.first
        if not first.is_visible():
            return {"ok": False, "count": n, "visible": False, "role": role, "name": name}
        # extract CSS id if present (for shoot querySelector path)
        handle = first.evaluate(
            """el => {
              if (el.id) return {id: el.id, tag: el.tagName.toLowerCase()};
              // nearest id ancestor for section-ish
              let cur = el;
              for (let i = 0; i < 4 && cur; i++) {
                if (cur.id) return {id: cur.id, tag: el.tagName.toLowerCase(), self: false};
                cur = cur.parentElement;
              }
              return {tag: el.tagName.toLowerCase(), text: (el.innerText||'').slice(0,40)};
            }"""
        )
        box = first.bounding_box() or {}
        selector = None
        if handle and handle.get("id") and handle.get("self") is not False and handle.get("tag"):
            # id on self
            if first.evaluate("el => !!el.id"):
                selector = "#" + handle["id"]
        elif handle and handle.get("id") and first.evaluate("el => el.id"):
            selector = "#" + first.evaluate("el => el.id")
        # try id on element directly
        eid = first.evaluate("el => el.id || ''")
        if eid:
            selector = "#" + eid
        return {
            "ok": True,
            "count": n,
            "visible": True,
            "role": role,
            "name": name,
            "selector": selector,
            "box": {
                "x": round(box.get("x", 0)),
                "y": round(box.get("y", 0)),
                "w": round(box.get("width", 0)),
                "h": round(box.get("height", 0)),
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "role": role, "name": name}


def _merge_aria_into_dom(dom: dict, aria_nodes: list[dict], verified: list[dict]) -> dict:
    """Enrich DOM scout with ARIA roles + verified locators."""
    aria_inter = aria_to_interactives(aria_nodes)
    # attach verify results
    by_key = {(v["role"], v["name"]): v for v in verified if v.get("ok")}
    for it in aria_inter:
        key = (it["role"], it["name"])
        # also try full name
        v = by_key.get(key) or by_key.get((it["role"], it.get("name_full", "")))
        if not v:
            # fuzzy: verified name startswith
            for (r, nm), vv in by_key.items():
                if r == it["role"] and (nm in it.get("name_full", "") or it["name"] in nm):
                    v = vv
                    break
        if v:
            it["verified"] = True
            it["selector"] = v.get("selector") or it.get("selector")
            it["box"] = v.get("box")
            it["live_count"] = v.get("count")
        else:
            it["verified"] = False

    def _text_match(a: str, b: str) -> float:
        """Strict overlap score 0..1 — avoid Install CTA ↔ Install accordion mixups."""
        a, b = (a or "").lower().strip(), (b or "").lower().strip()
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if a in b or b in a:
            # require substantial containment (not one shared token)
            shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
            if len(shorter) >= 8 and len(shorter) / max(1, len(longer)) >= 0.45:
                return 0.85
            return 0.2
        # token Jaccard with min token len 2
        ta = {t for t in re.split(r"[\s·|/+,]+", a) if len(t) >= 2}
        tb = {t for t in re.split(r"[\s·|/+,]+", b) if len(t) >= 2}
        if not ta or not tb:
            return 0.0
        inter = ta & tb
        if not inter:
            return 0.0
        # penalize single generic token matches (install, system, …)
        if len(inter) == 1 and next(iter(inter)) in {
            "install", "system", "agents", "track", "map", "github", "open", "all"
        }:
            return 0.15
        return len(inter) / max(len(ta), len(tb))

    # attach role locators onto matching DOM interactives by strict text match
    dom_inter = list(dom.get("interactives") or [])
    for d in dom_inter:
        dtxt = d.get("text") or ""
        best = None
        best_score = 0.0
        for a in aria_inter:
            an = a.get("name_full") or a.get("name") or ""
            m = _text_match(dtxt, an)
            if m >= 0.5 and m > best_score:
                best_score = m
                best = a
        if best:
            d["role"] = best.get("role") or d.get("role")
            d["name"] = best.get("name")
            d["locator"] = best.get("locator")
            d["demo_score"] = best.get("demo_score")
            d["verified"] = best.get("verified", False)
            d["source"] = "dom+aria"
            d["match_score"] = round(best_score, 2)
            if best.get("selector") and not d.get("selector"):
                d["selector"] = best["selector"]
        else:
            d.setdefault(
                "demo_score",
                40 if d.get("kind") in ("accordion", "cta", "diagram", "workcenter") else 20,
            )
            d.setdefault("source", "dom")

    # inject high-score aria-only interactives missing from DOM
    existing_sel = {d.get("selector") for d in dom_inter}
    existing_names = {(d.get("name") or d.get("text") or "").lower() for d in dom_inter}
    for a in aria_inter:
        if not a.get("verified"):
            continue
        nm = (a.get("name") or "").lower()
        if any(nm and (nm in en or en in nm) for en in existing_names if en):
            continue
        entry = {
            "tag": a["role"],
            "selector": a.get("selector") or f"role={a['role']}[name=\"{a['name']}\"]",
            "text": a.get("name"),
            "role": a["role"],
            "name": a.get("name"),
            "locator": a.get("locator"),
            "kind": a.get("kind"),
            "demo_score": a.get("demo_score"),
            "verified": True,
            "source": "aria",
            "box": a.get("box"),
        }
        if entry["selector"] not in existing_sel:
            dom_inter.append(entry)
            existing_sel.add(entry["selector"])

    # sort by demo_score
    dom_inter.sort(key=lambda x: -(x.get("demo_score") or 0))
    dom["interactives"] = dom_inter[:56]
    dom["interactive_count"] = len(dom["interactives"])
    dom["aria_interactives"] = aria_inter[:40]
    dom["verified_count"] = sum(1 for d in dom_inter if d.get("verified"))

    # enrich sections with aria headings
    aria_secs = aria_to_sections(aria_nodes)
    for sec in dom.get("sections") or []:
        h = (sec.get("heading") or "").lower()
        for a in aria_secs:
            ah = (a.get("heading") or "").lower()
            if ah and (ah in h or h in ah):
                if a.get("deck") and not sec.get("deck"):
                    sec["deck"] = a["deck"]
                sec["aria_heading"] = a["heading"]
                break
        # re-rank section interactives
        inter = sec.get("interactives") or []
        for d in inter:
            dtxt = (d.get("text") or "").lower()
            for a in aria_inter:
                an = (a.get("name_full") or a.get("name") or "").lower()
                if an and dtxt and (an in dtxt or dtxt[:20] in an):
                    d["locator"] = a.get("locator")
                    d["name"] = a.get("name")
                    d["role"] = a.get("role")
                    d["demo_score"] = a.get("demo_score")
                    d["verified"] = a.get("verified")
                    break
        inter.sort(key=lambda x: -(x.get("demo_score") or 0))
        sec["interactives"] = inter
        sec["has_accordion"] = any(
            i.get("kind") == "accordion" or (i.get("locator") or {}).get("role") == "button"
            and re.match(r"^\d{2}\b", i.get("name") or i.get("text") or "")
            for i in inter
        )

    dom["aria_section_headings"] = aria_secs
    return dom


def write_scout_plan(scout: dict, path: Path) -> Path:
    """Planner-style Markdown plan (Playwright Agents artifact)."""
    lines = [
        f"# Scout Plan — {scout.get('title') or scout.get('url')}",
        "",
        f"**URL:** {scout.get('url')}",
        f"**Engine:** scout v{scout.get('scout_version', 2)} (ARIA + DOM + live verify)",
        f"**Sections:** {scout.get('section_count')} · "
        f"**Interactives:** {scout.get('interactive_count')} · "
        f"**Verified:** {scout.get('verified_count', 0)}",
        "",
        "## Application Overview",
        "",
        (scout.get("description") or "(no meta description)")[:400],
        "",
        "## Demo Scenarios (ranked)",
        "",
    ]
    for i, it in enumerate((scout.get("interactives") or [])[:12], 1):
        loc = it.get("locator") or {}
        lines.append(
            f"### {i}. {it.get('kind', 'click')} — {it.get('text') or it.get('name') or it.get('selector')}"
        )
        lines.append("")
        lines.append(f"- **demo_score:** {it.get('demo_score', '?')}")
        lines.append(f"- **selector:** `{it.get('selector')}`")
        if loc:
            lines.append(
                f"- **role locator:** `getByRole({loc.get('role')!r}, name={loc.get('name')!r})`"
            )
        lines.append(f"- **verified:** {it.get('verified', False)} · source={it.get('source')}")
        lines.append("")
        lines.append("**Steps:**")
        lines.append(f"1. Scroll to target")
        lines.append(f"2. Spotlight + cursor path")
        lines.append(f"3. Click `{it.get('selector') or loc}`")
        lines.append("")
    lines.append("## Sections")
    lines.append("")
    for sec in scout.get("sections") or []:
        lines.append(f"- `{sec.get('selector')}` — **{sec.get('heading')}** "
                     f"({len(sec.get('interactives') or [])} interactives)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def scout_url(url: str, viewport: dict | None = None, work: Path | None = None) -> dict[str, Any]:
    """
    Load URL → DOM map + ARIA snapshot + live role verification.
    Scout v2 — community-informed Planner grade.
    """
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
        page.goto(url, wait_until="load", timeout=120_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        page.wait_for_timeout(900)
        page.add_style_tag(content=".cursor,.cursor-dot{display:none!important}")

        # 1) DOM pass
        data = page.evaluate(SCOUT_JS)

        # 2) ARIA snapshot pass (Playwright MCP / Agents core)
        aria_yaml = ""
        try:
            aria_yaml = page.aria_snapshot() or ""
            data["aria_snapshot_chars"] = len(aria_yaml)
            print(f"[scout] aria_snapshot {len(aria_yaml)} chars", flush=True)
        except Exception as e:
            data["aria_snapshot_error"] = str(e)
            print(f"[scout] ! aria_snapshot failed: {e}", flush=True)

        aria_nodes = parse_aria_snapshot(aria_yaml)
        data["aria_node_count"] = len(aria_nodes)

        # 3) Live verify top role candidates (Generator pattern)
        candidates = aria_to_interactives(aria_nodes)[:28]
        verified: list[dict] = []
        for c in candidates:
            # use fuller name for getByRole when available
            nm = c.get("name_full") or c.get("name") or ""
            # Playwright name match: use shorter unique fragment for long accordion labels
            name_for_role = nm
            # accordion buttons often have multi-line accessible name — use heading slice
            if len(nm) > 40:
                # prefer trailing Korean/title part after digits
                m = re.search(r"\d{2}\s+\S+\s+(.+)", nm)
                if m:
                    name_for_role = m.group(1).strip()[:40]
                else:
                    name_for_role = nm[:40]
            v = live_verify_role(page, c["role"], name_for_role)
            if v and v.get("ok"):
                v["name"] = c.get("name")  # keep short key
                v["name_used"] = name_for_role
                verified.append(v)
                c["verified"] = True
                c["selector"] = v.get("selector")
                c["box"] = v.get("box")
            else:
                # retry with original short name
                v2 = live_verify_role(page, c["role"], c.get("name") or nm[:30])
                if v2 and v2.get("ok"):
                    v2["name"] = c.get("name")
                    verified.append(v2)
                    c["verified"] = True
                    c["selector"] = v2.get("selector")
                    c["box"] = v2.get("box")
                else:
                    c["verified"] = False
        print(
            f"[scout] live-verify {sum(1 for c in candidates if c.get('verified'))}/{len(candidates)} roles",
            flush=True,
        )

        data = _merge_aria_into_dom(data, aria_nodes, verified)
        data["scout_version"] = 2
        data["scout_engine"] = "aria+dom+live_verify"

        # optional artifacts
        if work is not None:
            work.mkdir(parents=True, exist_ok=True)
            if aria_yaml:
                (work / "scout.aria.yml").write_text(aria_yaml, encoding="utf-8")
                data["aria_snapshot_file"] = str(work / "scout.aria.yml")
            shot = work / "scout_full.png"
            try:
                page.screenshot(path=str(shot), full_page=False)
                data["screenshot"] = str(shot)
            except Exception as e:
                data["screenshot_error"] = str(e)
            plan = write_scout_plan(data, work / "scout_plan.md")
            data["plan_file"] = str(plan)
            print(f"[scout] plan → {plan}", flush=True)

        context.close()
        browser.close()

    data["url"] = url
    from datetime import datetime, timezone
    data["scouted_at"] = datetime.now(timezone.utc).isoformat()
    print(
        f"[scout] v2 sections={data.get('section_count')} "
        f"interactives={data.get('interactive_count')} "
        f"verified={data.get('verified_count')} "
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
    sections = sections[: max(1, max_beats)]
    if len(sections) > max_beats:
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
        inter = sorted(
            sec.get("interactives") or [],
            key=lambda x: -(x.get("demo_score") or 0),
        )
        # open accordion first
        for it in inter:
            if it.get("kind") == "accordion":
                clicks.append(_click_from_interactive(it, "open accordion"))
                break
        # one more: diagram / workcenter / cta / card / button
        for kind in ("diagram", "workcenter", "cta", "card", "button", "tab"):
            for it in inter:
                if it.get("kind") == kind and not any(
                    c.get("selector") == it.get("selector") for c in clicks
                ):
                    clicks.append(_click_from_interactive(it, f"demo {kind}"))
                    break
            if len(clicks) >= 2:
                break

        is_first = i == 0
        is_last = i == len(sections) - 1
        beat = {
            "id": f"b{i}_{sec.get('id', f'sec{i}')}"[:48],
            "narration": _narrate_section(sec, is_first, is_last, site_title),
            "camera": {
                "action": "goto_top" if is_first and sec.get("id") == "cover" else "scroll_to",
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

    for b, sec in zip(beats, sections):
        if not b.get("clicks") and (sec.get("interactives") or []):
            it = sorted(sec["interactives"], key=lambda x: -(x.get("demo_score") or 0))[0]
            b["clicks"] = [_click_from_interactive(it, f"force {it.get('kind')}")]
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
        "collapse_all_selector": scout.get("collapse_all_selector"),
        "beats": beats,
        "from_scout": True,
        "scout_stats": {
            "sections": scout.get("section_count"),
            "interactives": scout.get("interactive_count"),
            "verified": scout.get("verified_count"),
            "scout_version": scout.get("scout_version", 2),
        },
    }
    return scenario


def _click_from_interactive(it: dict, why: str) -> dict:
    c: dict[str, Any] = {
        "selector": it.get("selector") or "",
        "optional": False,
        "why": why,
    }
    if it.get("locator"):
        c["locator"] = it["locator"]
    if it.get("role") and it.get("name"):
        c["role"] = it["role"]
        c["name"] = it["name"]
    if it.get("verified"):
        c["scout_verified"] = True
    return c


def merge_scenario_with_scout(scenario: dict, scout: dict) -> dict:
    """Keep hand-written narrations; inject verified role locators from scout."""
    by_id = {s.get("id"): s for s in scout.get("sections") or []}
    # global verified interactives by kind
    global_inter = scout.get("interactives") or []
    out_beats = []
    for b in scenario.get("beats") or []:
        cam = dict(b.get("camera") or {})
        sel = cam.get("selector") or ""
        sid = sel.lstrip("#") if sel.startswith("#") else ""
        sec = by_id.get(sid)
        if not sec and sid:
            for k, s in by_id.items():
                if k and k in (b.get("id") or ""):
                    sec = s
                    break
        clicks = list(b.get("clicks") or [])
        if sec:
            cam["selector"] = sec.get("selector") or cam.get("selector")
            has_open = any(
                any(k in (c.get("selector") or "").lower() for k in ("acc", "-head", "summary", "toggle"))
                or "open accordion" in (c.get("why") or "").lower()
                or c.get("role") == "button" and c.get("name")
                for c in clicks
            )
            if sec.get("has_accordion") and not has_open:
                for it in sec.get("interactives") or []:
                    if it.get("kind") == "accordion":
                        clicks.insert(0, _click_from_interactive(it, "open accordion"))
                        break
        # enrich existing clicks with role locators from scout map
        for c in clicks:
            if c.get("locator") or (c.get("role") and c.get("name")):
                continue
            csel = c.get("selector") or ""
            cwhy = (c.get("why") or "").lower()
            for it in (sec.get("interactives") if sec else None) or global_inter:
                if csel and it.get("selector") == csel:
                    if it.get("locator"):
                        c["locator"] = it["locator"]
                    if it.get("role") and it.get("name"):
                        c["role"] = it["role"]
                        c["name"] = it["name"]
                    if it.get("verified"):
                        c["scout_verified"] = True
                    break
                # match by why/kind
                if "accordion" in cwhy and it.get("kind") == "accordion":
                    if it.get("locator"):
                        c["locator"] = it["locator"]
                    if it.get("role"):
                        c["role"] = it["role"]
                        c["name"] = it.get("name")
                    if it.get("selector") and not csel:
                        c["selector"] = it["selector"]
                    break
        # dedupe
        seen_sel: set[str] = set()
        deduped = []
        for c in clicks:
            s = c.get("selector") or json.dumps(c.get("locator") or {}, sort_keys=True)
            if s in seen_sel:
                continue
            seen_sel.add(s)
            deduped.append(c)
        b = {
            **b,
            "camera": cam,
            "clicks": deduped,
            "scout_ref": {
                "section_id": (sec or {}).get("id"),
                "heading": (sec or {}).get("heading"),
            } if sec else b.get("scout_ref"),
        }
        out_beats.append(b)
    scenario = {**scenario, "beats": out_beats}
    if scout.get("expand_all_selector"):
        scenario["expand_all_selector"] = scout["expand_all_selector"]
    if scout.get("collapse_all_selector"):
        scenario["collapse_all_selector"] = scout["collapse_all_selector"]
    scenario["scout_merged"] = True
    scenario["scout_version"] = scout.get("scout_version", 2)
    return scenario


def save_scout(scout: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scout, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[scout] wrote {path}", flush=True)
    return path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Scout v2 — ARIA + DOM + live verify")
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
