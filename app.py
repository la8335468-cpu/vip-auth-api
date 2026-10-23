import os
import time
import json
from flask import Flask, request, jsonify, render_template_string
import urllib.request

app = Flask(__name__)

# Aapka amanmod wala Firebase URL
FIREBASE_URL = "https://amanmod-91196-default-rtdb.firebaseio.com"

def db_get(path):
    try:
        url = f"{FIREBASE_URL}/{path}.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"DB Get Error: {e}")
        return None

def db_put(path, data):
    try:
        url = f"{FIREBASE_URL}/{path}.json"
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='PUT')
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"DB Put Error: {e}")
        return None

def db_patch(path, data):
    try:
        url = f"{FIREBASE_URL}/{path}.json"
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='PATCH')
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"DB Patch Error: {e}")
        return None

@app.route('/')
def home():
    try:
        with open("seller.html", "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return "Seller panel not found"

@app.route('/admin')
def admin_panel():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return "Admin panel not found"

@app.route('/admin/data', methods=['GET'])
def admin_data():
    resellers = db_get("resellers") or {}
    app_control = db_get("control") or {"status": "active", "alert_title": "", "alert_msg": ""}
    return jsonify({
        "success": True,
        "resellers": resellers,
        "control": app_control,
        "server_time": int(time.time() * 1000)
    })

@app.route('/admin/add_reseller', methods=['POST'])
def admin_add_reseller():
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '').strip()
    balance = float(request.form.get('balance', 500))
    expiry_timestamp = int(request.form.get('expiry_timestamp', 0))
    
    if not username or not password:
        return jsonify({"success": False, "msg": "Username aur Password zaroori hai!"})
        
    reseller_data = {
        "password": password,
        "balance": balance,
        "expiry_timestamp": expiry_timestamp,
        "whatsapp": "",
        "telegram": "",
        "transactions": [{
            "date": time.strftime('%d %b %Y, %I:%M %p'),
            "type": "credit",
            "amount": balance,
            "details": "Admin created account with custom validity"
        }]
    }
    db_put(f"resellers/{username}", reseller_data)
    return jsonify({"success": True, "msg": "Reseller Account Created Successfully!"})

@app.route('/admin/delete_reseller', methods=['POST'])
def admin_delete_reseller():
    username = request.form.get('username', '').strip().lower()
    urllib.request.urlopen(urllib.request.Request(f"{FIREBASE_URL}/resellers/{username}.json", method='DELETE'))
    return jsonify({"success": True, "msg": "Reseller Deleted Successfully!"})

@app.route('/admin/set_status', methods=['POST'])
def admin_set_status():
    status = request.form.get('status', 'active')
    db_patch("control", {"status": status})
    return jsonify({"success": True, "msg": f"App status updated to {status}"})

@app.route('/admin/send_alert', methods=['POST'])
def admin_send_alert():
    title = request.form.get('title', '')
    msg = request.form.get('msg', '')
    db_patch("control", {"alert_title": title, "alert_msg": msg})
    return jsonify({"success": True, "msg": "Broadcast Alert Sent!"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
