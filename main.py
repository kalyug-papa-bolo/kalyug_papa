from flask import Flask, request, jsonify
import requests
import re
import html
import json
import os
from functools import wraps

app = Flask(__name__)

# ====== CONFIG ======
API_KEY = os.getenv("HEXAVAULT_API_KEY", "papa")
TARGET = "https://anon-num-info.vercel.app/num?key=num5017temp&num={num}"
# ====================


# ====== API KEY CHECK ======
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Read key from header, query, form, or JSON
        key = (
            request.headers.get("X-API-Key")
            or request.args.get("api_key")
            or request.form.get("api_key")
        )
        # Check JSON body safely
        if not key and request.is_json:
            data = request.get_json(silent=True)
            if data:
                key = data.get("api_key")

        if key != API_KEY:
            return jsonify({"success": False, "error": "Unauthorized. Provide valid API key."}), 401

        return f(*args, **kwargs)
    return decorated
# ============================


def extract_json_from_html(html_text):
    m = re.search(r"<pre>(.*?)</pre>", html_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1)
    unescaped = html.unescape(raw)
    try:
        return json.loads(unescaped)
    except json.JSONDecodeError:
        cleaned = unescaped.strip()
        cleaned = re.sub(r",\s*}", "}", cleaned)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


@app.route("/lookup", methods=["GET", "POST"])
@require_api_key
def lookup():
    number = (
        request.args.get("number")
        or request.form.get("number")
    )

    if not number and request.is_json:
        data = request.get_json(silent=True)
        if data:
            number = data.get("number")

    if not number:
        return jsonify({"success": False, "error": "Provide 'number' parameter"}), 400

    try:
        resp = requests.post(
            TARGET,
            data={"number": number},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; HexaVault-API-Proxy/1.0)"}
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"Request failed: {str(e)}"}), 502

    if resp.status_code != 200:
        return jsonify({"success": False, "error": f"Upstream returned {resp.status_code}"}), 502

    parsed = extract_json_from_html(resp.text)
    if parsed is None:
        return jsonify({"success": False, "error": "Could not parse JSON", "raw_preview": resp.text[:500]}), 500

    return jsonify({"success": True, "source_status": resp.status_code, "payload": parsed})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
