#!/usr/bin/env python3
# main.py
# RC Lookup API with the SAME system as file #1 (keys, rate-limit, logs, consent),
# but owner name is INCLUDED (not removed). Response also includes "powered_by": "Kalyug".
from flask import Flask, request, jsonify, Response
import requests, time, threading, os, re
from datetime import datetime, timezone
from urllib.parse import quote
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
BRAND = os.getenv("BRAND", "Kalyug")

# -----------------------
# Configuration  (same style as file #1)  :contentReference[oaicite:2]{index=2}
# -----------------------
ADMIN_KEY = "kalyug"               # admin key (keep secret)
TEMP_KEY = "jhat-ke-pakode"        # temporary key example
TTL_HOURS = 24
MAX_REQ_PER_IP = 20
REQ_TIMEOUT = 10

# Simple in-memory usage tracking (not persistent)  :contentReference[oaicite:3]{index=3}
_data = {"created": time.time(), "uses": {}, "log": []}
_lock = threading.Lock()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def valid_temp():
    return (time.time() - _data["created"]) < TTL_HOURS * 3600

def inc(ip, rc):
    with _lock:
        c = _data["uses"].get(ip, 0)
        if c >= MAX_REQ_PER_IP:
            return False
        _data["uses"][ip] = c + 1
        _data["log"].append({"ip": ip, "rc": rc, "ts": now_iso()})
        if len(_data["log"]) > 300:
            _data["log"] = _data["log"][-300:]
        return True

# -----------------------
# Scraper (from your RC file, adapted for this API)  :contentReference[oaicite:4]{index=4}
# -----------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5)",
    "Referer": "https://vahanx.in/",
    "Accept-Language": "en-US,en;q=0.9"
}

def _find_text(soup, label):
    try:
        span = soup.find("span", string=lambda s: s and s.strip().lower() == label.lower())
        if span:
            p = span.find_parent("div").find("p")
            return p.get_text(strip=True) if p else None
    except Exception:
        pass
    return None

def _section_dict(soup, header_contains, keys):
    h3 = soup.find("h3", string=lambda s: s and header_contains.lower() in s.lower())
    card = h3.find_parent("div", class_="hrc-details-card") if h3 else None
    out = {}
    for k in keys:
        try:
            span = card.find("span", string=lambda s: s and k.lower() in s.lower()) if card else None
            p = span.find_next("p") if span else None
            if p: out[k.lower().replace(" ", "_")] = p.get_text(strip=True)
        except Exception:
            pass
    return out

