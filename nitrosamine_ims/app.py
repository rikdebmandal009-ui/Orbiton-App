"""
Intelligent Inventory Management System
Run this file -> your browser opens automatically with the full dashboard
"""

import os
import json
import webbrowser
import threading
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from pathlib import Path
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='templates', static_folder='static')

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

NITROSAMINE_FILE = DATA_DIR / "nitrosamines.xlsx"
RAWMAT_FILE      = DATA_DIR / "raw_materials.xlsx"
HISTORY_FILE     = DATA_DIR / "usage_history.json"
RESTOCK_FILE     = DATA_DIR / "restock_history.json"


# ── Data loading & cleaning ───────────────────────────────────────────────────

def parse_qty(val):
    """Convert '500 mg', '1.5 g', '2g' → grams as float"""
    if pd.isna(val):
        return 0.0
    s = str(val).strip().lower().replace(" ", "")
    if "mg" in s:
        return float(s.replace("mg", "")) / 1000
    if "g" in s:
        return float(s.replace("g", ""))
    try:
        return float(s)
    except:
        return 0.0


def load_data():
    nit_path = NITROSAMINE_FILE if NITROSAMINE_FILE.exists() else Path("data/nitrosamines.xlsx")
    raw_path  = RAWMAT_FILE     if RAWMAT_FILE.exists()      else Path("data/raw_materials.xlsx")

    df_nit = pd.read_excel(nit_path)
    df_raw = pd.read_excel(raw_path)

    df_nit.columns = [c.strip().upper() for c in df_nit.columns]
    df_raw.columns = [c.strip().upper() for c in df_raw.columns]

    df_nit["QTY_G"] = df_nit["QTY"].apply(parse_qty)
    df_raw["QTY_G"] = df_raw["QTY"].apply(parse_qty)

    df_nit["IMPURITY NAME"] = df_nit["IMPURITY NAME"].str.strip()
    df_raw["IMPURITY NAME"] = df_raw["IMPURITY NAME"].str.strip()

    return df_nit, df_raw


def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2)


def load_restock_history():
    if RESTOCK_FILE.exists():
        with open(RESTOCK_FILE) as f:
            return json.load(f)
    return {}


def save_restock_history(h):
    with open(RESTOCK_FILE, "w") as f:
        json.dump(h, f, indent=2)


# ── Prediction engine ─────────────────────────────────────────────────────────

DAILY_USE_DEFAULTS = {
    "N,Nitrosodimethylamine":       0.18,
    "N-Nitrosodiethylamine":        0.04,
    "N-Nitroso-diisopropylamine":   0.09,
    "N-Nitroso-di-n-butylamine":    0.05,
    "N-Nitrosobutylmethylamine":    0.08,
    "N-Nitrosoethylmethylamine":    0.03,
    "N-Nitrosodipropylamine":       0.06,
    "N-Nitrosoethylisopropylamine": 0.02,
    "N-Nitroso-N-methylaniline":    0.03,
}


def calc_days_remaining(qty_g, daily_use_g):
    if daily_use_g <= 0:
        return 999
    return round(qty_g / daily_use_g)


def get_status(days):
    if days < 15:  return "critical"
    if days < 30:  return "watch"
    return "safe"


def predict_depletion_date(days):
    return (datetime.now() + timedelta(days=days)).strftime("%d %b %Y")


def normalize_image_name(name):
    base = "".join(c if c.isalnum() or c=='_' else '_' for c in name.replace(' ', '_'))
    base = '_'.join([part for part in base.split('_') if part])
    return f"{base}.png"


