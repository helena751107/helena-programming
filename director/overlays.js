// Injected into page during tutorial shoot — cursor + caption + progress
(() => {
  if (window.__helenaDirectorOverlay) return;
  window.__helenaDirectorOverlay = true;

  const css = `
  #hd-cursor {
    position: fixed; width: 22px; height: 22px; margin-left: -11px; margin-top: -11px;
    border: 2px solid #3db8a8; border-radius: 50%;
    background: rgba(61,184,168,.25); box-shadow: 0 0 0 6px rgba(61,184,168,.12);
    pointer-events: none; z-index: 2147483646; transition: left .25s cubic-bezier(.16,1,.3,1), top .25s cubic-bezier(.16,1,.3,1), transform .15s;
    left: 50%; top: 40%;
  }
  #hd-cursor.pulse { transform: scale(1.45); background: rgba(240,199,94,.35); border-color: #f0c75e; }
  #hd-caption {
    position: fixed; left: 16px; right: 16px; bottom: 22px; z-index: 2147483646;
    background: rgba(10,9,8,.82); border: 1px solid rgba(244,239,230,.14);
    border-left: 3px solid #3db8a8; color: #f4efe6;
    font: 600 15px/1.35 "Noto Sans CJK KR","Noto Sans CJK",system-ui,sans-serif;
    padding: 12px 14px; border-radius: 4px; backdrop-filter: blur(8px);
    letter-spacing: -0.01em; word-break: keep-all;
  }
  #hd-chip {
    position: fixed; top: 14px; left: 50%; transform: translateX(-50%);
    z-index: 2147483646; font: 600 11px/1 "Noto Sans CJK KR",system-ui,sans-serif;
    letter-spacing: .14em; text-transform: uppercase;
    color: #0a0908; background: #3db8a8; padding: 8px 12px; border-radius: 999px;
    white-space: nowrap;
  }
  #hd-progress {
    position: fixed; left: 0; top: 0; height: 3px; z-index: 2147483647;
    background: linear-gradient(90deg,#3db8a8,#d4a84b); width: 0%;
    transition: width .35s ease;
  }
  `;
  const st = document.createElement("style");
  st.textContent = css;
  document.documentElement.appendChild(st);

  const progress = document.createElement("div");
  progress.id = "hd-progress";
  document.documentElement.appendChild(progress);

  const chip = document.createElement("div");
  chip.id = "hd-chip";
  chip.textContent = "TUTORIAL";
  document.documentElement.appendChild(chip);

  const caption = document.createElement("div");
  caption.id = "hd-caption";
  caption.textContent = "";
  document.documentElement.appendChild(caption);

  const cursor = document.createElement("div");
  cursor.id = "hd-cursor";
  document.documentElement.appendChild(cursor);

  window.__hd = {
    setCaption(text) {
      caption.textContent = text || "";
      caption.style.opacity = text ? "1" : "0";
    },
    setChip(text) {
      chip.textContent = text || "TUTORIAL";
    },
    setProgress(p) {
      progress.style.width = Math.max(0, Math.min(100, p * 100)) + "%";
    },
    async moveCursorTo(el) {
      if (!el) return;
      const r = el.getBoundingClientRect();
      const x = r.left + r.width / 2;
      const y = r.top + Math.min(r.height / 2, 40);
      cursor.style.left = x + "px";
      cursor.style.top = y + "px";
      await new Promise((r) => setTimeout(r, 280));
    },
    async pulse() {
      cursor.classList.add("pulse");
      await new Promise((r) => setTimeout(r, 180));
      cursor.classList.remove("pulse");
      await new Promise((r) => setTimeout(r, 120));
    },
  };
})();
