// Pro tutorial overlays v5 — Screen Studio / playwright-recast language
// approachMs cursor hold · stable auto-zoom · Ken Burns micro-drift · cinematic dim
// v5: no zoom jitter on re-lock · deliberate click approach · larger cursor
(() => {
  if (window.__helenaDirectorOverlayV5) return;
  window.__helenaDirectorOverlayV5 = true;
  window.__helenaDirectorOverlayV4 = true;
  window.__helenaDirectorOverlayV3 = true;
  window.__helenaDirectorOverlayV2 = true;

  const css = `
  #hd-progress {
    position: fixed; left: 0; top: 0; height: 5px; z-index: 2147483647;
    background: linear-gradient(90deg,#2a9d8f,#e9c46a,#f4a261);
    width: 0%; transition: width .55s cubic-bezier(.16,1,.3,1);
    box-shadow: 0 0 16px rgba(42,157,143,.5);
  }
  #hd-chip {
    position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
    z-index: 2147483647;
    font-family: "Noto Sans CJK KR",system-ui,sans-serif;
    font-size: 13px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase;
    color: #0a0908; background: linear-gradient(90deg,#2a9d8f,#3db8a8);
    padding: 10px 18px; border-radius: 999px; white-space: nowrap;
    box-shadow: 0 8px 28px rgba(0,0,0,.5);
  }
  #hd-vignette {
    position: fixed; inset: 0; z-index: 2147483644; pointer-events: none;
    background: radial-gradient(ellipse at center, transparent 42%, rgba(0,0,0,.38) 100%);
    opacity: 0; transition: opacity .4s;
  }
  #hd-vignette.on { opacity: 1; }
  #hd-hole {
    position: fixed; z-index: 2147483645; pointer-events: none;
    border-radius: 16px;
    box-shadow: 0 0 0 9999px rgba(0,0,0,.48);
    outline: 2.5px solid rgba(61,184,168,.9);
    outline-offset: 5px;
    transition: left .48s cubic-bezier(.16,1,.3,1), top .48s cubic-bezier(.16,1,.3,1),
      width .48s cubic-bezier(.16,1,.3,1), height .48s cubic-bezier(.16,1,.3,1), opacity .3s;
    opacity: 0;
  }
  #hd-ring {
    position: fixed; z-index: 2147483646; pointer-events: none;
    border: 3.5px solid #f0c75e; border-radius: 18px;
    box-shadow:
      0 0 0 7px rgba(240,199,94,.25),
      0 0 0 14px rgba(61,184,168,.12),
      0 0 42px rgba(240,199,94,.5);
    transition: left .45s cubic-bezier(.16,1,.3,1), top .45s cubic-bezier(.16,1,.3,1),
      width .45s cubic-bezier(.16,1,.3,1), height .45s cubic-bezier(.16,1,.3,1), opacity .25s;
    opacity: 0;
  }
  #hd-ring.live {
    animation: hdRingPulse 1.6s ease-in-out infinite;
  }
  @keyframes hdRingPulse {
    0%, 100% { box-shadow: 0 0 0 7px rgba(240,199,94,.22), 0 0 0 14px rgba(61,184,168,.1), 0 0 32px rgba(240,199,94,.42); }
    50% { box-shadow: 0 0 0 11px rgba(240,199,94,.34), 0 0 0 20px rgba(61,184,168,.16), 0 0 56px rgba(240,199,94,.58); }
  }
  #hd-cursor {
    position: fixed; z-index: 2147483647; pointer-events: none;
    width: 52px; height: 52px; margin-left: -6px; margin-top: -4px;
    left: 50%; top: 38%;
    transition: left .72s cubic-bezier(.22,1,.36,1), top .72s cubic-bezier(.22,1,.36,1), transform .18s;
    filter: drop-shadow(0 4px 14px rgba(0,0,0,.65));
    opacity: 1;
  }
  #hd-cursor.fast {
    transition: left .2s cubic-bezier(.16,1,.3,1), top .2s cubic-bezier(.16,1,.3,1), transform .12s;
  }
  #hd-cursor.approach {
    transition: left .65s cubic-bezier(.22,1,.36,1), top .65s cubic-bezier(.22,1,.36,1);
  }
  #hd-cursor svg { display: block; width: 52px; height: 52px; }
  #hd-cursor.pulse { transform: scale(.72); }
  html.hd-zoom-root { overflow: hidden; }
  body.hd-zoomed {
    transition: transform .7s cubic-bezier(.16,1,.3,1);
    will-change: transform;
  }
  @keyframes hdKen {
    0% { transform: scale(var(--hd-s, 1.16)) translate(0,0); }
    100% { transform: scale(var(--hd-s, 1.18)) translate(var(--hd-kx, -0.6%), var(--hd-ky, -0.4%)); }
  }
  body.hd-zoomed.hd-ken {
    animation: hdKen 4.5s ease-in-out infinite alternate;
  }
  #hd-ripple, #hd-ripple2, #hd-ripple3 {
    position: fixed; z-index: 2147483646; pointer-events: none;
    width: 26px; height: 26px; margin: -13px 0 0 -13px; border-radius: 50%;
    opacity: 0;
  }
  #hd-ripple { border: 3px solid #3db8a8; }
  #hd-ripple2 { border: 3px solid #f0c75e; }
  #hd-ripple3 { border: 2px solid #f4efe6; }
  #hd-ripple.on { animation: hdRipple .75s ease-out forwards; }
  #hd-ripple2.on { animation: hdRipple .9s ease-out .1s forwards; }
  #hd-ripple3.on { animation: hdRipple 1.05s ease-out .18s forwards; }
  @keyframes hdRipple {
    0% { transform: scale(.3); opacity: 1; }
    100% { transform: scale(3.8); opacity: 0; }
  }
  #hd-caption {
    position: fixed; left: 16px; right: 16px; bottom: 20px; z-index: 2147483647;
    font-family: "Noto Sans CJK KR","Noto Sans CJK",system-ui,sans-serif;
    background: rgba(8,7,6,.94); border: 1px solid rgba(244,239,230,.2);
    border-left: 5px solid #2a9d8f; color: #f4efe6;
    font-size: 17px; font-weight: 700; line-height: 1.45;
    padding: 14px 16px; border-radius: 10px;
    backdrop-filter: blur(14px); word-break: keep-all;
    opacity: 0; transition: opacity .3s;
    box-shadow: 0 12px 48px rgba(0,0,0,.5);
  }
  #hd-caption .hd-k {
    display: block; font-size: 11px; letter-spacing: .18em; text-transform: uppercase;
    color: #3db8a8; margin-bottom: 6px; font-weight: 800;
  }
  #hd-callout {
    position: fixed; z-index: 2147483646; pointer-events: none;
    font-family: "Noto Sans CJK KR",system-ui,sans-serif;
    font-size: 14px; font-weight: 800; color: #0a0908;
    background: linear-gradient(90deg,#f0c75e,#e8b84a); padding: 8px 14px; border-radius: 8px;
    opacity: 0; transition: opacity .28s, transform .32s;
    transform: translateY(8px);
    box-shadow: 0 8px 22px rgba(0,0,0,.45);
    letter-spacing: .03em;
  }
  #hd-callout.show { opacity: 1; transform: translateY(0); }
  #hd-click-badge {
    position: fixed; z-index: 2147483647; pointer-events: none;
    font-family: system-ui,sans-serif;
    font-size: 12px; font-weight: 900; letter-spacing: .14em;
    color: #0a0908; background: #3db8a8;
    padding: 6px 12px; border-radius: 999px;
    opacity: 0; transition: opacity .22s, transform .28s;
    transform: scale(.8);
    box-shadow: 0 6px 20px rgba(61,184,168,.55);
  }
  #hd-click-badge.show { opacity: 1; transform: scale(1); }
  #hd-letter {
    position: fixed; left: 0; right: 0; z-index: 2147483643; pointer-events: none;
    background: #050403; height: 0; transition: height .5s;
  }
  #hd-letter.top { top: 0; }
  #hd-letter.bot { bottom: 0; }
  #hd-letter.on { height: 28px; }
  `;

  const style = document.createElement("style");
  style.textContent = css;
  document.documentElement.appendChild(style);

  const progress = Object.assign(document.createElement("div"), { id: "hd-progress" });
  const chip = Object.assign(document.createElement("div"), { id: "hd-chip", textContent: "PRODUCT TOUR" });
  const caption = Object.assign(document.createElement("div"), { id: "hd-caption" });
  caption.innerHTML = '<span class="hd-k">STEP</span><span class="hd-t"></span>';
  const vignette = Object.assign(document.createElement("div"), { id: "hd-vignette" });
  const hole = Object.assign(document.createElement("div"), { id: "hd-hole" });
  const ring = Object.assign(document.createElement("div"), { id: "hd-ring" });
  const ripple = Object.assign(document.createElement("div"), { id: "hd-ripple" });
  const ripple2 = Object.assign(document.createElement("div"), { id: "hd-ripple2" });
  const ripple3 = Object.assign(document.createElement("div"), { id: "hd-ripple3" });
  const callout = Object.assign(document.createElement("div"), { id: "hd-callout" });
  const badge = Object.assign(document.createElement("div"), { id: "hd-click-badge", textContent: "CLICK" });
  const letterT = Object.assign(document.createElement("div"), { id: "hd-letter", className: "top" });
  const letterB = Object.assign(document.createElement("div"), { id: "hd-letter", className: "bot" });
  const cursor = Object.assign(document.createElement("div"), { id: "hd-cursor" });
  cursor.innerHTML = `<svg viewBox="0 0 52 52" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M10 5l26 20.2-11.5 2.6L32 44.5l-5.2 2.2-4.9-16.8L10 38.5V5z"
      fill="#f8f4ec" stroke="#0a0908" stroke-width="2.2"/>
    <path d="M10 5l26 20.2-11.5 2.6L32 44.5l-5.2 2.2-4.9-16.8L10 38.5V5z"
      stroke="#f0c75e" stroke-width="1.4" fill="none" opacity=".95"/>
  </svg>`;

  [progress, chip, caption, vignette, hole, ring, ripple, ripple2, ripple3, callout, badge, letterT, letterB, cursor]
    .forEach((el) => document.documentElement.appendChild(el));

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let cursorPos = { x: window.innerWidth * 0.5, y: window.innerHeight * 0.38 };
  let zoomOn = false;
  let lastZoomKey = "";

  function placeBox(el, target, pad = 10) {
    if (!target) {
      el.style.opacity = "0";
      return null;
    }
    const r = target.getBoundingClientRect();
    const left = Math.max(6, r.left - pad);
    const top = Math.max(56, r.top - pad);
    let width = Math.min(window.innerWidth - left - 6, Math.max(52, r.width + pad * 2));
    let height = Math.min(window.innerHeight - top - 100, Math.max(44, r.height + pad * 2));
    width = Math.min(width, window.innerWidth - 28);
    height = Math.min(height, Math.min(400, window.innerHeight * 0.5));
    el.style.left = left + "px";
    el.style.top = top + "px";
    el.style.width = width + "px";
    el.style.height = height + "px";
    el.style.opacity = "1";
    return { left, top, width, height, cx: left + width / 2, cy: top + height / 2 };
  }

  window.__hdZoomLog = window.__hdZoomLog || [];

  window.__hd = {
    version: 5,
    _primary: null,

    setCaption(text, kicker = "STEP") {
      caption.querySelector(".hd-k").textContent = kicker;
      caption.querySelector(".hd-t").textContent = text || "";
      caption.style.opacity = text ? "1" : "0";
    },
    setChip(text) {
      chip.textContent = text || "PRODUCT TOUR";
    },
    setProgress(p) {
      progress.style.width = Math.max(0, Math.min(100, p * 100)) + "%";
    },
    setCinematic(on) {
      letterT.classList.toggle("on", !!on);
      letterB.classList.toggle("on", !!on);
      vignette.classList.toggle("on", !!on);
    },

    _resolveTarget(el) {
      if (!el) return null;
      const r0 = el.getBoundingClientRect();
      const maxRing = Math.min(window.innerHeight * 0.48, 380);
      let target = el;
      if (r0.height > maxRing || r0.width > window.innerWidth * 0.92) {
        target =
          el.querySelector(
            "a.btn.btn-solid, a.btn, .acc-head, button.wc-item, " +
            "h1, h2, .ch-title, button, [role='button'], g.node"
          ) || el;
      }
      const ban = (node) => {
        if (!node || !node.closest) return false;
        return !!(
          node.closest(".stat, .stats, .metric, .metrics, .stat-grid, .kpi, .counters") ||
          node.closest("[data-stat], [class*='stat-'], [class*='metric']")
        );
      };
      if (ban(target)) {
        target =
          document.querySelector("#cover a.btn.btn-solid, a.btn.btn-solid, h1") ||
          target;
      }
      return target;
    },

    _placeCallout(el, label) {
      if (!label || !el) return;
      const r = el.getBoundingClientRect();
      callout.textContent = label;
      let cy = r.top - 48;
      let cx = Math.min(window.innerWidth - 190, Math.max(12, r.left));
      if (r.height > window.innerHeight * 0.45 || r.top < 60) {
        cy = Math.max(60, Math.min(r.top + 12, window.innerHeight - 90));
        cx = Math.min(window.innerWidth - 190, Math.max(14, r.left + 10));
      } else {
        cy = Math.max(60, cy);
      }
      cy = Math.max(56, Math.min(window.innerHeight - 56, cy));
      cx = Math.max(10, Math.min(window.innerWidth - 170, cx));
      callout.style.left = cx + "px";
      callout.style.top = cy + "px";
      callout.classList.add("show");
    },

    /**
     * Stable auto-zoom. Re-lock with same key skips restart (no jitter).
     * scale ~1.16–1.2 + optional Ken Burns micro-drift.
     */
    autoZoom(el, on, strength = 1.18) {
      try {
        if (!on) {
          document.documentElement.classList.remove("hd-zoom-root");
          document.body.classList.remove("hd-zoomed", "hd-ken");
          document.body.style.transform = "";
          document.body.style.transformOrigin = "";
          document.body.style.removeProperty("--hd-s");
          document.body.style.removeProperty("--hd-kx");
          document.body.style.removeProperty("--hd-ky");
          zoomOn = false;
          lastZoomKey = "";
          window.__hdZoomLog.push({ t: Date.now(), on: false });
          return null;
        }
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        const ox = (cx / window.innerWidth) * 100;
        const oy = Math.min(70, Math.max(30, (cy / window.innerHeight) * 100));
        let s = strength;
        if (r.height > window.innerHeight * 0.45) s = Math.min(s, 1.1);
        if (r.height > window.innerHeight * 0.65) s = Math.min(s, 1.06);
        const key = `${Math.round(ox)}:${Math.round(oy)}:${s.toFixed(2)}`;
        // Same focus → keep animation running (no reset jitter)
        if (zoomOn && key === lastZoomKey) {
          return { reused: true, scale: s, ox, oy };
        }
        lastZoomKey = key;
        document.documentElement.classList.add("hd-zoom-root");
        document.body.classList.add("hd-zoomed", "hd-ken");
        document.body.style.transformOrigin = ox + "% " + oy + "%";
        document.body.style.setProperty("--hd-s", String(s));
        document.body.style.setProperty("--hd-kx", (ox > 50 ? "-" : "") + "0.55%");
        document.body.style.setProperty("--hd-ky", (oy > 50 ? "-" : "") + "0.35%");
        document.body.style.transform = `scale(${s})`;
        zoomOn = true;
        const entry = {
          t: Date.now(), on: true, scale: s, ox, oy,
          cx: Math.round(cx), cy: Math.round(cy),
          w: Math.round(r.width), h: Math.round(r.height),
        };
        window.__hdZoomLog.push(entry);
        return entry;
      } catch (e) {
        return null;
      }
    },
    _softZoom(el, on) {
      return this.autoZoom(el, on, on ? 1.18 : 1.0);
    },

    async focus(el, label) {
      if (!el) return null;
      const target = this._resolveTarget(el);
      this._primary = target;
      this.setCinematic(true);
      target.scrollIntoView({ block: "center", behavior: "instant" });
      await sleep(240);
      placeBox(hole, target, 14);
      placeBox(ring, target, 10);
      ring.classList.add("live");
      this._placeCallout(target, label);
      await this.moveCursorTo(target, false);
      this.autoZoom(target, true, 1.18);
      await sleep(360);
      return true;
    },

    /** Hold: re-assert ring/cursor; zoom only if target moved */
    holdFocus(el, label) {
      if (!el) return;
      const target = this._resolveTarget(el);
      this._primary = target;
      placeBox(hole, target, 14);
      placeBox(ring, target, 10);
      ring.classList.add("live");
      this._placeCallout(target, label);
      this.moveCursorTo(target, true);
      this.autoZoom(target, true, 1.16);
    },

    clearFocus() {
      hole.style.opacity = "0";
      ring.style.opacity = "0";
      ring.classList.remove("live");
      callout.classList.remove("show");
      badge.classList.remove("show");
      this.autoZoom(null, false);
      this.setCinematic(false);
      this._primary = null;
    },

    async moveCursorTo(el, fast = false) {
      if (!el) return cursorPos;
      const r = el.getBoundingClientRect();
      const x = r.left + Math.min(Math.max(r.width * 0.55, 16), Math.max(20, r.width - 14));
      const y = r.top + Math.min(Math.max(r.height * 0.42, 14), Math.max(20, r.height - 14));
      cursor.classList.remove("approach");
      if (fast) cursor.classList.add("fast");
      else cursor.classList.remove("fast");
      cursor.style.left = x + "px";
      cursor.style.top = y + "px";
      cursorPos = { x, y };
      await sleep(fast ? 180 : 720);
      cursor.classList.remove("fast");
      return cursorPos;
    },

    /**
     * recast-style: glide → approach hold → click ripple
     * approachMs default 520 (deliberate, not teleport)
     */
    async clickAnim(x, y, approachMs = 520) {
      cursor.classList.add("approach");
      cursor.style.left = x + "px";
      cursor.style.top = y + "px";
      cursorPos = { x, y };
      await sleep(approachMs);
      cursor.classList.remove("approach");
      for (const el of [ripple, ripple2, ripple3]) {
        el.style.left = x + "px";
        el.style.top = y + "px";
        el.classList.remove("on");
      }
      void ripple.offsetWidth;
      ripple.classList.add("on");
      ripple2.classList.add("on");
      ripple3.classList.add("on");
      badge.style.left = x + 20 + "px";
      badge.style.top = y - 32 + "px";
      badge.classList.add("show");
      cursor.classList.add("pulse");
      await sleep(200);
      cursor.classList.remove("pulse");
      await sleep(480);
      badge.classList.remove("show");
    },

    /**
     * Full pro sequence (recast polished click):
     * focus+zoom → cursor approach → hold → multi-ripple → keep focus
     */
    async demoClick(el, label) {
      if (!el) return false;
      const target = this._resolveTarget(el);
      await this.focus(target, label || "Click");
      const pos = await this.moveCursorTo(target, false);
      // Held approach over painted target (recast approachMs)
      await this.clickAnim(pos.x, pos.y, 520);
      this.holdFocus(target, label || "Click");
      await sleep(380);
      return true;
    },

    parkCursor() {
      const x = window.innerWidth * 0.5;
      const y = window.innerHeight * 0.36;
      cursor.style.left = x + "px";
      cursor.style.top = y + "px";
      cursorPos = { x, y };
    },

    drainZoomLog() {
      const log = window.__hdZoomLog || [];
      window.__hdZoomLog = [];
      return log;
    },
  };

  window.__hd.parkCursor();
  window.__hd.setCinematic(true);
})();