def build_inventory_data():
    df_nit, df_raw = load_data()
    history = load_history()
    restock_history = load_restock_history()
    items = []

    for _, row in df_nit.iterrows():
        name   = row["IMPURITY NAME"]
        qty_g  = row["QTY_G"]
        batch  = row.get("BATCH NO", "—")
        cas    = row.get("CAS NO", "—")

        # Add restocked amounts
        restocks = restock_history.get(name, {"entries": []})["entries"]
        total_restocked = sum(float(e.get("restocked_g", 0)) for e in restocks)
        qty_g += total_restocked

        hist   = history.get(name, {})
        daily  = hist.get("daily_use_g", DAILY_USE_DEFAULTS.get(name, 0.05))
        days   = calc_days_remaining(qty_g, daily)
        status = get_status(days)

        raw_row = df_raw[df_raw["S.NO"] == row["S.NO"]] if "S.NO" in df_raw.columns else pd.DataFrame()
        raw_name = raw_row["IMPURITY NAME"].values[0] if not raw_row.empty else "—"
        raw_qty  = float(raw_row["QTY_G"].values[0])  if not raw_row.empty else 0.0
        ratio    = round(raw_qty / qty_g, 1) if qty_g > 0 else 0

        image_name = normalize_image_name(name)
        image_path = (Path(app.static_folder) / image_name)
        if not image_path.exists():
            image_name = ''  # No fallback image, will show upload button only

        items.append({
            "name":          name,
            "batch":         str(batch),
            "cas":           str(cas),
            "qty_g":         round(qty_g, 3),
            "daily_use_g":   round(daily, 3),
            "days_remaining": days,
            "depletion_date": predict_depletion_date(days),
            "status":        status,
            "raw_material":  raw_name,
            "raw_qty_g":     round(raw_qty, 1),
            "ratio":         ratio,
            "image":         f"/static/{image_name}" if image_name else "",
        })

    items.sort(key=lambda x: x["days_remaining"])
    return items


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/inventory")
def api_inventory():
    items = build_inventory_data()
    critical = sum(1 for i in items if i["status"] == "critical")
    watch    = sum(1 for i in items if i["status"] == "watch")
    avg_days = round(sum(i["days_remaining"] for i in items) / len(items)) if items else 0
    safe = len(items) - critical - watch
    return jsonify({
        "items":    items,
        "summary":  {"critical": critical, "watch": watch, "avg_days": avg_days, "total": len(items), "safe": safe},
        "updated":  datetime.now().strftime("%d %b %Y, %H:%M"),
    })


@app.route('/api/upload_structure', methods=['POST'])
def api_upload_structure():
    name = request.form.get('name', '').strip()
    img = request.files.get('image')

    if not name or not img:
        return jsonify({'ok': False, 'error': 'name and image are required'}), 400

    # Validate file type - only PNG allowed
    if not img.filename.lower().endswith('.png'):
        return jsonify({'ok': False, 'error': 'Only PNG files are allowed'}), 400

    filename = secure_filename(normalize_image_name(name))
    save_path = Path(app.static_folder) / filename
    img.save(save_path)

    return jsonify({'ok': True, 'file': f'/static/{filename}'})


@app.route("/api/update_usage", methods=["POST"])
def api_update_usage():
    data    = request.json
    name    = data.get("name")
    used_g  = float(data.get("used_g", 0))
    history = load_history()
    if name not in history:
        history[name] = {"entries": []}
    history[name]["entries"].append({"date": datetime.now().isoformat(), "used_g": used_g})
    entries = history[name]["entries"][-30:]
    if entries:
        total_days = max(1, (datetime.fromisoformat(entries[-1]["date"]) -
                             datetime.fromisoformat(entries[0]["date"])).days + 1)
        history[name]["daily_use_g"] = sum(e["used_g"] for e in entries) / total_days
    history[name]["entries"] = entries
    save_history(history)
    return jsonify({"ok": True})


@app.route("/api/restock", methods=["POST"])
def api_restock():
    data    = request.json
    name    = data.get("name")
    restocked_g  = float(data.get("restocked_g", 0))
    restock_history = load_restock_history()
    if name not in restock_history:
        restock_history[name] = {"entries": []}
    restock_history[name]["entries"].append({"date": datetime.now().isoformat(), "restocked_g": restocked_g})
    # Keep all entries for restocks
    save_restock_history(restock_history)
    return jsonify({"ok": True})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    for key, fname in [("nitrosamines", NITROSAMINE_FILE), ("raw_materials", RAWMAT_FILE)]:
        if key in request.files:
            request.files[key].save(fname)
    return jsonify({"ok": True, "message": "Files uploaded. Dashboard will refresh automatically."})


def open_browser():
    import time; time.sleep(1.2)
    webbrowser.open("http://localhost:5050")


if __name__ == "__main__":
    print("=" * 55)
    print("  Intelligent Inventory Management System — starting...")
    print("  Opening dashboard at http://localhost:5050")
    print("  Press Ctrl+C to stop")
    print("=" * 55)
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=5050, debug=False)
