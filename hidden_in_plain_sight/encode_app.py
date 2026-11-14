"""ENCODE app (sender's computer): type 3 words, get the fractal PNG, download it.

usage: python encode_app.py [words.csv] [port]     -> opens http://127.0.0.1:8765
Offline, stdlib http.server only. Pairs with decode_app.py on the other computer.
"""
import base64
import io
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import codec
import encoder

WORDLIST = None
THEME_OPTIONS = "".join(f'<option value="{t}">{t}</option>' for t in ["auto", *encoder.THEMES])

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Encode</title>
<style>
 * { box-sizing: border-box; }
 html, body { margin: 0; min-height: 100%; background: #000; color: #cfd6ff; font-family: -apple-system, Helvetica, Arial, sans-serif; }
 body { display: grid; place-items: center; min-height: 100vh; gap: 18px; padding: 24px 16px; }
 img { display: block; width: min(100vw - 32px, 640px); height: auto; }
 #stage { display: grid; place-items: center; min-height: 320px; width: min(100vw - 32px, 640px); border: 1px dashed #22225a; }
 #stage p { color: #4f589a; margin: 0; font-size: 14px; }
 .bar { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; align-items: center; }
 input[type=text], select { width: 130px; padding: 8px 10px; background: #0a0a30; color: #fff; border: 1px solid #3a3aa0; border-radius: 4px; font-size: 15px; }
 button { padding: 8px 16px; background: #1a1aa8; color: #fff; border: 0; border-radius: 4px; font-size: 15px; cursor: pointer; }
 a.dl { padding: 8px 16px; border: 1px solid #3a3aa0; border-radius: 4px; color: #9fd3ff; font-size: 15px; text-decoration: none; }
 #err { color: #ff8a8a; font-size: 14px; min-height: 18px; text-align: center; }
 #sym { font-size: 12px; color: #4f589a; min-height: 16px; }
</style></head><body>
 <div id="stage"><p>three words &rarr; one fractal</p></div>
 <div class="bar">
  <input type="text" id="w1" placeholder="word 1"><input type="text" id="w2" placeholder="word 2"><input type="text" id="w3" placeholder="word 3">
  <select id="theme">__THEMES__</select>
  <button onclick="encode()">Encode</button>
  <a id="dl" class="dl" download="secret.png" style="display:none">Download PNG</a>
 </div>
 <div id="sym"></div><div id="err"></div>
<script>
const $ = id => document.getElementById(id);
async function encode(){
  const words=['w1','w2','w3'].map(i=>$(i).value.trim());
  $('err').textContent=''; $('sym').textContent='';
  const r=await fetch('/api/encode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({words, theme:$('theme').value})});
  const res=await r.json();
  if(res.error){$('err').textContent=res.error;return;}
  $('stage').innerHTML='<img src="data:image/png;base64,'+res.png+'">';
  $('dl').href='data:image/png;base64,'+res.png; $('dl').download=words.join('_')+'.png'; $('dl').style.display='inline-block';
  $('sym').textContent='symbols: '+res.symbols.join(' ');
}
document.querySelectorAll('input[type=text]').forEach(i=>i.addEventListener('keydown',e=>{if(e.key==='Enter')encode();}));
</script></body></html>
""".replace("__THEMES__", THEME_OPTIONS)


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
        if self.path != "/api/encode":
            return self._send(b'{"error":"not found"}', "application/json", 404)
        words = [str(w).strip().lower() for w in body.get("words", [])]
        theme = body.get("theme", encoder.DEFAULT_THEME)
        if len(words) != 3 or not all(words):
            return self._send(json.dumps({"error": "please enter three words"}).encode(), "application/json")
        if theme != "auto" and theme not in encoder.THEMES:
            theme = encoder.DEFAULT_THEME
        try:
            img = encoder.render(words, WORDLIST, theme=theme)
            symbols = codec.words_to_symbols(words, WORDLIST)
        except ValueError as e:
            return self._send(json.dumps({"error": str(e)}).encode(), "application/json")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        out = {"png": base64.b64encode(buf.getvalue()).decode(), "symbols": symbols}
        self._send(json.dumps(out).encode(), "application/json")


def main(argv):
    global WORDLIST
    words_csv = argv[1] if len(argv) > 1 else codec.default_word_list_path()
    port = int(argv[2]) if len(argv) > 2 else 8765
    WORDLIST = codec.load_words(words_csv)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"ENCODE app  |  word list: {words_csv} ({len(WORDLIST)} words)\nopen {url}  (Ctrl+C to stop)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
