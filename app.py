import os
import time
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Aapka Firebase Realtime Database URL
FIREBASE_URL = "https://amanmod-91196-default-rtdb.firebaseio.com"


# --- FIREBASE REST API HELPERS ---
def fb_get(endpoint):
    try:
        r = requests.get(f"{FIREBASE_URL}/{endpoint}.json", timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def fb_put(endpoint, data):
    try:
        r = requests.put(f"{FIREBASE_URL}/{endpoint}.json", json=data, timeout=10)
        return r.status_code in [200, 201]
    except Exception:
        return False

def fb_patch(endpoint, data):
    try:
        r = requests.patch(f"{FIREBASE_URL}/{endpoint}.json", json=data, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def fb_delete(endpoint):
    try:
        r = requests.delete(f"{FIREBASE_URL}/{endpoint}.json", timeout=10)
        return r.status_code == 200
    except Exception:
        return False


# --- WEB PAGES ROUTES ---
@app.route('/')
@app.route('/seller')
def seller_page():
    if os.path.exists('seller.html'):
        return send_file('seller.html')
    return "Error: seller.html file repo me nahi mili", 404

@app.route('/admin')
def admin_page():
    if os.path.exists('admin.html'):
        return send_file('admin.html')
    return "Error: admin.html file repo me nahi mili", 404


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
        "status": "active"
    }

    if fb_put(f"resellers/{user}", data):
        return jsonify({"success": True, "msg": f"Reseller [{user}] successfully create ho gaya!"})
    return jsonify({"success": False, "msg": "Firebase data save error!"}), 500

@app.route('/admin/get_resellers', methods=['GET'])
def get_resellers():
    resellers_dict = fb_get("resellers")
    if not resellers_dict or not isinstance(resellers_dict, dict):
        return jsonify([])
    return jsonify(list(resellers_dict.values()))

@app.route('/admin/recharge_reseller', methods=['POST'])
def recharge_reseller():
    user = request.form.get('username', '').strip().lower()
    amount = float(request.form.get('amount', 0.0))

    reseller = fb_get(f"resellers/{user}")
    if not reseller:
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
    if not reseller or reseller.get('password') != pwd:
        return jsonify({"success": False, "msg": "Galat Username ya Password!"}), 401

    if reseller.get('status') != 'active':
        return jsonify({"success": False, "msg": "Aapka account Blocked hai!"}), 403

    now = int(time.time() * 1000)
    exp = reseller.get('expiry_timestamp', 0)
    if exp > 0 and now > exp:
        return jsonify({"success": False, "msg": "Aapka Reseller account EXPIRE ho chuka hai!"}), 403

    return jsonify({
        "success": True,
        "username": reseller.get('username', user),
        "balance": reseller.get('balance', 0.0)
    })

@app.route('/reseller/data', methods=['GET'])
def reseller_data():
    user = request.args.get('username', '').strip().lower()
    reseller = fb_get(f"resellers/{user}")

    if not reseller:
        return jsonify({"success": False, "msg": "User not found"}), 404

    all_keys = fb_get("keys") or {}
    user_keys = []
    if isinstance(all_keys, dict):
        for k, v in all_keys.items():
            if isinstance(v, dict) and v.get('reseller', '').lower() == user:
                user_keys.append(v)

    user_keys.sort(key=lambda x: x.get('expiry_timestamp', 0), reverse=True)

    return jsonify({
        "success": True,
        "balance": reseller.get('balance', 0.0),
        "expiry_timestamp": reseller.get('expiry_timestamp', 0),
        "keys": user_keys
    })

@app.route('/reseller/generate_key', methods=['POST'])
def reseller_generate_key():
    user = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    plan = request.form.get('plan', '1d')
    cost = float(request.form.get('cost', 40.0))

    reseller = fb_get(f"resellers/{user}")
    if not reseller or float(reseller.get('balance', 0.0)) < cost:
        return jsonify({"success": False, "msg": "Balance kam hai! Wallet recharge karein."}), 400

    now = int(time.time() * 1000)
    if plan == '1h':
        exp = now + (3600 * 1000)
        plan_name = "1 Hour"
    elif plan == '1d':
        exp = now + (24 * 3600 * 1000)
        plan_name = "1 Day"
    else:
        exp = now + (30 * 24 * 3600 * 1000)
        plan_name = "1 Month"

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
        return jsonify({"success": True, "key": key, "cost": cost})
    return jsonify({"success": False, "msg": "Key generate fail!"}), 500

@app.route('/reseller/edit_key', methods=['POST'])
def reseller_edit_key():
    user = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    status = request.form.get('status', '').strip()
    plan = request.form.get('plan', '').strip()
    reset_hwid = str(request.form.get('reset_hwid', '')).lower() == 'true'

    key_obj = fb_get(f"keys/{key}")
    if not key_obj or key_obj.get('reseller', '').lower() != user:
        return jsonify({"success": False, "msg": "Key nahi mili!"}), 404

    now = int(time.time() * 1000)
    exp = key_obj.get('expiry_timestamp', 0)
    plan_name = key_obj.get('plan', '1 Day')

    if plan:
        if plan == '1h':
            exp = now + (3600 * 1000)
            plan_name = "1 Hour"
        elif plan == '1d':
            exp = now + (24 * 3600 * 1000)
            plan_name = "1 Day"
        elif plan == '1m':
            exp = now + (30 * 24 * 3600 * 1000)
            plan_name = "1 Month"

    updates = {
        "plan": plan_name,
        "expiry_timestamp": exp,
        "status": status if status else key_obj.get('status', 'unused')
    }
    if reset_hwid:
        updates["hwid"] = ""

    if fb_patch(f"keys/{key}", updates):
        return jsonify({"success": True, "msg": "Key successfully update ho gayi!"})
    return jsonify({"success": False, "msg": "Key update fail!"}), 500

@app.route('/reseller/delete_key', methods=['POST'])
def reseller_delete_key():
    user = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()

    key_obj = fb_get(f"keys/{key}")
    if not key_obj or key_obj.get('reseller', '').lower() != user:
        return jsonify({"success": False, "msg": "Key nahi mili!"}), 404

    if fb_delete(f"keys/{key}"):
        return jsonify({"success": True, "msg": "Key permanently delete ho gayi!"})
    return jsonify({"success": False, "msg": "Delete fail!"}), 500


# --- TARGET ANDROID APP VERIFY (/verify) ---
@app.route('/verify', methods=['POST'])
def verify():
    key = request.form.get('key', '').strip().upper()
    hwid = request.form.get('hwid', '').strip().lower()

    if not key or not hwid:
        return jsonify({"status": False, "msg": "KEY AUR HWID MISSING HAI"}), 400

    key_obj = fb_get(f"keys/{key}")
    if not key_obj:
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
