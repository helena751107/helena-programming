#!/usr/bin/env python3
"""ParkSyTTS 모델 업로드 서버 — PC 웹브라우저에서 모델 파일을 폰으로 전송.

사용법:
  python3 upload_server.py              # 0.0.0.0:8765
  python3 upload_server.py --port 9999  # 다른 포트
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
from html import escape
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
for sub in ["gpt", "sovits", "ref"]:
    (MODEL_DIR / sub).mkdir(exist_ok=True)

# ── filename → subdirectory routing ──────────────────────────────────────────
ROUTES = [
    (r"parksy_v2-e15\.ckpt", "gpt"),
    (r"parksy_v2_e8_s256\.pth", "sovits"),
    (r"seg004\.wav", "ref"),
]

STATUS = {}


def route_file(filename: str) -> str | None:
    for pattern, subdir in ROUTES:
        if re.search(pattern, filename):
            return subdir
    return None


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ParkSyTTS 모델 업로드</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;
       background:#0f0f0f;color:#e0e0e0;min-height:100vh;
       display:flex;align-items:center;justify-content:center}
  .card{background:#1a1a1a;border-radius:16px;padding:32px 28px;
        max-width:520px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,.5)}
  h1{font-size:22px;margin-bottom:6px}
  .sub{color:#888;font-size:13px;margin-bottom:24px}
  .drop{display:flex;align-items:center;justify-content:center;
        border:2px dashed #444;border-radius:12px;padding:48px 16px;
        cursor:pointer;transition:border .2s;margin-bottom:20px}
  .drop.dragover{border-color:#6cf;background:#1a2a3a}
  .drop p{color:#aaa;font-size:15px;text-align:center}
  .drop input{display:none}
  .checklist{list-style:none;margin-bottom:20px}
  .checklist li{display:flex;align-items:center;gap:10px;padding:8px 0;
                border-bottom:1px solid #2a2a2a;font-size:14px}
  .checklist .icon{width:22px;text-align:center;font-size:15px}
  .checklist .ok{color:#4caf50}.checklist .wait{color:#555}
  .checklist .name{flex:1;color:#ccc}
  .checklist .size{color:#666;font-size:12px}
  .status{margin-top:12px;padding:10px 14px;border-radius:8px;
          font-size:13px;display:none}
  .status.success{display:block;background:#1b3a1b;color:#6f6}
  .status.error{display:block;background:#3a1b1b;color:#f66}
  .ip{font-size:12px;color:#555;margin-top:18px;text-align:center}
  button{margin-top:16px;width:100%;padding:12px;border:none;
         border-radius:10px;background:#2563eb;color:#fff;
         font-size:15px;cursor:pointer;transition:opacity .2s}
  button:disabled{opacity:.4;cursor:default}
  button:hover:not(:disabled){opacity:.85}
</style>
</head>
<body>
<div class="card">
  <h1>🎙 ParkSyTTS v1 · 모델 업로드</h1>
  <p class="sub">PC에서 모델 3개를 끌어다 놓거나 클릭해서 선택</p>
  <div class="drop" id="drop">
    <p>📂 여기에 파일을 드래그하거나<br>클릭해서 선택하세요</p>
    <input type="file" id="fileInput" multiple accept=".ckpt,.pth,.wav">
  </div>
  <ul class="checklist" id="checklist">
    <li id="row-gpt"><span class="icon wait">⬜</span><span class="name">parksy_v2-e15.ckpt</span><span class="size">149MB</span></li>
    <li id="row-sovits"><span class="icon wait">⬜</span><span class="name">parksy_v2_e8_s256.pth</span><span class="size">165MB</span></li>
    <li id="row-ref"><span class="icon wait">⬜</span><span class="name">seg004.wav</span><span class="size">ref</span></li>
  </ul>
  <div class="status" id="status"></div>
  <button id="btn" disabled>3개 파일을 모두 업로드하세요</button>
  <p class="ip">서버: PHONE_IP:PORT</p>
</div>
<script>
const EXPECTED = {
  gpt:    {name:'parksy_v2-e15.ckpt',     row:'row-gpt'},
  sovits: {name:'parksy_v2_e8_s256.pth',  row:'row-sovits'},
  ref:    {name:'seg004.wav',             row:'row-ref'},
};
let done = {gpt:false, sovits:false, ref:false};

function updateUI(){
  const all = done.gpt && done.sovits && done.ref;
  document.getElementById('btn').disabled = !all;
  document.getElementById('btn').textContent = all
    ? '✅ 모든 모델 준비 완료! 이제 TTS 사용 가능'
    : '3개 파일을 모두 업로드하세요';
}

async function upload(file){
  const key = Object.entries(EXPECTED).find(([,v])=>file.name.includes(v.name))?.[0];
  const row = key ? document.getElementById(EXPECTED[key].row) : null;
  const icon = row?.querySelector('.icon');
  if(icon){icon.textContent='⬆️';icon.className='icon';}

  const form = new FormData();
  form.append('file', file);

  try{
    const res = await fetch('/upload', {method:'POST',body:form});
    const data = await res.json();
    if(data.ok){
      if(key){done[key]=true;if(icon){icon.textContent='✅';icon.className='icon ok';}}
      updateUI();
      showStatus(`✔ ${file.name} 저장 완료 (→ models/${data.subdir}/)`, 'success');
    }else{
      if(icon){icon.textContent='❌';icon.className='icon';}
      showStatus(`✖ ${file.name}: ${data.error}`, 'error');
    }
  }catch(e){
    if(icon){icon.textContent='❌';icon.className='icon';}
    showStatus(`✖ ${file.name}: 네트워크 오류 - ${e.message}`, 'error');
  }
}

function showStatus(msg, cls){
  const s = document.getElementById('status');
  s.textContent=msg;s.className='status '+cls;
}

document.getElementById('drop').onclick = ()=>document.getElementById('fileInput').click();
document.getElementById('fileInput').onchange = (e)=>{
  for(const f of e.target.files) upload(f);
};

const drop = document.getElementById('drop');
['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('dragover')}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('dragover')}));
drop.addEventListener('drop', e=>{
  for(const f of e.dataTransfer.files) upload(f);
});
</script>
</body>
</html>"""


class UploadHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/upload":
            self._serve_html()
        elif parsed.path == "/status":
            self._serve_json(STATUS)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/upload":
            self.send_error(404)
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._serve_json({"ok": False, "error": "multipart/form-data 필요"})
            return

        # parse multipart manually (no extra deps)
        boundary = content_type.split("boundary=")[-1].encode()
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        filename, data = self._parse_multipart(body, boundary)
        if not filename or not data:
            self._serve_json({"ok": False, "error": "파일을 찾을 수 없습니다"})
            return

        subdir = route_file(filename)
        if not subdir:
            self._serve_json({
                "ok": False,
                "error": f"알 수 없는 파일: {filename}. parksy_v2-e15.ckpt / parksy_v2_e8_s256.pth / seg004.wav 만 업로드 가능",
            })
            return

        dest = MODEL_DIR / subdir / filename
        dest.write_bytes(data)
        size_mb = len(data) / (1024 * 1024)
        print(f"  ✅ {filename} → models/{subdir}/ ({size_mb:.1f}MB)")
        STATUS[subdir] = {"file": filename, "size_mb": round(size_mb, 1)}
        self._serve_json({"ok": True, "subdir": subdir, "size_mb": round(size_mb, 1)})

    def _serve_html(self):
        ip = self.headers.get("Host", "0.0.0.0:8765")
        body = HTML.replace("PHONE_IP:PORT", escape(ip)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self, obj):
        import json
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_multipart(self, body: bytes, boundary: bytes):
        parts = body.split(b"--" + boundary)
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header, _, content = part.partition(b"\r\n\r\n")
            content = content.rstrip(b"\r\n").rstrip(b"--").rstrip(b"\r\n")
            if not content:
                continue
            # extract filename
            match = re.search(rb'filename="([^"]*)"', header)
            if match:
                return match.group(1).decode("utf-8", errors="replace"), content
        return None, None


def main():
    parser = argparse.ArgumentParser(description="ParkSyTTS 모델 업로드 서버")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()

    server = HTTPServer((args.bind, args.port), UploadHandler)
    print(f"""
╔══════════════════════════════════════════════╗
║  🎙 ParkSyTTS v1 · 모델 업로드 서버          ║
║                                              ║
║  📂 저장 경로: {MODEL_DIR}
║  🌐 PC에서 접속: http://{_get_ip()}:{args.port}
║                                              ║
║  필요한 파일 3개:                             ║
║  ├── gpt/parksy_v2-e15.ckpt      (149MB)     ║
║  ├── sovits/parksy_v2_e8_s256.pth (165MB)    ║
║  └── ref/seg004.wav                          ║
║                                              ║
║  ⏎ Ctrl+C로 종료                              ║
╚══════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 서버 종료")


def _get_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.219.131"


if __name__ == "__main__":
    main()
