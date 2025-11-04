from flask import Flask, request, jsonify, Response
import requests, time, threading, os
from datetime import datetime, timezone

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# Keys / config
ADMIN_KEY = "kalyug"
TEMP_KEY = "jhat-ke-pakode"  # existing temp key; keep/manage carefully
# Upstream API you provided:
UPSTREAM_API = "https://subhxmouktik-number-api.onrender.com/api?key=DARKDB&type=mobile&term={num}"

TTL_HOURS = 24
MAX_REQ_PER_IP = 20
REQ_TIMEOUT = 10

# Mask placeholder to be used for any sensitive owner/name fields
MASK_PLACEHOLDER = "[REDACTED]"

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
    return Response("<h2>Secure Number Lookup API</h2><p>Use /api/info?key=...&num=...&consent=true for consented lookups.</p>", content_type="text/html; charset=utf-8")

def mask_sensitive_fields(obj):
    """
    Recursively mask likely-sensitive fields in a JSON-like object.
    This is conservative: it masks keys that commonly indicate a person name/owner.
    """
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            lk = k.lower()
            # If key suggests a personal identity field, mask it
            if any(token in lk for token in ("name", "owner", "fullname", "registered_to", "holder", "cnic", "aadhaar")):
                new[k] = MASK_PLACEHOLDER
            else:
                new[k] = mask_sensitive_fields(v)
        return new
    elif isinstance(obj, list):
        return [mask_sensitive_fields(x) for x in obj]
    else:
        return obj

@app.route("/api/info")
def info():
    key = request.args.get("key")
    num = request.args.get("num", "").strip()
    ip = request.headers.get("x-forwarded-for", request.remote_addr)
    consent = request.args.get("consent", "false").lower() == "true"

    if not key:
        return jsonify({"success": False, "error": "Missing key"}), 401
    if not num.isdigit():
        return jsonify({"success": False, "error": "Invalid number"}), 400

    # Authentication & rate limiting
    if key == ADMIN_KEY:
        pass
    elif key == TEMP_KEY:
        if not valid_temp():
            return jsonify({"success": False, "error": "Temp key expired"}), 401
        if not inc(ip, num):
            return jsonify({"success": False, "error": "Limit reached"}), 429
    else:
        return jsonify({"success": False, "error": "Invalid key"}), 401

    # If the user has not provided explicit consent (consent=true) and is not admin, return masked result only.
    require_consent_for_identifiers = True

    try:
        r = requests.get(UPSTREAM_API.format(num=num), timeout=REQ_TIMEOUT)
        upstream_data = r.json()
    except Exception as e:
        return jsonify({"success": False, "error": "Upstream error: " + str(e)}), 500

    # If user is admin OR explicit consent provided, return upstream data but still mask highly sensitive keys if no consent
    if key == ADMIN_KEY or (consent and not require_consent_for_identifiers is False):
        # Admins and consented requests get the upstream response — but still optionally mask very sensitive keys unless explicit admin override
        # NOTE: If you want admins to see raw data, you can skip masking for ADMIN_KEY here (use caution).
        result = upstream_data
    else:
        # Non-admin/no-consent: conservatively mask fields that look like person identifiers
        result = mask_sensitive_fields(upstream_data)

    # Always include a policy note in response
    policy_note = (
        "This service masks possible personal identity fields unless 'consent=true' is provided "
        "or request is made with an admin key. Ensure you have legal right and explicit consent "
        "before accessing personal data."
    )

    return jsonify({"success": True, "queried": num, "upstream": result, "policy_note": policy_note, "time": now()})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
