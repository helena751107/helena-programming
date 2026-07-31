#!/usr/bin/env python3
"""
make_page.py — 마크다운 백서 → 프리미엄 인터랙티브 HTML + 영상 익스포트
========================================================================
입력:  .md 파일
출력:  단일 .html — 풀스크린·아코디언·글래스모피즘·애니메이션·Mermaid·영상저장
"""

import os, sys, re, json, argparse
from pathlib import Path


def parse_markdown_full(text: str) -> list:
    blocks = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^(#{1,3})\s+(.+)', line)
        if m:
            blocks.append({"type": f"h{len(m.group(1))}", "content": m.group(2).strip()})
            i += 1; continue
        if line.strip().startswith('```'):
            lang = line.strip()[3:].strip()
            code_lines = []; i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i]); i += 1
            i += 1
            code = '\n'.join(code_lines)
            blocks.append({"type": "mermaid" if lang == 'mermaid' else "code", "content": code, "lang": lang})
            continue
        if line.strip().startswith('|') and i+1 < len(lines) and re.match(r'^\|[\s\-:|]+\|$', lines[i+1].strip()):
            table_lines = [line]; i += 1
            if i < len(lines): table_lines.append(lines[i]); i += 1
            while i < len(lines) and lines[i].strip().startswith('|'): table_lines.append(lines[i]); i += 1
            blocks.append({"type": "table", "content": '\n'.join(table_lines)})
            continue
        if re.match(r'^\s*[\-\*]\s+', line):
            items = []
            while i < len(lines) and re.match(r'^\s*[\-\*]\s+', lines[i]):
                item = re.sub(r'^\s*[\-\*]\s+', '', lines[i]).strip()
                item = re.sub(r'`([^`]+)`', r'\1', item)
                item = re.sub(r'\*\*([^*]+)\*\*', r'\1', item)
                if item: items.append(item)
                i += 1
            blocks.append({"type": "list", "content": items})
            continue
        if not line.strip() or line.strip().startswith('---'): i += 1; continue
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('#') and not lines[i].strip().startswith('```') and not lines[i].strip().startswith('|') and not re.match(r'^\s*[\-\*]\s+', lines[i]):
            clean = lines[i].strip()
            clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
            clean = re.sub(r'[*_`]', '', clean)
            if clean: para_lines.append(clean)
            i += 1
        if para_lines: blocks.append({"type": "p", "content": ' '.join(para_lines)})
        else: i += 1
    return blocks


def group_sections(blocks: list) -> list:
    sections = []; current = {"title": "", "blocks": []}
    for b in blocks:
        if b["type"] == "h1":
            if current["title"] or current["blocks"]: sections.append(current)
            current = {"title": b["content"], "blocks": []}
        elif b["type"] in ("h2", "h3"):
            if current["title"] or current["blocks"]: sections.append(current)
            current = {"title": b["content"], "blocks": []}
        else:
            current["blocks"].append(b)
    if current["title"] or current["blocks"]: sections.append(current)
    return sections[:12]


def generate_html(sections: list, title: str) -> str:
    sections_js = json.dumps([
        {"title": s["title"], "blocks": s["blocks"]} for s in sections
    ], ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#050510; --bg2:#0a0a20; --surface:rgba(255,255,255,0.03);
  --border:rgba(255,255,255,0.06); --border2:rgba(255,255,255,0.1);
  --text:#e8e8f0; --text2:rgba(255,255,255,0.65); --text3:rgba(255,255,255,0.35);
  --accent:#818cf8; --accent2:#6366f1; --accent-glow:rgba(99,102,241,0.3);
  --gold:#f59e0b; --gold-glow:rgba(245,158,11,0.2);
  --green:#34d399; --red:#f87171; --pink:#f472b6; --cyan:#22d3ee;
  --font:'Inter','Noto Sans KR',system-ui,sans-serif;
  --transition:0.5s cubic-bezier(0.16,1,0.3,1);
}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{scroll-behavior:smooth;scroll-snap-type:y mandatory;overflow-y:scroll;height:100vh}}
body{{font-family:var(--font);background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased}}

