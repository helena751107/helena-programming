// Pro tutorial overlays — community-informed (Screen Studio / product demo patterns)
// Spotlight cutout · focus ring · cursor trail · caption · progress
(() => {
  if (window.__helenaDirectorOverlayV2) return;
  window.__helenaDirectorOverlayV2 = true;

  const css = `
  #hd-root { all: initial; }
  #hd-dim {
    position: fixed; inset: 0; z-index: 2147483645;
    pointer-events: none;
    background: rgba(0,0,0,.55);
    opacity: 0; transition: opacity .35s ease;
    /* hole via box-shadow on #hd-hole */
  }
  #hd-hole {
    position: fixed; z-index: 2147483645; pointer-events: none;
    border-radius: 12px;
    box-shadow: 0 0 0 9999px rgba(0,0,0,.58);
    outline: 2px solid rgba(61,184,168,.95);
    outline-offset: 3px;
    transition: left .35s cubic-bezier(.16,1,.3,1), top .35s cubic-bezier(.16,1,.3,1),
      width .35s cubic-bezier(.16,1,.3,1), height .35s cubic-bezier(.16,1,.3,1), opacity .25s;
    opacity: 0;
  }
  #hd-ring {
    position: fixed; z-index: 2147483646; pointer-events: none;
    border: 2px solid #f0c75e; border-radius: 14px;
    box-shadow: 0 0 0 4px rgba(240,199,94,.2), 0 0 28px rgba(61,184,168,.35);
    transition: left .3s cubic-bezier(.16,1,.3,1), top .3s cubic-bezier(.16,1,.3,1),
      width .3s cubic-bezier(.16,1,.3,1), height .3s cubic-bezier(.16,1,.3,1), opacity .2s;
    opacity: 0;
  }
  #hd-cursor {
    position: fixed; z-index: 2147483647; pointer-events: none;
    width: 28px; height: 28px; margin-left: -4px; margin-top: -2px;
    transition: left .28s cubic-bezier(.16,1,.3,1), top .28s cubic-bezier(.16,1,.3,1), transform .12s;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,.45));
  }
  #hd-cursor svg { display: block; width: 28px; height: 28px; }
  #hd-cursor.pulse { transform: scale(.82); }
  #hd-ripple {
    position: fixed; z-index: 2147483646; pointer-events: none;
    width: 18px; height: 18px; margin: -9px 0 0 -9px; border-radius: 50%;
    border: 2px solid #3db8a8; opacity: 0;
  }
  #hd-ripple.on {
    animation: hdRipple .55s ease-out forwards;
  }
  @keyframes hdRipple {
    0% { transform: scale(.4); opacity: .9; }
    100% { transform: scale(2.6); opacity: 0; }
  }
  #hd-caption {
    position: fixed; left: 16px; right: 16px; bottom: 20px; z-index: 2147483647;
    font-family: "Noto Sans CJK KR","Noto Sans CJK",system-ui,sans-serif;
    background: rgba(10,9,8,.88); border: 1px solid rgba(244,239,230,.16);
    border-left: 3px solid #3db8a8; color: #f4efe6;
    font-size: 15px; font-weight: 600; line-height: 1.4;
    padding: 12px 14px 12px 14px; border-radius: 6px;
    backdrop-filter: blur(10px); word-break: keep-all;
    opacity: 0; transition: opacity .25s;
  }
  #hd-caption .hd-k {
    display: block; font-size: 10px; letter-spacing: .16em; text-transform: uppercase;
    color: #3db8a8; margin-bottom: 4px; font-weight: 700;
  }
  #hd-chip {
    position: fixed; top: 12px; left: 50%; transform: translateX(-50%);
    z-index: 2147483647;
    font-family: "Noto Sans CJK KR",system-ui,sans-serif;
    font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
    color: #0a0908; background: linear-gradient(90deg,#3db8a8,#5fd4c4);
    padding: 8px 14px; border-radius: 999px; white-space: nowrap;
    box-shadow: 0 4px 20px rgba(0,0,0,.35);
  }
  #hd-progress {
    position: fixed; left: 0; top: 0; height: 3px; z-index: 2147483647;
    background: linear-gradient(90deg,#3db8a8,#d4a84b,#f0c75e);
    width: 0%; transition: width .4s ease;
  }
  #hd-callout {
    position: fixed; z-index: 2147483646; pointer-events: none;
    font-family: "Noto Sans CJK KR",system-ui,sans-serif;
    font-size: 12px; font-weight: 700; color: #0a0908;
    background: #f0c75e; padding: 5px 10px; border-radius: 4px;
    opacity: 0; transition: opacity .2s, transform .25s;
    transform: translateY(4px);
    box-shadow: 0 4px 14px rgba(0,0,0,.3);
  }
  #hd-callout.show { opacity: 1; transform: translateY(0); }
  `;

  const style = document.createElement("style");
  style.textContent = css;
  document.documentElement.appendChild(style);

  const progress = Object.assign(document.createElement("div"), { id: "hd-progress" });
  const chip = Object.assign(document.createElement("div"), { id: "hd-chip", textContent: "PRODUCT TOUR" });
  const caption = Object.assign(document.createElement("div"), { id: "hd-caption" });
  caption.innerHTML = '<span class="hd-k">STEP</span><span class="hd-t"></span>';
  const hole = Object.assign(document.createElement("div"), { id: "hd-hole" });
  const ring = Object.assign(document.createElement("div"), { id: "hd-ring" });
  const ripple = Object.assign(document.createElement("div"), { id: "hd-ripple" });
  const callout = Object.assign(document.createElement("div"), { id: "hd-callout" });
  const cursor = Object.assign(document.createElement("div"), { id: "hd-cursor" });
  cursor.innerHTML = `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M6 3l16 12.5-7.2 1.6L18 28l-3.2 1.4-3.1-10.5L6 24.5V3z" fill="#f4efe6" stroke="#0a0908" stroke-width="1.4"/>
  </svg>`;

  [progress, chip, caption, hole, ring, ripple, callout, cursor].forEach((el) =>
    document.documentElement.appendChild(el)
  );

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function placeBox(el, target, pad = 8) {
    if (!target) {
      el.style.opacity = "0";
      return null;
    }
    const r = target.getBoundingClientRect();
    const left = Math.max(6, r.left - pad);
    const top = Math.max(6, r.top - pad);
    const width = Math.min(window.innerWidth - left - 6, r.width + pad * 2);
    const height = Math.min(window.innerHeight - top - 6, r.height + pad * 2);
    el.style.left = left + "px";
    el.style.top = top + "px";
    el.style.width = width + "px";
    el.style.height = height + "px";
    el.style.opacity = "1";
    return { left, top, width, height, cx: left + width / 2, cy: top + height / 2 };
  }

  window.__hd = {
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
    async focus(el, label) {
      if (!el) return;
      el.scrollIntoView({ block: "center", behavior: "instant" });
      await sleep(200);
      placeBox(hole, el, 10);
      placeBox(ring, el, 6);
      if (label) {
        const r = el.getBoundingClientRect();
        callout.textContent = label;
        callout.style.left = Math.min(window.innerWidth - 160, Math.max(8, r.left)) + "px";
        callout.style.top = Math.max(8, r.top - 36) + "px";
        callout.classList.add("show");
      }
      await sleep(350);
    },
    clearFocus() {
      hole.style.opacity = "0";
      ring.style.opacity = "0";
      callout.classList.remove("show");
    },
    async moveCursorTo(el) {
      if (!el) return { x: 0, y: 0 };
      const r = el.getBoundingClientRect();
      const x = r.left + Math.min(r.width * 0.55, r.width - 8);
      const y = r.top + Math.min(r.height * 0.45, 36);
      cursor.style.left = x + "px";
      cursor.style.top = y + "px";
      await sleep(300);
      return { x, y };
    },
    async clickAnim(x, y) {
      ripple.style.left = x + "px";
      ripple.style.top = y + "px";
      ripple.classList.remove("on");
      void ripple.offsetWidth;
      ripple.classList.add("on");
      cursor.classList.add("pulse");
      await sleep(140);
      cursor.classList.remove("pulse");
      await sleep(200);
    },
    async demoClick(el, label) {
      await this.focus(el, label || "Click");
      const pos = await this.moveCursorTo(el);
      await this.clickAnim(pos.x, pos.y);
      await sleep(120);
    },
  };
})();
