import os
import time
import json
from flask import Flask, request, jsonify, render_template_string
import urllib.request

app = Flask(__name__)

# Aapka Firebase Realtime Database URL
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

@app.route('/')
def home():
    return "VIP Auth & Reseller API is Running Successfully!"

# Reseller Login API
@app.route('/reseller/login', methods=['POST'])
def reseller_login():
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '').strip()
    
    if not username or not password:
        return jsonify({"success": False, "msg": "Username aur Password zaroori hai!"})
    
    resellers = db_get("resellers") or {}
    if username in resellers:
        if resellers[username].get('password') == password:
            return jsonify({"success": True, "msg": "Login Successful"})
            
    return jsonify({"success": False, "msg": "Invalid Username or Password!"})

# Reseller Dashboard Data API
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
    
    # Keys fetch karna jo is reseller ne banayi hain
    all_keys = db_get("keys") or {}
    my_keys = []
    for k, info in all_keys.items():
        if info.get('reseller') == username:
            info['key'] = k
            my_keys.append(info)
            
    # Transactions fetch karna
    transactions = reseller_info.get('transactions', [])
    
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

# Key Generation API (Supports Custom Price)
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
    current_balance = reseller_info.get('balance', 0)
    
    # Trial key ke liye cost 0 hogi
    cost = 0 if plan == 'trial' else custom_cost
    
    if current_balance < cost:
        return jsonify({"success": False, "msg": f"Aapka balance kam hai! Required: ₹{cost}, Available: ₹{current_balance}"})
        
    # Check if key already exists
    all_keys = db_get("keys") or {}
    if key in all_keys:
        return jsonify({"success": False, "msg": "Yeh key pehle se bani hui hai!"})
        
    # Deduct balance
    new_balance = current_balance - cost
    
    # Add transaction
    transactions = reseller_info.get('transactions', [])
    tx_entry = {
        "date": time.strftime('%d %b %Y, %I:%M %p'),
        "type": "debit",
        "amount": cost,
        "details": f"Generated key: {key} ({plan})"
    }
    transactions.insert(0, tx_entry)
    
    # Save key to DB
    key_data = {
        "reseller": username,
        "expiry_timestamp": expiry_timestamp,
        "plan": plan,
        "status": "unused",
        "hwid": ""
    }
    db_put(f"keys/{key}", key_data)
    
    # Update reseller balance and transactions
    db_patch(f"resellers/{username}", {
        "balance": new_balance,
        "transactions": transactions
    })
    
    return jsonify({"success": True, "cost": cost, "new_balance": new_balance, "msg": "Key Generated Successfully!"})

# Edit Key API (Status & HWID Reset)
@app.route('/reseller/edit_key', methods=['POST'])
def edit_key():
    username = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    new_status = request.form.get('status')
    reset_hwid = request.form.get('reset_hwid') == 'true'
    
    all_keys = db_get("keys") or {}
    if key not in all_keys:
        return jsonify({"success": False, "msg": "Key not found"})
        
    key_info = all_keys[key]
    if key_info.get('reseller') != username:
        return jsonify({"success": False, "msg": "Permission denied"})
        
    updates = {}
    if new_status:
        updates['status'] = new_status
    if reset_hwid:
        updates['hwid'] = ""
        
    db_patch(f"keys/{key}", updates)
    return jsonify({"success": True, "msg": "Key Updated Successfully!"})

# Delete Key API
@app.route('/reseller/delete_key', methods=['POST'])
def delete_key():
    username = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    
    all_keys = db_get("keys") or {}
    if key not in all_keys:
        return jsonify({"success": False, "msg": "Key not found"})
        
    if all_keys[key].get('reseller') != username:
        return jsonify({"success": False, "msg": "Permission denied"})
        
    # Delete key from Firebase
    urllib.request.urlopen(urllib.request.Request(f"{FIREBASE_URL}/keys/{key}.json", method='DELETE'))
    return jsonify({"success": True, "msg": "Key Deleted Successfully!"})

# Update Contact Links API
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
