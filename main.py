from flask import Flask, request, jsonify, Response
import requests, time, threading, os
from datetime import datetime, timezone

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

ADMIN_KEY = "kalyug"
TEMP_KEY = "kaifu-temp"
UPSTREAM_API = "https://numapi.anshapi.workers.dev/?num={num}"
TTL_HOURS = 24
MAX_REQ_PER_IP = 20
REQ_TIMEOUT = 10

_data = {"created": time.time(), "uses": {}, "log": []}
_lock = threading.Lock()

def now(): return datetime.now(timezone.utc).isoformat()
def valid_temp(): return (time.time() - _data["created"]) < TTL_HOURS * 3600

def inc(ip, num):
    with _lock:
        c = _data["uses"].get(ip, 0)
        if c >= MAX_REQ_PER_IP:
            return False
        _data["uses"][ip] = c + 1
        _data["log"].append({"ip": ip, "num": num, "ts": now()})
        if len(_data["log"]) > 300:
            _data["log"] = _data["log"][-300:]
        return True

@app.route("/")
def home():
    html = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width,initial-scale=1"/>
      <title>Secure Number Lookup</title>
      <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body{
          height:100vh;display:flex;align-items:center;justify-content:center;
          background:linear-gradient(135deg,#000814,#001d3d,#003566);
          color:#fff;font-family:Inter,Segoe UI,sans-serif;
          overflow:hidden;text-align:center;
        }
        .msg{
          font-size:2rem;font-weight:800;
          background:linear-gradient(90deg,#00e6ff,#8b5cff);
          -webkit-background-clip:text;-webkit-text-fill-color:transparent;
          animation:pop 2s infinite alternate ease-in-out;
        }
        @keyframes pop{0%{transform:scale(1);}100%{transform:scale(1.2);}}
        #warn{
          display:none;position:fixed;inset:0;background:rgba(0,0,0,0.9);
          color:#ffb3b3;font-size:2rem;font-weight:900;align-items:center;
          justify-content:center;animation:blink 0.7s infinite alternate;
          z-index:9999;text-shadow:0 0 10px red;
        }
        @keyframes blink{0%{opacity:1;}100%{opacity:0.6;}}
      </style>
    </head>
    <body>
      <div class="msg">Kya bhai... kya karne ja raha hai 😏</div>
      <div id="warn">KYA KAR RHA HAI BSDK — API LGE 🔥</div>
      <script>
        const warn=document.getElementById('warn');
        let open=false;
        setInterval(()=>{
          const t=performance.now();
          debugger;
          if(performance.now()-t>100){
            if(!open){
              open=true;
              warn.style.display='flex';
            }
          }
        },800);
      </script>
    </body>
    </html>
    """
    return Response(html, content_type="text/html; charset=utf-8")

@app.route("/api/info")
def info():
    key = request.args.get("key")
    num = request.args.get("num", "").strip()
    ip = request.headers.get("x-forwarded-for", request.remote_addr)

    if not key:
        return jsonify({"success": False, "error": "Missing key"}), 401
    if not num.isdigit():
        return jsonify({"success": False, "error": "Invalid number"}), 400

    if key == ADMIN_KEY:
        pass
    elif key == TEMP_KEY:
        if not valid_temp():
            return jsonify({"success": False, "error": "Temp key expired"}), 401
        if not inc(ip, num):
            return jsonify({"success": False, "error": "Limit reached"}), 429
    else:
        return jsonify({"success": False, "error": "Invalid key"}), 401

    try:
        r = requests.get(UPSTREAM_API.format(num=num), timeout=REQ_TIMEOUT)
        data = r.json()
        return jsonify({"success": True, "queried": num, "upstream": data, "time": now()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
