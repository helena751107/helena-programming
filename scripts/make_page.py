#!/usr/bin/env python3
"""
make_page.py — 마크다운 백서 → 인터랙티브 HTML + 영상 익스포트
--------------------------------------------------------------------------------
입력:  .md 파일 (백서, 로그, 문서)
출력:  단일 .html 파일 — 클릭 네비게이션 + TTS + 다이어그램 + 인포그래픽 + 영상저장

실행:  python3 scripts/make_page.py 문서.md
열기:  생성된 .html을 브라우저에서 열고 "▶ Play All" 누르면 TTS 읽으면서
       자동 페이지 넘김 → 종료 시 WebM 자동 다운로드

브라우저만 있으면 된다. 서버 불필요.
"""

import os, sys, re, json, argparse
from pathlib import Path


# ── 마크다운 파싱 ──
def parse_markdown_full(text: str) -> list:
    """
    마크다운 → [ {type, content, meta} ] 구조화
    type: h1,h2,h3, p, table, code_mermaid, code_other, list, hr
    """
    blocks = []
    lines = text.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]

        # 헤딩
        m = re.match(r'^(#{1,3})\s+(.+)', line)
        if m:
            level = len(m.group(1))
            blocks.append({"type": f"h{level}", "content": m.group(2).strip()})
            i += 1
            continue

        # 코드 블록
        if line.strip().startswith('```'):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 닫는 ```
            code = '\n'.join(code_lines)
            if lang == 'mermaid':
                blocks.append({"type": "mermaid", "content": code})
            else:
                blocks.append({"type": "code", "content": code, "lang": lang})
            continue

        # 표
        if line.strip().startswith('|') and i+1 < len(lines) and re.match(r'^\|[\s\-:|]+\|$', lines[i+1].strip()):
            table_lines = [line]
            i += 1
            # 헤더 구분선
            if i < len(lines): table_lines.append(lines[i]); i += 1
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i]); i += 1
            blocks.append({"type": "table", "content": '\n'.join(table_lines)})
            continue

        # 리스트
        if re.match(r'^\s*[\-\*]\s+', line):
            list_items = []
            while i < len(lines) and re.match(r'^\s*[\-\*]\s+', lines[i]):
                item = re.sub(r'^\s*[\-\*]\s+', '', lines[i]).strip()
                # 인라인 코드/볼드 제거
                item = re.sub(r'`([^`]+)`', r'\1', item)
                item = re.sub(r'\*\*([^*]+)\*\*', r'\1', item)
                if item: list_items.append(item)
                i += 1
            blocks.append({"type": "list", "content": list_items})
            continue

        # 빈 줄 / 구분선
        if not line.strip() or line.strip().startswith('---'):
            i += 1
            continue

        # 일반 텍스트 (문단 누적)
        para_lines = []
        while i < len(lines) and lines[i].strip() and \
              not lines[i].strip().startswith('#') and \
              not lines[i].strip().startswith('```') and \
              not lines[i].strip().startswith('|') and \
              not re.match(r'^\s*[\-\*]\s+', lines[i]):
            clean = lines[i].strip()
            clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
            clean = re.sub(r'[*_`]', '', clean)
            if clean: para_lines.append(clean)
            i += 1
        if para_lines:
            blocks.append({"type": "p", "content": ' '.join(para_lines)})
        else:
            i += 1

    return blocks


# ── 섹션 그룹화 ──
def group_sections(blocks: list) -> list:
    """h2/h3 기준으로 블록들을 섹션으로 묶음"""
    sections = []
    current = {"title": "", "blocks": []}

    for b in blocks:
        if b["type"] in ("h1",):
            if current["title"] or current["blocks"]:
                sections.append(current)
            current = {"title": b["content"], "blocks": []}
        elif b["type"] in ("h2", "h3"):
            if current["title"] or current["blocks"]:
                sections.append(current)
            current = {"title": b["content"], "blocks": []}
        else:
            current["blocks"].append(b)

    if current["title"] or current["blocks"]:
        sections.append(current)

    return sections[:10]


# ── HTML 생성 ──
def generate_html(sections: list, title: str) -> str:
    """섹션 → 완전한 인터랙티브 HTML 페이지"""
    sections_js = json.dumps([
        {"title": s["title"], "blocks": s["blocks"]}
        for s in sections
    ], ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<title>{title} — Helena Studio</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
:root{{--bg:#0f172a;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#64748b;--accent:#6366f1;--accent2:#818cf8;--gold:#f59e0b;--green:#4ade80}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column}}
/* 헤더 */
.topbar{{position:sticky;top:0;z-index:100;background:var(--bg);border-bottom:1px solid var(--border);padding:.75rem 1rem;display:flex;align-items:center;gap:.75rem}}
.topbar h2{{font-size:1rem;flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}}
.btn{{padding:.5rem 1rem;border:none;border-radius:8px;cursor:pointer;font-size:.8rem;font-weight:700;transition:all .15s}}
.btn:active{{transform:scale(.96)}}
.btn-primary{{background:var(--accent);color:#fff}}
.btn-primary.playing{{background:#dc2626}}
.btn-outline{{background:transparent;border:1px solid var(--border);color:var(--text)}}
.btn-sm{{padding:.35rem .7rem;font-size:.7rem}}
.btn-icon{{background:none;border:none;color:var(--text);cursor:pointer;font-size:1.2rem;padding:.25rem}}

/* 인디케이터 */
.dots{{display:flex;gap:4px;align-items:center}}
.dot{{width:8px;height:8px;border-radius:50%;background:var(--border);transition:all .2s;cursor:pointer}}
.dot.active{{background:var(--accent);transform:scale(1.3)}}
.dot.done{{background:var(--green)}}

/* 메인 */
.main{{flex:1;padding:1.5rem;max-width:800px;margin:0 auto;width:100%}}
.section{{display:none;animation:fadeIn .3s}}
.section.active{{display:block}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:translateY(0)}}}}

/* 카드 */
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.5rem;margin-bottom:1rem}}
.card h3{{font-size:1.3rem;margin-bottom:1rem;color:#f8fafc}}
.card p{{font-size:1rem;line-height:1.7;color:var(--text);margin-bottom:.75rem}}
.card code{{background:#1e1e2e;padding:.15rem .4rem;border-radius:4px;font-size:.85rem;color:#f472b6}}

/* 인포그래픽 카드 */
.info-card{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem;margin:1rem 0}}
.info-item{{background:linear-gradient(135deg,#1e1a3a,#1e293b);border:1px solid var(--border);border-radius:10px;padding:1rem;text-align:center}}
.info-item .num{{font-size:2rem;font-weight:800;color:var(--accent2)}}
.info-item .label{{font-size:.75rem;color:var(--muted);margin-top:.25rem}}

/* 테이블 */
.table-wrap{{overflow-x:auto;margin:1rem 0;border-radius:8px;border:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:.85rem}}
th{{background:var(--accent);color:#fff;padding:.6rem;text-align:left;font-weight:600}}
td{{padding:.5rem .6rem;border-bottom:1px solid var(--border)}}
tr:last-child td{{border-bottom:none}}
tr:nth-child(even){{background:rgba(255,255,255,.02)}}

/* 리스트 */
.list-item{{padding:.6rem 1rem;border-left:2px solid var(--accent);margin:.4rem 0;background:rgba(99,102,241,.05);border-radius:0 6px 6px 0;font-size:.9rem}}

/* 다이어그램 */
.mermaid-wrap{{background:#fff;border-radius:8px;padding:1rem;margin:1rem 0;overflow-x:auto}}

/* 코드 */
.code-block{{background:#1e1e2e;border-radius:8px;padding:1rem;overflow-x:auto;font-size:.8rem;font-family:monospace;color:#a6adc8;margin:1rem 0}}

/* TTS 표시 */
.tts-indicator{{position:fixed;bottom:1rem;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;padding:.5rem 1.5rem;border-radius:20px;font-size:.8rem;display:none;z-index:200;animation:pulse 1s infinite}}
.tts-indicator.show{{display:block}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.7}}}}

/* 진행바 */
.progress{{height:3px;background:var(--border);position:sticky;top:52px;z-index:99}}
.progress-fill{{height:100%;background:var(--accent);transition:width .3s;width:0%}}

/* 내비 */
.nav-row{{display:flex;gap:.5rem;justify-content:center;padding:1rem}}
</style>
</head>
<body>

<div class="topbar">
  <span style="font-size:1.2rem">🎬</span>
  <h2>{title}</h2>
  <div class="dots" id="dots"></div>
  <button class="btn btn-primary" id="playBtn" onclick="togglePlay()">▶ Play All</button>
</div>
<div class="progress"><div class="progress-fill" id="progressFill"></div></div>
<div class="main" id="main"></div>
<div class="tts-indicator" id="ttsIndicator">🔊 TTS 읽는 중...</div>
<div class="nav-row">
  <button class="btn btn-outline btn-sm" onclick="prev()">◀ 이전</button>
  <span style="font-size:.8rem;color:var(--muted);align-self:center" id="pageNum">1/1</span>
  <button class="btn btn-outline btn-sm" id="nextBtn" onclick="next()">다음 ▶</button>
  <button class="btn btn-outline btn-sm" onclick="exportVideo()" title="전체 재생 후 영상 저장">📥 영상저장</button>
</div>

<script>
// ── DATA ──
const SECTIONS = {sections_js};
let idx = 0, playing = false, playTimer = null;

// ── INIT ──
mermaid.initialize({{startOnLoad:false,theme:'default'}});
document.addEventListener('DOMContentLoaded',()=>{{
  renderAll();
  renderDots();
  showSection(0);
}});

// ── RENDER ──
function renderAll() {{
  const main = document.getElementById('main');
  main.innerHTML = SECTIONS.map((s,i) => {{
    let html = `<div class="section" id="sec${{i}}"><div class="card"><h3>${{esc(s.title)}}</h3>`;
    for (const b of s.blocks) {{
      if (b.type==='p') html += `<p>${{esc(b.content)}}</p>`;
      else if (b.type==='mermaid') html += `<div class="mermaid-wrap"><div class="mermaid" id="mm${{i}}">${{esc(b.content)}}</div></div>`;
      else if (b.type==='code') html += `<div class="code-block"><pre>${{esc(b.content)}}</pre></div>`;
      else if (b.type==='table') html += renderTable(b.content);
      else if (b.type==='list') html += b.content.map(l=>`<div class="list-item">${{esc(l)}}</div>`).join('');
    }}
    html += '</div></div>';
    return html;
  }}).join('');
  // Mermaid 렌더링
  setTimeout(async ()=>{{
    const els = document.querySelectorAll('.mermaid');
    for (const el of els) {{
      try {{
        const id = 'mm_'+Math.random().toString(36).slice(2);
        el.id = id;
        const {{svg}} = await mermaid.render(id+'_svg', el.textContent);
        el.innerHTML = svg;
      }} catch(e) {{ el.innerHTML = '<p style=color:red>Diagram error</p>'; }}
    }}
  }},100);
}}

function renderTable(text) {{
  const lines = text.trim().split('\\n');
  if (lines.length<2) return '';
  const parseRow = l => l.split('|').filter(c=>c.trim()).map(c=>c.trim());
  const header = parseRow(lines[0]);
  const alignRow = lines[1]; // 구분선 건너뛰기
  const rows = lines.slice(2).map(parseRow);
  let html = '<div class="table-wrap"><table><thead><tr>';
  header.forEach(h=>html+=`<th>${{esc(h)}}</th>`);
  html+='</tr></thead><tbody>';
  rows.forEach(r=>{{html+='<tr>'; r.forEach(c=>html+=`<td>${{esc(c)}}</td>`); html+='</tr>'}});
  html+='</tbody></table></div>';
  return html;
}}

// ── NAV ──
function showSection(i) {{
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  const el = document.getElementById('sec'+i);
  if (el) el.classList.add('active');
  idx = i;
  updateDots();
  document.getElementById('pageNum').textContent = (i+1)+'/'+SECTIONS.length;
  document.getElementById('progressFill').style.width = ((i+1)/SECTIONS.length*100)+'%';
  document.getElementById('nextBtn').style.display = i>=SECTIONS.length-1 ? 'none' : '';
}}

function next() {{ if (idx<SECTIONS.length-1) showSection(idx+1); }}
function prev() {{ if (idx>0) showSection(idx-1); }}

// ── DOTS ──
function renderDots() {{
  document.getElementById('dots').innerHTML = SECTIONS.map((_,i) =>
    `<div class="dot" onclick="showSection(${{i}})" id="dot${{i}}"></div>`).join('');
}}
function updateDots() {{
  document.querySelectorAll('.dot').forEach((d,i)=>{{
    d.classList.toggle('active', i===idx);
    d.classList.toggle('done', i<idx);
  }});
}}

// ── TTS ──
function speak(text) {{
  return new Promise(resolve => {{
    if (!window.speechSynthesis) {{ setTimeout(resolve,text.length*60); return; }}
    const u = new SpeechSynthesisUtterance(text);
    const voices = speechSynthesis.getVoices();
    const kr = voices.filter(v=>v.lang.startsWith('ko'));
    if (kr.length) u.voice = kr[0];
    u.rate = 0.95; u.pitch = 1;
    u.onend = ()=>resolve();
    u.onerror = ()=>resolve();
    speechSynthesis.speak(u);
  }});
}}

async function readSection(i) {{
  const s = SECTIONS[i];
  const lines = [s.title];
  for (const b of s.blocks) {{
    if (b.type==='p') lines.push(b.content);
    else if (b.type==='list') lines.push(...b.content);
    else if (b.type==='code') lines.push('코드블록');
    else if (b.type==='table') lines.push('표');
  }}
  const text = lines.join('. ').substring(0, 2000);
  document.getElementById('ttsIndicator').classList.add('show');
  showSection(i);
  await speak(text);
  document.getElementById('ttsIndicator').classList.remove('show');
}}

// ── PLAY ALL ──
async function togglePlay() {{
  if (playing) {{ stopPlay(); return; }}
  playing = true;
  const btn = document.getElementById('playBtn');
  btn.textContent = '⏸ Stop'; btn.classList.add('playing');
  document.getElementById('nextBtn').style.display = 'none';

  for (let i=idx; i<SECTIONS.length; i++) {{
    if (!playing) break;
    await readSection(i);
    if (i<SECTIONS.length-1 && playing) await new Promise(r=>setTimeout(r,500));
  }}
  if (playing) {{ stopPlay(); }}
}}

function stopPlay() {{
  playing = false;
  window.speechSynthesis?.cancel();
  const btn = document.getElementById('playBtn');
  btn.textContent = '▶ Play All'; btn.classList.remove('playing');
  document.getElementById('ttsIndicator').classList.remove('show');
  document.getElementById('nextBtn').style.display = idx>=SECTIONS.length-1 ? 'none' : '';
}}

// ── 영상 익스포트 ──
async function exportVideo() {{
  const btn = event.target;
  btn.textContent = '⏳ 녹화중...'; btn.disabled = true;

  const canvas = document.createElement('canvas');
  canvas.width = 720; canvas.height = 1280;
  const ctx = canvas.getContext('2d');
  const stream = canvas.captureStream(30);
  const chunks = [];
  const rec = new MediaRecorder(stream, {{mimeType:'video/webm;codecs=vp9'}});
  rec.ondataavailable = e => chunks.push(e.data);
  rec.start();

  for (let i=0; i<SECTIONS.length; i++) {{
    const s = SECTIONS[i];
    // Draw frame
    const grad = ctx.createLinearGradient(0,0,0,1280);
    grad.addColorStop(0,'#0f172a'); grad.addColorStop(0.5,'#1e1a3a'); grad.addColorStop(1,'#0f172a');
    ctx.fillStyle = grad; ctx.fillRect(0,0,720,1280);
    ctx.fillStyle = '#475569'; ctx.font='12px system-ui'; ctx.fillText('HELENA STUDIO',560,50);
    ctx.fillStyle = '#6366f1'; ctx.font='14px system-ui'; ctx.fillText(`SECTION ${{i+1}}/${{SECTIONS.length}}`,50,130);
    ctx.fillStyle = '#f8fafc'; ctx.font='bold 32px system-ui';
    const tl = wrapText(ctx, s.title, 620);
    tl.forEach((l,j)=>ctx.fillText(l, 50, 200+j*45));

    ctx.fillStyle = '#cbd5e1'; ctx.font='20px system-ui';
    let y = 200+tl.length*45+40;
    for (const b of s.blocks) {{
      let t = '';
      if (b.type==='p') t = b.content;
      else if (b.type==='list') t = b.content.join('. ');
      if (t) {{
        const bl = wrapText(ctx, t.substring(0,300), 620);
        bl.slice(0,8).forEach(l=>{{ if(y<1200) ctx.fillText(l,50,y); y+=30; }});
      }}
    }}

    // Progress bar
    ctx.fillStyle = '#1e293b'; ctx.fillRect(50,1230,620,3);
    ctx.fillStyle = '#6366f1'; ctx.fillRect(50,1230,620*(i+1)/SECTIONS.length,3);
    ctx.fillStyle = '#475569'; ctx.font='11px system-ui'; ctx.fillText(`${{i+1}}/${{SECTIONS.length}}`,660,1255);

    await readSection(i);
    if (i<SECTIONS.length-1) await new Promise(r=>setTimeout(r,300));
  }}

  // End frame
  ctx.fillStyle = '#0f172a'; ctx.fillRect(0,0,720,1280);
  ctx.fillStyle = '#f8fafc'; ctx.font='bold 30px system-ui';
  ctx.fillText('완료',50,600);
  await new Promise(r=>setTimeout(r,2000));

  rec.stop();
  await new Promise(r=>rec.onstop=r);

  const blob = new Blob(chunks,{{type:'video/webm'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'helena-studio.webm';
  a.click();

  btn.textContent = '📥 영상저장'; btn.disabled = false;
}}

function wrapText(ctx, text, maxW) {{
  const words = text.split(' '), lines = []; let line = '';
  for (const w of words) {{
    const t = line ? line+' '+w : w;
    if (ctx.measureText(t).width > maxW && line) {{ lines.push(line); line = w; }}
    else line = t;
  }}
  if (line) lines.push(line);
  return lines;
}}

// ── UTIL ──
function esc(s) {{ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }}
</script>
</body></html>'''


# ── CLI ──
def main():
    ap = argparse.ArgumentParser(description="마크다운 → 인터랙티브 HTML + 영상익스포트")
    ap.add_argument("source", help=".md 파일")
    ap.add_argument("--output","-o", help="출력 .html 경로")
    args = ap.parse_args()

    text = Path(args.source).read_text(encoding="utf-8", errors="replace")
    blocks = parse_markdown_full(text)
    sections = group_sections(blocks)

    if not sections:
        print("❌ 섹션 없음"); return

    # 제목 추출
    title = sections[0]["title"] if sections else Path(args.source).stem

    html = generate_html(sections, title)

    out = args.output or f"/tmp/{Path(args.source).stem}.html"
    Path(out).write_text(html, encoding="utf-8")
    print(f"✅ {out} ({len(sections)}섹션, {len(html)/1024:.0f}KB)")
    print(f"   브라우저에서 열고 '▶ Play All' 누르면 TTS 읽어줌")
    print(f"   '📥 영상저장' 누르면 전체 세션 WebM 저장")


if __name__ == "__main__":
    main()
