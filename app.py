import os
import time
import json
import math
import urllib.request
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# --- BUILT-IN CORS ---
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

FIREBASE_URL = "https://amanmod-91196-default-rtdb.firebaseio.com"

# --- FIREBASE REST API HELPERS ---
def fb_request(endpoint, data=None, method='GET'):
    try:
        url = f"{FIREBASE_URL}/{endpoint}.json"
        body = json.dumps(data).encode('utf-8') if data is not None else None
        headers = {'Content-Type': 'application/json'} if body else {}

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body) if res_body and res_body != "null" else True
    except Exception:
        return None

def fb_get(endpoint):
    return fb_request(endpoint, method='GET')

def fb_put(endpoint, data):
    res = fb_request(endpoint, data=data, method='PUT')
    return res is not None

def fb_patch(endpoint, data):
    res = fb_request(endpoint, data=data, method='PATCH')
    return res is not None

def fb_delete(endpoint):
    res = fb_request(endpoint, method='DELETE')
    return res is not None


# --- WEB PAGE ROUTES ---
@app.route('/')
@app.route('/seller')
def seller_page():
    if os.path.exists('seller.html'):
        return send_file('seller.html')
    return "Error: seller.html missing in repo", 404

@app.route('/admin')
def admin_page():
    if os.path.exists('admin.html'):
        return send_file('admin.html')
    return "Error: admin.html missing in repo", 404


# --- MASTER ADMIN APIS ---
@app.route('/admin/create_reseller', methods=['POST'])
def create_reseller():
    user = request.form.get('username', '').strip().lower()
    pwd = request.form.get('password', '').strip()
    balance = float(request.form.get('balance', 0.0))
    days = int(request.form.get('days', 30))

    if not user or not pwd:
        return jsonify({"success": False, "msg": "Username aur Password zaroori hain!"}), 400

    expiry = int(time.time() * 1000) + (days * 24 * 60 * 60 * 1000)

    data = {
        "username": user,
        "password": pwd,
        "balance": balance,
        "expiry_timestamp": expiry,
        "status": "active",
        "whatsapp": "https://wa.me/919999999999",
        "telegram": "https://t.me/your_telegram_id"
    }

    if fb_put(f"resellers/{user}", data):
        return jsonify({"success": True, "msg": f"Reseller [{user}] successfully create ho gaya!"})
    return jsonify({"success": False, "msg": "Firebase write fail!"}), 500

@app.route('/admin/get_resellers', methods=['GET'])
def get_resellers():
    resellers_raw = fb_get("resellers")
    if not resellers_raw:
        return jsonify([])

    if isinstance(resellers_raw, dict):
        resellers_list = list(resellers_raw.values())
    elif isinstance(resellers_raw, list):
        resellers_list = [item for item in resellers_raw if item is not None and isinstance(item, dict)]
    else:
        resellers_list = []

    return jsonify(resellers_list)

@app.route('/admin/recharge_reseller', methods=['POST'])
def recharge_reseller():
    user = request.form.get('username', '').strip().lower()
    amount = float(request.form.get('amount', 0.0))

    reseller = fb_get(f"resellers/{user}")
    if not reseller or not isinstance(reseller, dict):
        return jsonify({"success": False, "msg": "Reseller nahi mila!"}), 404

    new_bal = float(reseller.get('balance', 0.0)) + amount
    if fb_patch(f"resellers/{user}", {"balance": new_bal}):
        return jsonify({"success": True, "balance": new_bal})
    return jsonify({"success": False, "msg": "Recharge fail!"}), 500

@app.route('/admin/delete_reseller', methods=['POST'])
def delete_reseller():
    user = request.form.get('username', '').strip().lower()
    if fb_delete(f"resellers/{user}"):
        return jsonify({"success": True})
    return jsonify({"success": False, "msg": "Delete fail!"}), 500


# --- RESELLER PANEL APIS ---
@app.route('/reseller/login', methods=['POST'])
def reseller_login():
    user = request.form.get('username', '').strip().lower()
    pwd = request.form.get('password', '').strip()

    reseller = fb_get(f"resellers/{user}")
    if not reseller or not isinstance(reseller, dict) or str(reseller.get('password')) != str(pwd):
        return jsonify({"success": False, "msg": "Galat Username ya Password!"}), 401

    if reseller.get('status') != 'active':
        return jsonify({"success": False, "msg": "Aapka account Blocked hai!"}), 403

    now = int(time.time() * 1000)
    exp = reseller.get('expiry_timestamp', 0)
    if exp > 0 and now > exp:
        return jsonify({"success": False, "msg": "Aapka Reseller account EXPIRE ho chuka hai!"}), 403

    return jsonify({
        "success": True,
        "username": str(reseller.get('username', user)),
        "balance": reseller.get('balance', 0.0)
    })

# SERVER TIME BHEJ RAHE HAIN
@app.route('/reseller/data', methods=['GET'])
def reseller_data():
    user = request.args.get('username', '').strip().lower()
    reseller = fb_get(f"resellers/{user}")

    if not reseller or not isinstance(reseller, dict):
        return jsonify({"success": False, "msg": "User not found"}), 404

    all_keys = fb_get("keys") or {}
    items = []
    if isinstance(all_keys, dict):
        items = list(all_keys.values())
    elif isinstance(all_keys, list):
        items = [k for k in all_keys if k is not None and isinstance(k, dict)]

    user_keys = [v for v in items if str(v.get('reseller', '')).lower() == user]
    user_keys.sort(key=lambda x: x.get('expiry_timestamp', 0), reverse=True)

    # Real Server Clock (UTC)
    server_real_time = int(time.time() * 1000)

    return jsonify({
        "success": True,
        "server_time": server_real_time,
        "balance": reseller.get('balance', 0.0),
        "expiry_timestamp": reseller.get('expiry_timestamp', 0),
        "whatsapp": reseller.get('whatsapp', 'https://wa.me/919999999999'),
        "telegram": reseller.get('telegram', 'https://t.me/your_telegram_id'),
        "keys": user_keys
    })

