import os
import sqlite3
import time
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_PATH = "database.db"

# --- DATABASE INIT ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resellers (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            balance REAL DEFAULT 0.0,
            expiry_timestamp INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            hwid TEXT DEFAULT '',
            status TEXT DEFAULT 'unused',
            reseller TEXT DEFAULT 'ADMIN',
            plan TEXT DEFAULT '1 Day',
            expiry_timestamp INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- WEB PAGE ROUTES ---
@app.route('/')
@app.route('/seller')
def seller_page():
    if os.path.exists('seller.html'):
        return send_file('seller.html')
    return "Error: seller.html file missing in repo", 404

@app.route('/admin')
def admin_page():
    if os.path.exists('admin.html'):
        return send_file('admin.html')
    return "Error: admin.html file missing in repo", 404


# --- MASTER ADMIN APIS (NO PASSWORD REQUIRED) ---
@app.route('/admin/create_reseller', methods=['POST'])
def create_reseller():
    user = request.form.get('username', '').strip().lower()
    pwd = request.form.get('password', '').strip()
    balance = float(request.form.get('balance', 0.0))
    days = int(request.form.get('days', 30))

    if not user or not pwd:
        return jsonify({"success": False, "msg": "Username aur Password zaroori hain!"}), 400

    expiry = int(time.time() * 1000) + (days * 24 * 60 * 60 * 1000)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO resellers (username, password, balance, expiry_timestamp, status) 
            VALUES (?, ?, ?, ?, 'active')
        """, (user, pwd, balance, expiry))
        conn.commit()
        return jsonify({"success": True, "msg": f"Reseller [{user}] successfully create ho gaya!"})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/get_resellers', methods=['GET'])
def get_resellers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, password, balance, expiry_timestamp, status FROM resellers")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/admin/recharge_reseller', methods=['POST'])
def recharge_reseller():
    user = request.form.get('username', '').strip().lower()
    amount = float(request.form.get('amount', 0.0))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE resellers SET balance = balance + ? WHERE username = ?", (amount, user))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/admin/delete_reseller', methods=['POST'])
def delete_reseller():
    user = request.form.get('username', '').strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM resellers WHERE username = ?", (user,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# --- RESELLER PANEL APIS ---
@app.route('/reseller/login', methods=['POST'])
def reseller_login():
    user = request.form.get('username', '').strip().lower()
    pwd = request.form.get('password', '').strip()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM resellers WHERE username = ?", (user,))
    row = cursor.fetchone()
    conn.close()

    if not row or row['password'] != pwd:
        return jsonify({"success": False, "msg": "Galat Username ya Password!"}), 401

    if row['status'] != 'active':
        return jsonify({"success": False, "msg": "Aapka account Blocked hai!"}), 403

    now = int(time.time() * 1000)
    if row['expiry_timestamp'] > 0 and now > row['expiry_timestamp']:
        return jsonify({"success": False, "msg": "Aapka Reseller account EXPIRE ho chuka hai!"}), 403

    return jsonify({"success": True, "username": row['username'], "balance": row['balance']})

@app.route('/reseller/data', methods=['GET'])
def reseller_data():
    user = request.args.get('username', '').strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance, expiry_timestamp FROM resellers WHERE username = ?", (user,))
    reseller = cursor.fetchone()

    cursor.execute("SELECT * FROM keys WHERE reseller = ? ORDER BY expiry_timestamp DESC", (user,))
    keys = cursor.fetchall()
    conn.close()

    if not reseller:
        return jsonify({"success": False, "msg": "User not found"}), 404

    return jsonify({
        "success": True,
        "balance": reseller['balance'],
        "expiry_timestamp": reseller['expiry_timestamp'],
        "keys": [dict(k) for k in keys]
    })

@app.route('/reseller/generate_key', methods=['POST'])
def reseller_generate_key():
    user = request.form.get('username', '').strip().lower()
    key = request.form.get('key', '').strip().upper()
    plan = request.form.get('plan', '1d')
    cost = float(request.form.get('cost', 40.0))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM resellers WHERE username = ?", (user,))
    res = cursor.fetchone()

    if not res or res['balance'] < cost:
        conn.close()
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

    cursor.execute("UPDATE resellers SET balance = balance - ? WHERE username = ?", (cost, user))
    cursor.execute("""
        INSERT INTO keys (key, status, reseller, plan, expiry_timestamp) 
        VALUES (?, 'unused', ?, ?, ?)
    """, (key, user, plan_name, exp))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "key": key, "cost": cost})


# --- TARGET ANDROID APP VERIFY (/verify) ---
@app.route('/verify', methods=['POST'])
def verify():
    key = request.form.get('key', '').strip().upper()
    hwid = request.form.get('hwid', '').strip().lower()

    if not key or not hwid:
        return jsonify({"status": False, "msg": "KEY AUR HWID MISSING HAI"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keys WHERE key = ?", (key,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": False, "msg": "INVALID LICENSE KEY"})

    now = int(time.time() * 1000)
    if row['expiry_timestamp'] > 0 and now > row['expiry_timestamp']:
        cursor.execute("UPDATE keys SET status = 'expired' WHERE key = ?", (key,))
        conn.commit()
        conn.close()
        return jsonify({"status": False, "msg": "KEY EXPIRED"})

    if row['status'] == 'frozen':
        conn.close()
        return jsonify({"status": False, "msg": "KEY IS FROZEN"})

    if not row['hwid']:
        cursor.execute("UPDATE keys SET hwid = ?, status = 'active' WHERE key = ?", (hwid, key))
        conn.commit()
        conn.close()
        return jsonify({"status": True, "msg": "DEVICE BOUND & ACCESS GRANTED"})

    if row['hwid'].lower() == hwid:
        conn.close()
        return jsonify({"status": True, "msg": "LOGIN SUCCESSFUL"})
    else:
        conn.close()
        return jsonify({"status": False, "msg": "HWID MISMATCH! BOUND TO ANOTHER DEVICE"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
