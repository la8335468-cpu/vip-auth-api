import os
import time
import json
import math
import urllib.request
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# --- BUILT-IN CORS ---
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --- FIREBASE REALTIME DATABASE URL ---
FIREBASE_URL = "https://reseller-c0cf4-default-rtdb.firebaseio.com"

# --- BUILT-IN IST TIME ---
def get_ist_datetime_str():
    try:
        ist_zone = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist_zone).strftime("%d %b %Y, %H:%M")
    except Exception:
        return datetime.utcnow().strftime("%d %b %Y, %H:%M")

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

def add_transaction(user, tx_type, amount, details):
    now_ts = int(time.time() * 1000)
    tx_data = {
        "timestamp": now_ts,
        "date": get_ist_datetime_str(),
        "type": tx_type,  # 'debit' ya 'credit'
        "amount": float(amount),
        "details": details
    }
    fb_put(f"resellers/{user}/transactions/{now_ts}", tx_data)


# --- UNIFIED SINGLE PORTAL & PAGE ROUTES ---
@app.route('/')
@app.route('/login')
@app.route('/admin')
@app.route('/seller')
@app.route('/master')
def serve_portal():
    if os.path.exists('index.html'):
        return send_file('index.html')
    path = request.path.strip('/')
    if path and os.path.exists(f"{path}.html"):
        return send_file(f"{path}.html")
    return "Error: index.html missing in repository", 404


# =======================================================
# 1. LEVEL 1: MASTER ADMIN (APP CONTROL & CREATE ADMINS)
# =======================================================

@app.route('/master/set_app_control', methods=['POST'])
def master_set_app_control():
    status = request.form.get('status', 'active').strip()
    alert_title = request.form.get('alert_title', '').strip()
    alert_msg = request.form.get('alert_msg', '').strip()
    show_alert = str(request.form.get('show_alert', 'false')).lower() == 'true'

    control_data = {
        "status": status,
        "alert_title": alert_title,
        "alert_msg": alert_msg,
        "show_alert": show_alert,
        "updated_at": int(time.time() * 1000)
    }

    if fb_patch("panel_config/app_control", control_data):
        return jsonify({"success": True, "msg": "App control status successfully update ho gaya!"})
    return jsonify({"success": False, "msg": "Firebase update fail!"}), 500

@app.route('/master/get_app_control', methods=['GET'])
def master_get_app_control():
    data = fb_get("panel_config/app_control")
    if not data or not isinstance(data, dict):
        return jsonify({
            "status": "active",
            "alert_title": "",
            "alert_msg": "",
            "show_alert": False
        })
    return jsonify(data)

@app.route('/master/create_admin', methods=['POST'])
def master_create_admin():
    user = request.form.get('username', '').strip().lower()
    pwd = request.form.get('password', '').strip()
    days = int(request.form.get('days', 30))

    if not user or not pwd:
        return jsonify({"success": False, "msg": "Username aur Password zaroori hain!"}), 400

    expiry = int(time.time() * 1000) + (days * 24 * 60 * 60 * 1000)

    admin_data = {
        "username": user,
        "password": pwd,
        "expiry_timestamp": expiry,
        "status": "active"
    }

    if fb_put(f"admins/{user}", admin_data):
        return jsonify({"success": True, "msg": f"Admin [{user}] successfully create ho gaya!"})
    return jsonify({"success": False, "msg": "Firebase write fail!"}), 500

@app.route('/master/get_admins', methods=['GET'])
def master_get_admins():
    admins_raw = fb_get("admins")
    if not admins_raw:
        return jsonify([])
    if isinstance(admins_raw, dict):
        return jsonify(list(admins_raw.values()))
    elif isinstance(admins_raw, list):
        return jsonify([item for item in admins_raw if item is not None and isinstance(item, dict)])
    return jsonify([])

@app.route('/master/delete_admin', methods=['POST'])
def master_delete_admin():
    user = request.form.get('username', '').strip().lower()
    if fb_delete(f"admins/{user}"):
        return jsonify({"success": True})
    return jsonify({"success": False, "msg": "Delete fail!"}), 500


