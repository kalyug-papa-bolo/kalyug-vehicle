# api/main.py
# Single-file Flask app (Landing page + API) for Vercel.
# Every response includes {"powered_by": "Kalyug"}.
import os, re, time, requests
from urllib.parse import quote
from flask import Flask, request, jsonify, make_response
from bs4 import BeautifulSoup

app = Flask(__name__)
BRAND = os.getenv("BRAND", "Kalyug")

# ---------- Stylish Landing Page (inline) ----------
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Kalyug RC Lookup — Fast Vehicle Info</title>
  <meta name="description" content="RC lookup tool by Kalyug. Fetch vehicle details instantly."/>
  <meta property="og:title" content="Kalyug RC Lookup"/>
  <meta property="og:description" content="Type an RC number and get details in seconds."/>
  <meta property="og:type" content="website"/>
  <link rel="icon" href="https://fav.farm/🚗"/>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .glass { background: rgba(4,7,17,.6); border: 1px solid rgba(148,163,184,.2); backdrop-filter: blur(10px); }
    .code { background: rgba(0,0,0,.55); }
  </style>
</head>
<body class="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 text-white selection:bg-indigo-500/40">
  <div class="max-w-3xl mx-auto py-14 px-4">
    <header class="mb-10 text-center">
      <h1 class="text-4xl md:text-5xl font-extrabold tracking-tight">Kalyug <span class="text-indigo-400">RC Lookup</span></h1>
      <p class="mt-3 text-slate-300">Instant vehicle details — clean JSON, serverless friendly.</p>
    </header>

    <div class="glass rounded-2xl p-6 shadow-2xl">
      <label class="block text-sm font-medium mb-2 text-slate-300">Enter RC Number</label>
      <div class="flex gap-2">
        <input id="rc" placeholder="e.g. DL01AB1234"
               class="w-full px-4 py-3 rounded-xl bg-slate-900/70 border border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500"/>
        <button id="go" class="px-5 py-3 rounded-xl bg-indigo-500 hover:bg-indigo-400 active:scale-95 transition font-semibold">Search</button>
      </div>
      <p id="msg" class="mt-3 text-sm text-slate-400"></p>
      <pre id="out" class="code mt-5 p-4 rounded-xl overflow-auto text-sm"></pre>
    </div>

    <footer class="mt-10 text-center text-slate-400">
      <p>Made with ❤️ by <span class="font-semibold text-white">Kalyug</span> •
         <a href="/api/vehicle-info?rc=DL01AB1234" class="underline hover:no-underline">API example</a></p>
    </footer>
  </div>

  <script>
    const rcEl = document.getElementById('rc');
    const goEl = document.getElementById('go');
    const msgEl = document.getElementById('msg');
    const outEl = document.getElementById('out');

    async function fetchRc() {
      const rc = rcEl.value.trim();
      if (!rc) { msgEl.textContent = "Please enter a valid RC number."; return; }
      msgEl.textContent = "Fetching…";
      outEl.textContent = "";
      try {
        const res = await fetch(`/api/vehicle-info?rc=${encodeURIComponent(rc)}`);
        const data = await res.json();
        msgEl.textContent = res.ok ? "Done." : "Failed to fetch.";
        outEl.textContent = JSON.stringify(data, null, 2);
      } catch (e) {
        msgEl.textContent = "Network error.";
        outEl.textContent = String(e);
      }
    }
    goEl.addEventListener('click', fetchRc);
    rcEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') fetchRc(); });
  </script>
</body>
</html>"""

# ---------- Scraper helpers ----------
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
        except:
            pass
    return out

def get_vehicle_details(rc_number: str):
    rc = rc_number.strip().upper()
    url = f"https://vahanx.in/rc-search/{quote(rc)}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
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
    owner_name   = card("Owner Name") or _find_text(soup, "Owner Name")
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

    data = {
        "registration_number": registration,
        "status": "success",
        "powered_by": BRAND,
        "basic_info": {
            "model_name": modal_name,
            "owner_name": owner_name,
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
    }
    return clean(data)

# ---------- Routes ----------
@app.get("/")
def landing():
    resp = make_response(INDEX_HTML, 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

@app.get("/health")
def health():
    return jsonify({"status": "healthy", "timestamp": time.time(), "powered_by": BRAND})

@app.get("/api/vehicle-info")
def vehicle_info():
    rc = request.args.get("rc", "").strip()
    if not rc:
        return jsonify({
            "error": "Missing rc parameter",
            "usage": "/api/vehicle-info?rc=<RC_NUMBER>",
            "powered_by": BRAND
        }), 400
    data = get_vehicle_details(rc)
    if "powered_by" not in data:
        data["powered_by"] = BRAND
    return jsonify(data)