def fetch_rc_details(rc_number: str):
    rc = rc_number.strip().upper()
    url = f"https://vahanx.in/rc-search/{quote(rc)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        return {"error": f"Failed to fetch data: {e}", "powered_by": BRAND}

    soup = BeautifulSoup(r.text, "html.parser")

    def card(label):
        for div in soup.select(".hrcd-cardbody"):
            span = div.find("span")
            if span and label.lower() in span.text.lower():
                p = div.find("p")
                return p.get_text(strip=True) if p else None
        return None

    registration = (soup.find("h1").get_text(strip=True) if soup.find("h1") else rc)
    modal_name   = card("Model Name") or _find_text(soup, "Model Name")
    owner_name   = card("Owner Name") or _find_text(soup, "Owner Name")   # <- owner name INCLUDED
    city         = card("City Name")  or _find_text(soup, "City Name")
    phone        = card("Phone")      or _find_text(soup, "Phone")
    address      = card("Address")    or _find_text(soup, "Address")

    ownership = _section_dict(soup, "Ownership Details",
                              ["Owner Name", "Father's Name", "Owner Serial No", "Registration Number", "Registered RTO"])
    vehicle   = _section_dict(soup, "Vehicle Details",
                              ["Model Name", "Maker Model", "Vehicle Class", "Fuel Type", "Fuel Norms", "Cubic Capacity", "Seating Capacity"])
    insurance = _section_dict(soup, "Insurance Information",
                              ["Insurance Company", "Insurance No", "Insurance Expiry", "Insurance Upto"])
    validity  = _section_dict(soup, "Important Dates",
                              ["Registration Date", "Vehicle Age", "Fitness Upto", "Insurance Upto", "Insurance Expiry In", "Tax Upto", "Tax Paid Upto"])
    puc       = _section_dict(soup, "PUC Details", ["PUC No", "PUC Upto"])
    other     = _section_dict(soup, "Other Information",
                              ["Financer Name", "Financier Name", "Cubic Capacity", "Seating Capacity", "Permit Type", "Blacklist Status", "NOC Details"])

    exp_box = soup.select_one(".insurance-alert-box.expired .title")
    expired_days = None
    if exp_box:
        m = re.search(r"(\d+)", exp_box.get_text(" ", strip=True))
        expired_days = int(m.group(1)) if m else None

    def clean(d):
        if isinstance(d, dict):
            return {k: clean(v) for k, v in d.items() if v not in (None, "", [])}
        return d

    return clean({
        "registration_number": registration,
        "status": "success",
        "powered_by": BRAND,
        "basic_info": {
            "model_name": modal_name,
            "owner_name": owner_name,   # owner shown
            "city": city,
            "phone": phone,
            "address": address
        },
        "ownership_details": {
            "owner_name": ownership.get("owner_name") or owner_name,
            "fathers_name": ownership.get("father's_name"),
            "serial_no": ownership.get("owner_serial_no"),
            "rto": ownership.get("registered_rto")
        },
        "vehicle_details": {
            "maker": vehicle.get("model_name") or modal_name,
            "model": vehicle.get("maker_model"),
            "vehicle_class": vehicle.get("vehicle_class"),
            "fuel_type": vehicle.get("fuel_type"),
            "fuel_norms": vehicle.get("fuel_norms"),
            "cubic_capacity": vehicle.get("cubic_capacity") or other.get("cubic_capacity"),
            "seating_capacity": vehicle.get("seating_capacity") or other.get("seating_capacity")
        },
        "insurance": {
            "status": "Expired" if expired_days else "Active",
            "company": insurance.get("insurance_company"),
            "policy_number": insurance.get("insurance_no"),
            "expiry_date": insurance.get("insurance_expiry"),
            "valid_upto": insurance.get("insurance_upto"),
            "expired_days_ago": expired_days
        },
        "validity": {
            "registration_date": validity.get("registration_date"),
            "vehicle_age": validity.get("vehicle_age"),
            "fitness_upto": validity.get("fitness_upto"),
            "insurance_upto": validity.get("insurance_upto"),
            "insurance_status": validity.get("insurance_expiry_in"),
            "tax_upto": validity.get("tax_upto") or validity.get("tax_paid_upto")
        },
        "puc_details": {
            "puc_number": puc.get("puc_no"),
            "puc_valid_upto": puc.get("puc_upto")
        },
        "other_info": {
            "financer": other.get("financer_name") or other.get("financier_name"),
            "permit_type": other.get("permit_type"),
            "blacklist_status": other.get("blacklist_status"),
            "noc": other.get("noc_details")
        }
    })

# -----------------------
# Routes (same style/flow as file #1)  :contentReference[oaicite:5]{index=5}
# -----------------------
@app.route("/")
def home():
    html = (
        "<h2>Kalyug RC Lookup (secured)</h2>"
        "<p>Use <code>/api/info?key=...&rc=DL01AB1234&consent=true</code></p>"
        "<p>Admin/Temp keys + per-IP rate-limit same as number API.</p>"
    )
    return Response(html, content_type="text/html; charset=utf-8")

@app.route("/api/info")
def api_info():
    key = request.args.get("key", "").strip()
    rc  = request.args.get("rc", "").strip().upper()
    ip  = request.headers.get("x-forwarded-for", request.remote_addr)
    # consent flag kept for parity with file #1 (not enforced)  :contentReference[oaicite:6]{index=6}
    _ = request.args.get("consent", "false").lower() == "true"

    if not key:
        return jsonify({"success": False, "error": "Missing key"}), 401
    if not rc or len(rc) < 5:
        return jsonify({"success": False, "error": "Invalid or missing 'rc' parameter"}), 400

    if key == ADMIN_KEY:
        pass
    elif key == TEMP_KEY:
        if not valid_temp():
            return jsonify({"success": False, "error": "Temp key expired"}), 401
        if not inc(ip, rc):
            return jsonify({"success": False, "error": "Rate limit exceeded"}), 429
    else:
        return jsonify({"success": False, "error": "Invalid key"}), 401

    data = fetch_rc_details(rc)
    if isinstance(data, dict) and "powered_by" not in data:
        data["powered_by"] = BRAND

    policy_note = "Api use karo masti me koi problem aye to contact karo Kalyug ko yani mujhe."
    return jsonify({
        "success": True,
        "queried": rc,
        "result": data,
        "policy_note": policy_note,
        "powered_by": BRAND,
        "time": now_iso()
    })

# Local dev
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
