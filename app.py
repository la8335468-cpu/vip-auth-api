from flask import Flask, request, jsonify
import sqlite3
import time

app = Flask(__name__)

# Database Initialization
def init_db():
    conn = sqlite3.connect("license.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            hwid TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            expiry_timestamp INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- 1. VERIFY API (Android Dialog ke liye) ---
@app.route('/verify', methods=['POST'])
def verify_key():
    key = request.form.get('key', '').strip().upper()
    hwid = request.form.get('hwid', '').strip().lower()

    if not key or not hwid:
        return jsonify({"status": False, "msg": "INVALID PARAMETERS"}), 400

    conn = sqlite3.connect("license.db")
    cursor = conn.cursor()
    cursor.execute("SELECT hwid, status, expiry_timestamp FROM keys WHERE key = ?", (key,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": False, "msg": "INVALID LICENSE KEY"})

    server_hwid, status, expiry = row
    current_time = int(time.time() * 1000)

    # Expiry Check
    if expiry > 0 and current_time > expiry:
        conn.close()
        return jsonify({"status": False, "msg": "KEY HAS EXPIRED"})

    # Status Check
    if status.lower() == 'blocked':
        conn.close()
        return jsonify({"status": False, "msg": "ACCESS BLOCKED"})

    # First Time Auto-bind HWID
    if not server_hwid:
        cursor.execute("UPDATE keys SET hwid = ? WHERE key = ?", (hwid, key))
        conn.commit()
        conn.close()
        return jsonify({"status": True, "msg": "DEVICE BOUND & ACCESS GRANTED"})

    # HWID Match
    conn.close()
    if server_hwid.lower() == hwid:
        return jsonify({"status": True, "msg": "LOGIN SUCCESSFUL"})
    else:
        return jsonify({"status": False, "msg": "HWID MISMATCH"})

# --- 2. ADMIN CREATE KEY API (Nayi key add karne ke liye) ---
@app.route('/create_key', methods=['POST'])
def create_key():
    key = request.form.get('key', '').strip().upper()
    hwid = request.form.get('hwid', '').strip().lower()
    days = int(request.form.get('days', 30))

    if not key:
        return jsonify({"error": "Key is required"}), 400

    expiry_timestamp = 0 if days == 0 else int(time.time() * 1000) + (days * 24 * 60 * 60 * 1000)

    conn = sqlite3.connect("license.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO keys (key, hwid, status, expiry_timestamp) VALUES (?, ?, 'active', ?)",
                       (key, hwid, expiry_timestamp))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "key": key, "days": days})
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