@app.route('/reseller/update_contact', methods=['POST'])
def update_contact():
    user = request.form.get('username', '').strip().lower()
    wa = request.form.get('whatsapp', '').strip()
    tg = request.form.get('telegram', '').strip()

    if not user:
        return jsonify({"success": False, "msg": "Username missing!"}), 400

    update_payload = {}
    if wa: update_payload["whatsapp"] = wa
    if tg: update_payload["telegram"] = tg

    fb_patch(f"resellers/{user}", update_payload)

    fb_patch("panel_config/contact", {
        "whatsapp": wa,
        "telegram": tg,
        "updated_by": user
    })

    return jsonify({"success": True, "msg": "WhatsApp aur Telegram links update ho gaye!"})

# KEY GENERATION (1 DIN = 100 RS FIXED)
@app.route('/reseller/generate_key', methods=['POST'])
def reseller_generate_key():
    user = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    custom_exp = request.form.get('expiry_timestamp', '').strip()

    now = int(time.time() * 1000)

    try:
        exp = int(custom_exp)
    except Exception:
        exp = now + (24 * 3600 * 1000)

    if exp <= now:
        return jsonify({"success": False, "msg": "Expiry date aane wale samay ki select karein!"}), 400

    diff_ms = exp - now
    days = max(1, math.ceil(diff_ms / (24 * 3600 * 1000.0)))
    cost = float(days * 100.0)

    reseller = fb_get(f"resellers/{user}")
    if not reseller or not isinstance(reseller, dict) or float(reseller.get('balance', 0.0)) < cost:
        return jsonify({"success": False, "msg": f"Balance kam hai! ₹{cost:.0f} chahiye ({days} Din ke liye)."}), 400

    new_bal = float(reseller.get('balance', 0.0)) - cost
    fb_patch(f"resellers/{user}", {"balance": new_bal})

    plan_name = f"{days} Day{'s' if days > 1 else ''}"

    key_data = {
        "key": key,
        "hwid": "",
        "status": "unused",
        "reseller": user,
        "plan": plan_name,
        "expiry_timestamp": exp
    }

    if fb_put(f"keys/{key}", key_data):
        return jsonify({"success": True, "key": key, "cost": cost, "days": days})
    return jsonify({"success": False, "msg": "Key generate fail!"}), 500

@app.route('/reseller/edit_key', methods=['POST'])
def reseller_edit_key():
    user = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    status = request.form.get('status', '').strip()
    reset_hwid = str(request.form.get('reset_hwid', '')).lower() == 'true'

    key_obj = fb_get(f"keys/{key}")
    if not key_obj or not isinstance(key_obj, dict) or str(key_obj.get('reseller', '')).lower() != user:
        return jsonify({"success": False, "msg": "Key nahi mili!"}), 404

    updates = {}
    if status: updates["status"] = status
    if reset_hwid: updates["hwid"] = ""

    if fb_patch(f"keys/{key}", updates):
        return jsonify({"success": True, "msg": "Key update ho gayi!"})
    return jsonify({"success": False, "msg": "Key update fail!"}), 500

@app.route('/reseller/delete_key', methods=['POST'])
def reseller_delete_key():
    user = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()

    key_obj = fb_get(f"keys/{key}")
    if not key_obj or not isinstance(key_obj, dict) or str(key_obj.get('reseller', '')).lower() != user:
        return jsonify({"success": False, "msg": "Key nahi mili!"}), 404

    if fb_delete(f"keys/{key}"):
        return jsonify({"success": True, "msg": "Key permanently delete ho gayi!"})
    return jsonify({"success": False, "msg": "Delete fail!"}), 500

# VERIFY ROUTE (100% SERVER CLOCK)
@app.route('/verify', methods=['POST'])
def verify():
    key = request.form.get('key', '').strip().upper()
    hwid = request.form.get('hwid', '').strip().lower()

    if not key or not hwid:
        return jsonify({"status": False, "msg": "KEY AUR HWID MISSING HAI"}), 400

    key_obj = fb_get(f"keys/{key}")
    if not key_obj or not isinstance(key_obj, dict):
        return jsonify({"status": False, "msg": "INVALID LICENSE KEY"})

    now = int(time.time() * 1000)
    exp = key_obj.get('expiry_timestamp', 0)
    if exp > 0 and now > exp:
        fb_patch(f"keys/{key}", {"status": "expired"})
        return jsonify({"status": False, "msg": "KEY EXPIRED"})

    if key_obj.get('status') == 'frozen':
        return jsonify({"status": False, "msg": "KEY IS FROZEN"})

    bound_hwid = key_obj.get('hwid', '').strip().lower()
    if not bound_hwid:
        fb_patch(f"keys/{key}", {"hwid": hwid, "status": "active"})
        return jsonify({"status": True, "msg": "DEVICE BOUND & ACCESS GRANTED"})

    if bound_hwid == hwid:
        return jsonify({"status": True, "msg": "LOGIN SUCCESSFUL"})
    else:
        return jsonify({"status": False, "msg": "HWID MISMATCH! BOUND TO ANOTHER DEVICE"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
