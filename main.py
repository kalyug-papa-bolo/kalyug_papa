#!/usr/bin/env python3
# main.py
# Flask-based proxy for number lookup with "owner" field removed from upstream responses.
# NOTE: This file intentionally removes any top-level or nested key named "owner" (case-insensitive)
# from the upstream API response before returning it to the caller. Other fields are preserved.

from flask import Flask, request, jsonify, Response
import requests
import time
import threading
import os
from datetime import datetime, timezone

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# -----------------------
# Configuration
# -----------------------
ADMIN_KEY = "kalyug"               # admin key (keep secret)
TEMP_KEY = "jhat-ke-pakode"        # temporary key example
UPSTREAM_API = "https://subhxmouktik-number-api.onrender.com/api?key=DARKDB&type=mobile&term={num}"
REQ_TIMEOUT = 10
TTL_HOURS = 24
MAX_REQ_PER_IP = 20

# Simple in-memory usage tracking (not persistent)
_data = {"created": time.time(), "uses": {}, "log": []}
_lock = threading.Lock()

# -----------------------
# Helpers
# -----------------------
def now():
    return datetime.now(timezone.utc).isoformat()

def valid_temp():
    return (time.time() - _data["created"]) < TTL_HOURS * 3600

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

def remove_owner_field(obj):
    """
    Recursively remove any key named 'owner' (case-insensitive) from dictionaries.
    Leaves all other fields intact.
    """
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k.lower() == "owner":
                # skip this key entirely (do not include in new)
                continue
            new[k] = remove_owner_field(v)
        return new
    elif isinstance(obj, list):
        return [remove_owner_field(x) for x in obj]
    else:
        return obj

# -----------------------
# Routes
# -----------------------
@app.route("/")
def home():
    html = (
        "<h2>Secure Number Lookup Proxy</h2>"
        "<p>Use <code>/api/info?key=...&num=...&consent=true</code> to query.</p>"
    )
    return Response(html, content_type="text/html; charset=utf-8")

@app.route("/api/info")
def info():
    key = request.args.get("key", "").strip()
    num = request.args.get("num", "").strip()
    ip = request.headers.get("x-forwarded-for", request.remote_addr)
    consent = request.args.get("consent", "false").lower() == "true"

    # Basic validation
    if not key:
        return jsonify({"success": False, "error": "Missing key"}), 401
    if not num or not num.isdigit():
        return jsonify({"success": False, "error": "Invalid or missing 'num' parameter"}), 400

    # Auth & rate limiting
    if key == ADMIN_KEY:
        # admin bypasses rate limits and TTL
        pass
    elif key == TEMP_KEY:
        if not valid_temp():
            return jsonify({"success": False, "error": "Temp key expired"}), 401
        if not inc(ip, num):
            return jsonify({"success": False, "error": "Rate limit exceeded"}), 429
    else:
        return jsonify({"success": False, "error": "Invalid key"}), 401

    # Call upstream
    try:
        resp = requests.get(UPSTREAM_API.format(num=num), timeout=REQ_TIMEOUT)
        resp.raise_for_status()
        upstream_data = resp.json()
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"Upstream request failed: {str(e)}"}), 502
    except ValueError as e:
        return jsonify({"success": False, "error": f"Invalid JSON from upstream: {str(e)}"}), 502

    # Remove any 'owner' fields completely (case-insensitive), preserving rest of the response.
    cleaned_data = remove_owner_field(upstream_data)

    # Add a policy note to remind callers about consent/legal usage
    Owner = (
        "@Jhat_ke_pakode_khaoge_babu")

    return jsonify({
        "queried": num,
        "policy_note": policy_note,
    })

# -----------------------
# Run app
# -----------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