# =======================================================
# 2. LEVEL 2: ADMIN PANEL (CREATES RESELLERS & WALLET)
# =======================================================

@app.route('/admin/login', methods=['POST'])
def admin_login():
    user = request.form.get('username', '').strip().lower()
    pwd = request.form.get('password', '').strip()

    admin = fb_get(f"admins/{user}")
    if not admin or not isinstance(admin, dict) or str(admin.get('password')) != str(pwd):
        return jsonify({"success": False, "msg": "Galat Admin ID ya Password!"}), 401

    if admin.get('status') != 'active':
        return jsonify({"success": False, "msg": "Aapka Admin account Blocked hai!"}), 403

    now = int(time.time() * 1000)
    exp = admin.get('expiry_timestamp', 0)
    if exp > 0 and now > exp:
        return jsonify({"success": False, "msg": "Aapka Admin account EXPIRE ho chuka hai!"}), 403

    return jsonify({
        "success": True,
        "username": str(admin.get('username', user))
    })

@app.route('/admin/create_reseller', methods=['POST'])
def admin_create_reseller():
    admin_user = request.form.get('admin_user', '').strip().lower()
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
        "created_by": admin_user if admin_user else "admin",
        "expiry_timestamp": expiry,
        "status": "active",
        "whatsapp": "https://wa.me/919999999999",
        "telegram": "https://t.me/your_telegram_id"
    }

    if fb_put(f"resellers/{user}", data):
        if balance > 0:
            add_transaction(user, "credit", balance, f"Initial Balance by @{admin_user}")
        return jsonify({"success": True, "msg": f"Reseller [{user}] successfully create ho gaya!"})
    return jsonify({"success": False, "msg": "Firebase write fail!"}), 500

@app.route('/admin/get_resellers', methods=['GET'])
def admin_get_resellers():
    admin_user = request.args.get('admin_user', '').strip().lower()
    resellers_raw = fb_get("resellers")
    if not resellers_raw:
        return jsonify([])

    items = []
    if isinstance(resellers_raw, dict):
        items = list(resellers_raw.values())
    elif isinstance(resellers_raw, list):
        items = [item for item in resellers_raw if item is not None and isinstance(item, dict)]

    if admin_user:
        items = [r for r in items if str(r.get('created_by', '')).lower() == admin_user or not r.get('created_by')]

    return jsonify(items)

@app.route('/admin/recharge_reseller', methods=['POST'])
def admin_recharge_reseller():
    admin_user = request.form.get('admin_user', '').strip().lower()
    user = request.form.get('username', '').strip().lower()
    amount = float(request.form.get('amount', 0.0))

    reseller = fb_get(f"resellers/{user}")
    if not reseller or not isinstance(reseller, dict):
        return jsonify({"success": False, "msg": "Reseller nahi mila!"}), 404

    new_bal = float(reseller.get('balance', 0.0)) + amount
    if fb_patch(f"resellers/{user}", {"balance": new_bal}):
        add_transaction(user, "credit", amount, f"Recharge by @{admin_user}")
        return jsonify({"success": True, "balance": new_bal})
    return jsonify({"success": False, "msg": "Recharge fail!"}), 500

@app.route('/admin/delete_reseller', methods=['POST'])
def admin_delete_reseller():
    user = request.form.get('username', '').strip().lower()
    if fb_delete(f"resellers/{user}"):
        return jsonify({"success": True})
    return jsonify({"success": False, "msg": "Delete fail!"}), 500


# =======================================================
# 3. LEVEL 3: RESELLER PANEL (KEYS & TRANSACTIONS)
# =======================================================

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

    tx_raw = reseller.get("transactions", {})
    user_txs = []
    if isinstance(tx_raw, dict):
        user_txs = list(tx_raw.values())
    elif isinstance(tx_raw, list):
        user_txs = [t for t in tx_raw if t is not None and isinstance(t, dict)]
    user_txs.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    server_real_time = int(time.time() * 1000)

    return jsonify({
        "success": True,
        "server_time": server_real_time,
        "balance": reseller.get('balance', 0.0),
        "expiry_timestamp": reseller.get('expiry_timestamp', 0),
        "whatsapp": reseller.get('whatsapp', 'https://wa.me/919999999999'),
        "telegram": reseller.get('telegram', 'https://t.me/your_telegram_id'),
        "keys": user_keys,
        "transactions": user_txs
    })