/* 배경 파티클 */
.bg-particles{{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}}
.bg-particles .orb{{position:absolute;border-radius:50%;filter:blur(100px);opacity:0.08;animation:float 20s infinite ease-in-out}}
.bg-particles .orb:nth-child(1){{width:600px;height:600px;background:var(--accent);top:-200px;left:-100px;animation-delay:0s}}
.bg-particles .orb:nth-child(2){{width:400px;height:400px;background:var(--pink);bottom:-100px;right:-100px;animation-delay:-7s}}
.bg-particles .orb:nth-child(3){{width:500px;height:500px;background:var(--cyan);top:50%;left:50%;animation-delay:-14s}}
@keyframes float{{0%,100%{{transform:translate(0,0) scale(1)}}25%{{transform:translate(100px,-50px) scale(1.1)}}50%{{transform:translate(-50px,100px) scale(0.9)}}75%{{transform:translate(-100px,-100px) scale(1.05)}}}}

/* 내비게이션 바 */
.navbar{{position:fixed;top:0;left:0;right:0;z-index:100;padding:1rem 1.5rem;
  background:rgba(5,5,16,0.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);display:flex;align-items:center;gap:1rem}}
.navbar .logo{{font-weight:800;font-size:1rem;letter-spacing:-0.02em;flex:1}}
.navbar .logo span{{color:var(--accent)}}
.nav-dots{{display:flex;gap:6px}}
.nav-dot{{width:10px;height:10px;border-radius:50%;background:var(--border2);cursor:pointer;transition:all 0.3s;position:relative}}
.nav-dot.active{{background:var(--accent);box-shadow:0 0 12px var(--accent-glow);transform:scale(1.2)}}
.nav-dot.done{{background:var(--green)}}
.nav-btn{{padding:.5rem 1rem;border:1px solid var(--border2);border-radius:8px;
  background:rgba(255,255,255,0.03);color:var(--text);cursor:pointer;
  font-size:.8rem;font-weight:500;transition:all 0.2s;font-family:var(--font)}}
