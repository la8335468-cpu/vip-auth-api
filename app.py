import os
import time
import json
from flask import Flask, request, jsonify, render_template_string
import urllib.request

app = Flask(__name__)

# Aapka purana amanmod wala Firebase URL
FIREBASE_URL = "https://amanmod-91196-default-rtdb.firebaseio.com"

def db_get(path):
    try:
        url = f"{FIREBASE_URL}/{path}.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data
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

# --- ROUTES ---

@app.route('/')
def home():
    try:
        with open("seller.html", "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return f"Seller panel file not found: {e}"

@app.route('/admin')
def admin_panel():
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return f"Admin panel file not found: {e}"

# --- RESELLER APIs ---

@app.route('/reseller/login', methods=['POST'])
def reseller_login():
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '').strip()
    
    if not username or not password:
        return jsonify({"success": False, "msg": "Username aur Password zaroori hai!"})
    
    resellers = db_get("resellers") or {}
    if username in resellers and isinstance(resellers[username], dict):
        if resellers[username].get('password') == password:
            return jsonify({"success": True, "msg": "Login Successful"})
            
    return jsonify({"success": False, "msg": "Invalid Username or Password!"})

@app.route('/reseller/data', methods=['GET'])
def reseller_data():
    username = request.args.get('username', '').strip().lower()
    if not username:
        return jsonify({"success": False, "msg": "Unauthorized"})
    
    resellers = db_get("resellers") or {}
    if username not in resellers:
        return jsonify({"success": False, "msg": "Reseller not found"})
        
    reseller_info = resellers[username]
    balance = reseller_info.get('balance', 0)
    expiry_timestamp = reseller_info.get('expiry_timestamp', 0)
    whatsapp = reseller_info.get('whatsapp', '')
    telegram = reseller_info.get('telegram', '')
    
    all_keys = db_get("keys") or {}
    my_keys = []
    if isinstance(all_keys, dict):
        for k, info in all_keys.items():
            if isinstance(info, dict) and info.get('reseller') == username:
                info['key'] = k
                my_keys.append(info)
            
    transactions = reseller_info.get('transactions', [])
    if not isinstance(transactions, list):
        transactions = []
    
    return jsonify({
        "success": True,
        "balance": balance,
        "expiry_timestamp": expiry_timestamp,
        "whatsapp": whatsapp,
        "telegram": telegram,
        "keys": my_keys,
        "transactions": transactions,
        "server_time": int(time.time() * 1000)
    })

@app.route('/reseller/generate_key', methods=['POST'])
def generate_key():
    username = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    expiry_timestamp = int(request.form.get('expiry_timestamp', 0))
    plan = request.form.get('plan', '1 Day')
    custom_cost = float(request.form.get('custom_cost', 0))
    
    if not username or not key:
        return jsonify({"success": False, "msg": "Invalid details"})
        
    resellers = db_get("resellers") or {}
    if username not in resellers:
        return jsonify({"success": False, "msg": "Reseller not found"})
        
    reseller_info = resellers[username]
    current_balance = float(reseller_info.get('balance', 0))
    
    cost = 0 if plan == 'trial' else custom_cost
    
    if current_balance < cost:
        return jsonify({"success": False, "msg": f"Aapka balance kam hai! Required: ₹{cost}, Available: ₹{current_balance}"})
        
    all_keys = db_get("keys") or {}
    if isinstance(all_keys, dict) and key in all_keys:
        return jsonify({"success": False, "msg": "Yeh key pehle se bani hui hai!"})
        
    new_balance = current_balance - cost
    
    transactions = reseller_info.get('transactions', [])
    if not isinstance(transactions, list):
        transactions = []
        
    tx_entry = {
        "date": time.strftime('%d %b %Y, %I:%M %p'),
        "type": "debit",
        "amount": cost,
        "details": f"Generated key: {key} ({plan})"
    }
    transactions.insert(0, tx_entry)
    
    key_data = {
        "reseller": username,
        "expiry_timestamp": expiry_timestamp,
        "plan": plan,
        "status": "unused",
        "hwid": ""
    }
    db_put(f"keys/{key}", key_data)
    
    db_patch(f"resellers/{username}", {
        "balance": new_balance,
        "transactions": transactions
    })
    
    return jsonify({"success": True, "cost": cost, "new_balance": new_balance, "msg": "Key Generated Successfully!"})