@app.route('/reseller/update_contact', methods=['POST'])
def update_contact():
    user = request.form.get('username', '').strip().lower()
    wa = request.form.get('whatsapp', '').strip()
    tg = request.form.get('telegram', '').strip()

    if not user:
        return jsonify({"success": False, "msg": "Username missing!"}), 400

    update_payload = {}
    if wa:
        update_payload["whatsapp"] = wa
    if tg:
        update_payload["telegram"] = tg

    fb_patch(f"resellers/{user}", update_payload)
    return jsonify({"success": True, "msg": "WhatsApp aur Telegram links update ho gaye!"})

# KEY GENERATION (Never, Hours, Days Support)
@app.route('/reseller/generate_key', methods=['POST'])
def reseller_generate_key():
    user = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    plan = request.form.get('plan', '').strip().lower()
    custom_exp = request.form.get('expiry_timestamp', '').strip()

    now = int(time.time() * 1000)

    if plan == 'trial':
        exp = now + (10 * 60 * 1000)
        cost = 0.0
        plan_name = "10 Min Trial"
        days_desc = "10 Min Trial"
    elif plan == 'never (lifetime)' or plan == 'never':
        exp = 0
        cost = 3000.0
        plan_name = "Never (Lifetime)"
        days_desc = "Lifetime"
    elif plan == '1 hour':
        exp = now + (3600 * 1000)
        cost = 5.0
        plan_name = "1 Hour"
        days_desc = "1 Hour"
    elif plan == '2 hours':
        exp = now + (2 * 3600 * 1000)
        cost = 10.0
        plan_name = "2 Hours"
        days_desc = "2 Hours"
    elif plan == '12 hours':
        exp = now + (12 * 3600 * 1000)
        cost = 50.0
        plan_name = "12 Hours"
        days_desc = "12 Hours"
    else:
        try:
            exp = int(custom_exp)
        except Exception:
            exp = now + (24 * 3600 * 1000)

        if exp > 0 and exp <= now:
            return jsonify({"success": False, "msg": "Expiry date aane wale samay ki select karein!"}), 400

        if exp == 0:
            cost = 3000.0
            plan_name = "Never (Lifetime)"
            days_desc = "Lifetime"
        else:
            diff_ms = exp - now
            days = max(1, math.ceil(diff_ms / (24 * 3600 * 1000.0)))
            cost = float(days * 100.0)
            plan_name = f"{days} Day{'s' if days > 1 else ''}"
            days_desc = f"day × {days}"

    reseller = fb_get(f"resellers/{user}")
    if not reseller or not isinstance(reseller, dict):
        return jsonify({"success": False, "msg": "Reseller not found"}), 404

    if cost > 0 and float(reseller.get('balance', 0.0)) < cost:
        return jsonify({"success": False, "msg": f"Balance kam hai! ₹{cost:.0f} chahiye."}), 400

    if cost > 0:
        new_bal = float(reseller.get('balance', 0.0)) - cost
        fb_patch(f"resellers/{user}", {"balance": new_bal})

    key_data = {
        "key": key,
        "hwid": "",
        "status": "unused",
        "reseller": user,
        "plan": plan_name,
        "expiry_timestamp": exp
    }

    if fb_put(f"keys/{key}", key_data):
        if cost > 0:
            add_transaction(user, "debit", cost, f"{key} {days_desc}")
        else:
            add_transaction(user, "debit", 0.0, f"{key} (10 Min Trial)")
        return jsonify({"success": True, "key": key, "cost": cost})
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
    if status:
        updates["status"] = status
    if reset_hwid:
        updates["hwid"] = ""

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


# --- TARGET ANDROID APP VERIFICATION (/verify) ---
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