.nav-btn:hover{{border-color:var(--accent);background:rgba(99,102,241,0.1)}}
.nav-btn.primary{{background:var(--accent2);border-color:var(--accent2);color:#fff;font-weight:600}}
.nav-btn.primary:hover{{background:var(--accent);box-shadow:0 0 20px var(--accent-glow)}}
.nav-btn.primary.playing{{background:#dc2626;border-color:#dc2626}}

/* 섹션 */
.slide{{min-height:100vh;display:flex;align-items:center;justify-content:center;
  padding:5rem 2rem 3rem;position:relative;z-index:1;
  scroll-snap-align:start;scroll-snap-stop:always}}
.slide-inner{{width:100%;max-width:900px}}
.slide-num{{font-size:.75rem;font-weight:600;letter-spacing:0.15em;color:var(--accent);
  text-transform:uppercase;margin-bottom:1rem}}
.slide h2{{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:800;line-height:1.2;
  letter-spacing:-0.03em;margin-bottom:2rem;background:linear-gradient(135deg,var(--text) 0%,var(--text2) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.slide h2 .hl{{color:var(--accent);-webkit-text-fill-color:var(--accent)}}

/* 글래스 카드 */
.glass{{background:var(--surface);border:1px solid var(--border);border-radius:20px;
  padding:2rem;margin-bottom:1rem;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  transition:all 0.3s}}
.glass:hover{{border-color:var(--border2);background:rgba(255,255,255,0.04)}}
.glass p{{font-size:1.05rem;line-height:1.75;color:var(--text2);margin-bottom:.75rem}}
.glass p:last-child{{margin-bottom:0}}

/* 아코디언 */
.accordion{{margin-bottom:.5rem;border-radius:14px;overflow:hidden;
  background:var(--surface);border:1px solid var(--border);transition:all 0.3s}}
.accordion-header{{padding:1.2rem 1.5rem;cursor:pointer;display:flex;
  align-items:center;justify-content:space-between;user-select:none;
  font-weight:600;font-size:1rem;transition:all 0.2s}}
.accordion-header:hover{{background:rgba(255,255,255,0.02)}}
.accordion-arrow{{font-size:.7rem;transition:transform 0.3s;color:var(--text3)}}
.accordion.open .accordion-arrow{{transform:rotate(180deg);color:var(--accent)}}
.accordion-body{{max-height:0;overflow:hidden;transition:max-height 0.4s ease,padding 0.4s ease}}
.accordion.open .accordion-body{{max-height:2000px;padding:0 1.5rem 1.5rem}}
.accordion-body p{{font-size:.95rem;line-height:1.7;color:var(--text2)}}

/* 인포그래픽 그리드 */
.info-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.75rem;margin:1.5rem 0}}
.info-tile{{background:linear-gradient(135deg,rgba(99,102,241,0.08),rgba(99,102,241,0.02));
  border:1px solid var(--border);border-radius:16px;padding:1.5rem;text-align:center;
  transition:all 0.3s;position:relative;overflow:hidden}}
.info-tile::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,var(--accent),transparent);opacity:0;transition:opacity 0.3s}}
.info-tile:hover{{border-color:var(--accent);transform:translateY(-2px)}}
.info-tile:hover::before{{opacity:1}}
.info-tile .val{{font-size:2.5rem;font-weight:900;background:linear-gradient(135deg,var(--accent),#c084fc);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.info-tile .lbl{{font-size:.75rem;color:var(--text3);margin-top:.4rem;font-weight:500}}

/* 하이라이트 카드 */
.hl-card{{background:linear-gradient(135deg,rgba(245,158,11,0.08),rgba(245,158,11,0.01));
  border:1px solid rgba(245,158,11,0.15);border-radius:16px;padding:1.5rem;margin:1rem 0}}
.hl-card .icon{{font-size:1.5rem;margin-bottom:.5rem}}
.hl-card p{{font-size:.95rem;line-height:1.7;color:var(--text2)}}
.hl-card strong{{color:var(--gold)}}

/* 테이블 */
.table-glass{{overflow-x:auto;margin:1rem 0;border-radius:14px;border:1px solid var(--border)}}
.table-glass table{{width:100%;border-collapse:collapse;font-size:.9rem}}
.table-glass th{{background:rgba(99,102,241,0.15);color:var(--accent);padding:.75rem 1rem;text-align:left;font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:0.05em}}
.table-glass td{{padding:.7rem 1rem;border-bottom:1px solid var(--border);color:var(--text2)}}
.table-glass tr:last-child td{{border-bottom:none}}
.table-glass tr:hover td{{background:rgba(255,255,255,0.02)}}

/* 리스트 */
.glass-list{{list-style:none}}
.glass-list li{{padding:.8rem 1rem;margin:.3rem 0;border-left:2px solid var(--accent);
  background:rgba(99,102,241,0.03);border-radius:0 8px 8px 0;font-size:.9rem;color:var(--text2);transition:all 0.2s}}
.glass-list li:hover{{border-left-width:4px;background:rgba(99,102,241,0.06)}}

/* 다이어그램 */
.mermaid-glass{{background:rgba(255,255,255,0.98);border-radius:14px;padding:1.5rem;margin:1rem 0;overflow-x:auto}}

/* 코드 */
.code-glass{{background:rgba(0,0,0,0.4);border:1px solid var(--border);border-radius:12px;padding:1.2rem;overflow-x:auto;font-family:'SF Mono','Fira Code',monospace;font-size:.8rem;color:#a6adc8;line-height:1.6;margin:1rem 0}}

/* TTS 인디케이터 */
.tts-badge{{position:fixed;bottom:2rem;left:50%;transform:translateX(-50%);z-index:200;
  background:var(--accent2);color:#fff;padding:.6rem 1.8rem;border-radius:30px;
  font-size:.85rem;font-weight:600;display:none;box-shadow:0 8px 30px var(--accent-glow);
  animation:pulse 1.5s infinite;letter-spacing:-0.01em}}
.tts-badge.on{{display:block}}
@keyframes pulse{{0%,100%{{opacity:1;transform:translateX(-50%) scale(1)}}50%{{opacity:.85;transform:translateX(-50%) scale(1.03)}}}}

/* 진행바 */
.progress-fixed{{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,var(--accent2),var(--accent),#c084fc);z-index:200;transition:width 0.5s ease;border-radius:0 2px 2px 0}}

/* 반응형 */
@media(max-width:768px){{
  .slide{{padding:4rem 1rem 2rem}}
  .glass{{padding:1.25rem}}
  .info-grid{{grid-template-columns:repeat(2,1fr)}}
  .navbar{{padding:.75rem 1rem;gap:.5rem}}
  .nav-btn{{padding:.4rem .7rem;font-size:.7rem}}
}}
</style>
</head>
<body>

<div class="bg-particles">
  <div class="orb"></div><div class="orb"></div><div class="orb"></div>
</div>
<div class="progress-fixed" id="progressBar" style="width:0%"></div>
<div class="navbar">
  <div class="logo">🎬 <span>Helena</span> Studio</div>
  <div class="nav-dots" id="navDots"></div>
  <button class="nav-btn primary" id="playBtn" onclick="togglePlay()">▶ Play All</button>
  <button class="nav-btn" onclick="exportVideo()">📥 저장</button>
</div>
<div class="tts-badge" id="ttsBadge">🔊 읽는 중...</div>

<div id="slides"></div>

<script>
const SECTIONS = {sections_js};
let idx=0,playing=false;

mermaid.initialize({{startOnLoad:false,theme:'base',themeVariables:{{primaryColor:'#818cf8',primaryTextColor:'#1e1b4b',primaryBorderColor:'#6366f1',lineColor:'#6366f1',secondaryColor:'#f0abfc',tertiaryColor:'#e0e7ff'}}}});

document.addEventListener('DOMContentLoaded',()=>{{
  renderSlides();
  renderNavDots();
  updateNav();
  // 초기 섹션 visible 감지
  const obs=new IntersectionObserver((entries)=>{{
    entries.forEach(e=>{{if(e.isIntersecting){{
      const i=parseInt(e.target.dataset.index);
      if(i!==idx){{idx=i;updateNav();}}
    }}}});
  }},{{threshold:0.5}});
  document.querySelectorAll('.slide').forEach(s=>obs.observe(s));
}});

function renderSlides(){{
  document.getElementById('slides').innerHTML=SECTIONS.map((s,i)=>{{
    let html=`<section class="slide" data-index="${{i}}"><div class="slide-inner">`;
    html+=`<div class="slide-num">Section ${{i+1}} / ${{SECTIONS.length}}</div>`;
    html+=`<h2>${{esc(s.title)}}</h2>`;

    // 블록 렌더링
    let accordionIdx=0;
    for(const b of s.blocks){{
      if(b.type==='p') html+=`<div class="glass"><p>${{esc(b.content)}}</p></div>`;
      else if(b.type==='list'){{
        html+=`<ul class="glass-list">`;
        b.content.forEach(l=>html+=`<li>${{esc(l)}}</li>`);
        html+=`</ul>`;
      }}
      else if(b.type==='mermaid'){{
        html+=`<div class="mermaid-glass"><div class="mermaid" id="mm${{i}}">${{esc(b.content)}}</div></div>`;
      }}
      else if(b.type==='table') html+=renderTable(b.content);
      else if(b.type==='code'){{
        html+=`<div class="accordion" id="acc${{i}}_${{accordionIdx}}">`;
        html+=`<div class="accordion-header" onclick="toggleAccordion('acc${{i}}_${{accordionIdx}}')">`;
        html+=`<span>💻 코드 보기</span><span class="accordion-arrow">▼</span></div>`;
        html+=`<div class="accordion-body"><div class="code-glass"><pre>${{esc(b.content)}}</pre></div></div></div>`;
        accordionIdx++;
      }}
    }}

    // 인포그래픽 자동 감지: 숫자 패턴
    const nums=extractNumbers(s);
    if(nums.length>=2){{
      html+=`<div class="info-grid">`;
      nums.forEach(n=>html+=`<div class="info-tile"><div class="val">${{n.val}}</div><div class="lbl">${{n.lbl}}</div></div>`);
      html+=`</div>`;
    }}

    html+=`</div></section>`;
    return html;
  }}).join('');

  // Mermaid
  setTimeout(async()=>{{
    for(const el of document.querySelectorAll('.mermaid')){{
      try{{const{{svg}}=await mermaid.render('mm_'+Math.random().toString(36).slice(2),el.textContent);el.innerHTML=svg}}
      catch(e){{el.innerHTML='<p style=color:var(--red)>Diagram error</p>'}}
    }}
  }},200);
}}

function extractNumbers(s){{
  const nums=[];
  const text=s.title+' '+s.blocks.filter(b=>b.type==='p').map(b=>b.content).join(' ');
  // "28개" "27🔒" 같은 패턴
  const m1=text.match(/(\d+)\s*(개|종|레포|🔒|🌐)/g);
  if(m1) m1.forEach(m=>{{const v=m.match(/(\d+)/);if(v)nums.push({{val:v[1],lbl:m.replace(v[1],'').trim()}});}});
  return nums.slice(0,6);
}}

function renderTable(text){{
  const lines=text.trim().split('\\n');
  if(lines.length<2)return'';
  const parseRow=l=>l.split('|').filter(c=>c.trim()).map(c=>c.trim());
  const header=parseRow(lines[0]);
  const rows=lines.slice(2).map(parseRow);
  let h='<div class="table-glass"><table><thead><tr>';
  header.forEach(c=>h+=`<th>${{esc(c)}}</th>`);
  h+='</tr></thead><tbody>';
  rows.forEach(r=>{{h+='<tr>';r.forEach(c=>h+=`<td>${{esc(c)}}</td>`);h+='</tr>'}});
  h+='</tbody></table></div>';
  return h;
}}

// 아코디언
function toggleAccordion(id){{document.getElementById(id).classList.toggle('open')}}

// 내비
function renderNavDots(){{
  document.getElementById('navDots').innerHTML=SECTIONS.map((_,i)=>
    `<div class="nav-dot" id="dot${{i}}" onclick="goTo(${{i}})" title="${{SECTIONS[i].title.substring(0,30)}}"></div>`).join('');
}}
function updateNav(){{
  document.querySelectorAll('.nav-dot').forEach((d,i)=>{{d.classList.toggle('active',i===idx);d.classList.toggle('done',i<idx)}});
  document.getElementById('progressBar').style.width=((idx+1)/SECTIONS.length*100)+'%';
}}
function goTo(i){{
  document.querySelectorAll('.slide')[i]?.scrollIntoView({{behavior:'smooth'}});
  idx=i;updateNav();
}}

// TTS
function speak(text){{
  return new Promise(resolve=>{{
    if(!window.speechSynthesis){{setTimeout(resolve,text.length*55);return}}
    const u=new SpeechSynthesisUtterance(text.substring(0,2000));
    const voices=speechSynthesis.getVoices();
    const kr=voices.filter(v=>v.lang.startsWith('ko'));
    if(kr.length)u.voice=kr[0];
    u.rate=0.92;u.pitch=1;
    u.onend=()=>resolve();u.onerror=()=>resolve();
    speechSynthesis.speak(u);
  }});
}}
async function readSection(i){{
  const s=SECTIONS[i];
  let text=s.title+'. ';
  for(const b of s.blocks){{
    if(b.type==='p')text+=b.content+'. ';
    else if(b.type==='list')text+=b.content.join('. ')+'. ';
  }}
  document.getElementById('ttsBadge').classList.add('on');
  goTo(i);
  await speak(text);
  document.getElementById('ttsBadge').classList.remove('on');
}}

// Play All
async function togglePlay(){{
  if(playing){{stopPlay();return}}
  playing=true;
  const btn=document.getElementById('playBtn');
  btn.textContent='⏸ Stop';btn.classList.add('playing');
  for(let i=idx;i<SECTIONS.length;i++){{
    if(!playing)break;
    await readSection(i);
    if(i<SECTIONS.length-1&&playing)await new Promise(r=>setTimeout(r,600));
  }}
  if(playing)stopPlay();
}}
function stopPlay(){{
  playing=false;window.speechSynthesis?.cancel();
  const btn=document.getElementById('playBtn');
  btn.textContent='▶ Play All';btn.classList.remove('playing');
  document.getElementById('ttsBadge').classList.remove('on');
}}

// 영상 익스포트
async function exportVideo(){{
  const btn=event.target;btn.textContent='⏳';btn.disabled=true;
  const canvas=document.createElement('canvas');canvas.width=720;canvas.height=1280;
  const ctx=canvas.getContext('2d');
  const stream=canvas.captureStream(30);
  const chunks=[];const rec=new MediaRecorder(stream,{{mimeType:'video/webm;codecs=vp9'}});
  rec.ondataavailable=e=>chunks.push(e.data);rec.start();

  for(let i=0;i<SECTIONS.length;i++){{
    const s=SECTIONS[i];
    const grad=ctx.createLinearGradient(0,0,0,1280);
    grad.addColorStop(0,'#050510');grad.addColorStop(0.5,'#0a0a20');grad.addColorStop(1,'#050510');
    ctx.fillStyle=grad;ctx.fillRect(0,0,720,1280);

    ctx.fillStyle='rgba(255,255,255,0.04)';ctx.beginPath();
    ctx.roundRect(30,30,660,1220,20);ctx.fill();
    ctx.strokeStyle='rgba(255,255,255,0.06)';ctx.lineWidth=1;
    ctx.beginPath();ctx.roundRect(30,30,660,1220,20);ctx.stroke();

    ctx.fillStyle='#818cf8';ctx.font='11px system-ui';ctx.fillText(f'SECTION ${{i+1}}/${{SECTIONS.length}}',60,80);

    ctx.fillStyle='#e8e8f0';ctx.font='bold 30px system-ui';
    const tl=wrapText(ctx,s.title,600);
    tl.forEach((l,j)=>ctx.fillText(l,60,140+j*42));

    ctx.fillStyle='rgba(255,255,255,0.6)';ctx.font='19px system-ui';
    let y=140+tl.length*42+30;
    for(const b of s.blocks){{
      let t='';if(b.type==='p')t=b.content;else if(b.type==='list')t=b.content.join('. ');
      if(t){{const bl=wrapText(ctx,t.substring(0,250),600);bl.slice(0,6).forEach(l=>{{if(y<1180){{ctx.fillText(l,60,y);y+=28}}}});}}
    }}

    ctx.fillStyle='rgba(255,255,255,0.05)';ctx.fillRect(30,1230,660,3);
    ctx.fillStyle='#818cf8';ctx.fillRect(30,1230,660*(i+1)/SECTIONS.length,3);
    ctx.fillStyle='rgba(255,255,255,0.2)';ctx.font='10px system-ui';ctx.fillText(f'${{i+1}}/${{SECTIONS.length}}',650,1255);

    await readSection(i);
    if(i<SECTIONS.length-1)await new Promise(r=>setTimeout(r,300));
  }}
  ctx.fillStyle='#050510';ctx.fillRect(0,0,720,1280);
  ctx.fillStyle='#e8e8f0';ctx.font='bold 28px system-ui';ctx.fillText('✓ 완료',60,600);
  await new Promise(r=>setTimeout(r,1500));
  rec.stop();await new Promise(r=>rec.onstop=r);

  const blob=new Blob(chunks,{{type:'video/webm'}});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='helena-studio.webm';a.click();
  btn.textContent='📥 저장';btn.disabled=false;
}}

function wrapText(ctx,text,maxW){{
  const words=text.split(' '),lines=[];let line='';
  for(const w of words){{const t=line?line+' '+w:w;if(ctx.measureText(t).width>maxW&&line){{lines.push(line);line=w}}else line=t}}
  if(line)lines.push(line);return lines;
}}
function esc(s){{const d=document.createElement('div');d.textContent=s;return d.innerHTML}}
</script>
</body></html>'''


def main():
    ap = argparse.ArgumentParser(description="Markdown -> premium interactive HTML")
    ap.add_argument("source", help=".md file")
    ap.add_argument("--output", "-o", help="output .html path")
    args = ap.parse_args()

    text = Path(args.source).read_text(encoding="utf-8", errors="replace")
    blocks = parse_markdown_full(text)
    sections = group_sections(blocks)
    if not sections: print("❌ 섹션 없음"); return
    title = sections[0]["title"] if sections else Path(args.source).stem
    html = generate_html(sections, title)
    out = args.output or f"/tmp/{Path(args.source).stem}.html"
    Path(out).write_text(html, encoding="utf-8")
    print(f"✅ {out}")
    print(f"   {len(sections)}섹션 · {len(html)/1024:.0f}KB")
    print(f"   풀스크린 · 글래스모피즘 · 아코디언 · Mermaid")
    print(f"   '▶ Play All' → TTS 자동넘김 → '📥 저장' → WebM")


if __name__ == "__main__":
    main()