@app.route('/reseller/edit_key', methods=['POST'])
def edit_key():
    username = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    new_status = request.form.get('status')
    reset_hwid = request.form.get('reset_hwid') == 'true'
    
    all_keys = db_get("keys") or {}
    if not isinstance(all_keys, dict) or key not in all_keys:
        return jsonify({"success": False, "msg": "Key not found"})
        
    key_info = all_keys[key]
    if not isinstance(key_info, dict) or key_info.get('reseller') != username:
        return jsonify({"success": False, "msg": "Permission denied"})
        
    updates = {}
    if new_status:
        updates['status'] = new_status
    if reset_hwid:
        updates['hwid'] = ""
        
    db_patch(f"keys/{key}", updates)
    return jsonify({"success": True, "msg": "Key Updated Successfully!"})

@app.route('/reseller/delete_key', methods=['POST'])
def delete_key():
    username = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    
    all_keys = db_get("keys") or {}
    if not isinstance(all_keys, dict) or key not in all_keys:
        return jsonify({"success": False, "msg": "Key not found"})
        
    if not isinstance(all_keys[key], dict) or all_keys[key].get('reseller') != username:
        return jsonify({"success": False, "msg": "Permission denied"})
        
    urllib.request.urlopen(urllib.request.Request(f"{FIREBASE_URL}/keys/{key}.json", method='DELETE'))
    return jsonify({"success": True, "msg": "Key Deleted Successfully!"})

@app.route('/reseller/update_contact', methods=['POST'])
def update_contact():
    username = request.form.get('username', '').strip().lower()
    whatsapp = request.form.get('whatsapp', '').strip()
    telegram = request.form.get('telegram', '').strip()
    
    db_patch(f"resellers/{username}", {
        "whatsapp": whatsapp,
        "telegram": telegram
    })
    return jsonify({"success": True, "msg": "Contact Links Updated Successfully!"})


# --- ADMIN APIs ---

@app.route('/admin/login', methods=['POST'])
def admin_login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    
    # Master Admin credentials (Aap ise change bhi kar sakte hain)
    admin_data = db_get("admin") or {"username": "admin", "password": "adminpassword123"}
    
    if username == admin_data.get("username") and password == admin_data.get("password"):
        return jsonify({"success": True, "msg": "Admin Login Successful"})
    return jsonify({"success": False, "msg": "Invalid Admin Credentials!"})

@app.route('/admin/data', methods=['GET'])
def admin_data():
    resellers = db_get("resellers") or {}
    keys = db_get("keys") or {}
    return jsonify({
        "success": True,
        "resellers": resellers,
        "keys": keys,
        "server_time": int(time.time() * 1000)
    })

@app.route('/admin/add_reseller', methods=['POST'])
def admin_add_reseller():
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '').strip()
    balance = float(request.form.get('balance', 0))
    
    if not username or not password:
        return jsonify({"success": False, "msg": "Username aur Password zaroori hai!"})
        
    reseller_data = {
        "password": password,
        "balance": balance,
        "expiry_timestamp": 0,
        "whatsapp": "",
        "telegram": "",
        "transactions": [{
            "date": time.strftime('%d %b %Y, %I:%M %p'),
            "type": "credit",
            "amount": balance,
            "details": "Admin created account with initial balance"
        }]
    }
    db_put(f"resellers/{username}", reseller_data)
    return jsonify({"success": True, "msg": "Reseller Added Successfully!"})

@app.route('/admin/topup', methods=['POST'])
def admin_topup():
    username = request.form.get('username', '').strip().lower()
    amount = float(request.form.get('amount', 0))
    
    resellers = db_get("resellers") or {}
    if username not in resellers:
        return jsonify({"success": False, "msg": "Reseller not found!"})
        
    current_balance = float(resellers[username].get('balance', 0))
    new_balance = current_balance + amount
    
    transactions = resellers[username].get('transactions', [])
    if not isinstance(transactions, list):
        transactions = []
        
    transactions.insert(0, {
        "date": time.strftime('%d %b %Y, %I:%M %p'),
        "type": "credit",
        "amount": amount,
        "details": "Admin added balance (Topup)"
    })
    
    db_patch(f"resellers/{username}", {
        "balance": new_balance,
        "transactions": transactions
    })
    return jsonify({"success": True, "msg": "Balance Added Successfully!"})

@app.route('/admin/delete_reseller', methods=['POST'])
def admin_delete_reseller():
    username = request.form.get('username', '').strip().lower()
    urllib.request.urlopen(urllib.request.Request(f"{FIREBASE_URL}/resellers/{username}.json", method='DELETE'))
    return jsonify({"success": True, "msg": "Reseller Deleted Successfully!"})

@app.route('/admin/delete_key', methods=['POST'])
def admin_delete_key():
    key = request.form.get('key', '').strip().upper()
    urllib.request.urlopen(urllib.request.Request(f"{FIREBASE_URL}/keys/{key}.json", method='DELETE'))
    return jsonify({"success": True, "msg": "Key Deleted Successfully by Admin!"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
