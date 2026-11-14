"""DECODE app (receiver's computer): drop the PNG, read the 3 words, see the overlay.

usage: python decode_app.py [words.csv] [port]     -> opens http://127.0.0.1:8766
Offline, stdlib http.server only. Pairs with encode_app.py on the other computer.
"""
import base64
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

import codec
import decoder

WORDLIST = None

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Decode</title>
<style>
 * { box-sizing: border-box; }
 html, body { margin: 0; min-height: 100%; background: #000; color: #cfd6ff; font-family: -apple-system, Helvetica, Arial, sans-serif; }
 body { display: grid; place-items: center; min-height: 100vh; gap: 18px; padding: 24px 16px; }
 img { display: block; width: min(100vw - 32px, 640px); height: auto; }
 #stage { display: grid; place-items: center; min-height: 320px; width: min(100vw - 32px, 640px); border: 1px dashed #22225a; cursor: pointer; }
 #stage.over { border-color: #9fd3ff; }
 #stage p { color: #4f589a; margin: 0; font-size: 14px; }
 #words { font-size: 34px; font-weight: 700; color: #fff; letter-spacing: 1px; min-height: 40px; text-align: center; }
 #note { font-size: 13px; color: #8f98e8; text-align: center; min-height: 18px; }
 #err { color: #ff8a8a; font-size: 14px; min-height: 18px; text-align: center; }
 label.btn { padding: 8px 16px; border: 1px solid #3a3aa0; border-radius: 4px; font-size: 15px; cursor: pointer; }
</style></head><body>
 <div id="stage" onclick="document.getElementById('file').click()"><p>drop the fractal PNG here (or click)</p></div>
 <div id="words"></div><div id="note"></div>
 <label class="btn" for="file">Choose image</label>
 <input type="file" id="file" accept="image/*" style="display:none" onchange="fileChosen(this.files[0])">
 <div id="err"></div>
<script>
const $ = id => document.getElementById(id);
async function decodeB64(b64){
  $('err').textContent=''; $('words').textContent='decoding…'; $('note').textContent='';
  const r=await fetch('/api/decode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({png:b64})});
  const res=await r.json();
  if(res.overlay) $('stage').innerHTML='<img src="data:image/png;base64,'+res.overlay+'">';
  if(res.error&&!res.words){$('words').textContent='';$('err').textContent=res.error;return;}
  $('words').textContent=res.words.join('  ');
  $('note').textContent=res.errata.length?('Reed-Solomon corrected '+res.errata.length+' bulb(s): '+res.errata.join(', ')):'all 15 bulbs read cleanly';
}
function fileChosen(f){ if(!f) return; const r=new FileReader(); r.onload=()=>decodeB64(r.result.split(',')[1]); r.readAsDataURL(f); }
const st=$('stage');
st.addEventListener('dragover',e=>{e.preventDefault();st.classList.add('over');});
st.addEventListener('dragleave',()=>st.classList.remove('over'));
st.addEventListener('drop',e=>{e.preventDefault();st.classList.remove('over');fileChosen(e.dataTransfer.files[0]);});
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, data, ctype, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(b'{"error":"bad request"}', "application/json", 400)
        if self.path != "/api/decode":
            return self._send(b'{"error":"not found"}', "application/json", 404)
        try:
            raw = base64.b64decode(body.get("png", ""))
            bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            bgr = None
        if bgr is None:
            return self._send(json.dumps({"error": "could not read image"}).encode(), "application/json")
        try:
            res = decoder.decode_image(bgr, WORDLIST)
        except decoder.DecodeError as e:
            return self._send(json.dumps({"error": f"decode failed: {e}"}).encode(), "application/json")
        ok, buf = cv2.imencode(".png", decoder.draw_overlay(bgr, res))
        out = {"words": res["words"], "errata": res["errata"], "symbols": res["symbols"],
               "error": res["error"], "overlay": base64.b64encode(buf.tobytes()).decode()}
        self._send(json.dumps(out).encode(), "application/json")


def main(argv):
    global WORDLIST
    words_csv = argv[1] if len(argv) > 1 else codec.default_word_list_path()
    port = int(argv[2]) if len(argv) > 2 else 8766
    WORDLIST = codec.load_words(words_csv)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"DECODE app  |  word list: {words_csv} ({len(WORDLIST)} words)\nopen {url}  (Ctrl+C to stop)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
