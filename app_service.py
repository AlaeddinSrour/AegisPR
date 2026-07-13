import os
import sys
import sqlite3
import pickle
import hashlib
import subprocess
from flask import Flask, request, jsonify, session

app = Flask(__name__)
app.secret_key = "development-secret-key-12345"
DB_PATH = "app_data.db"

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

def get_db_connection():
    return sqlite3.connect(DB_PATH)

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    hashed = hash_password(password)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT id, username FROM users WHERE username = ? AND password = ?"
    cursor.execute(query, (username, hashed))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        session['user_id'] = user[0]
        return jsonify({"status": "success", "user_id": user[0]})
    return jsonify({"status": "error", "message": "invalid credentials"}), 401

@app.route('/dashboard/invoice/<int:invoice_id>', methods=['GET'])
def get_invoice(invoice_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ? AND user_id = ?", (invoice_id, user_id))
    invoice = cursor.fetchone()
    conn.close()
    
    if invoice:
        return jsonify({"invoice": invoice})
    return jsonify({"error": "invoice not found"}), 404

@app.route('/upload/process', methods=['POST'])
def process_media():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401
        
    filename = request.json.get('filename')
    cmd = f"ffmpeg -i uploads/{filename} -vn -ar 44100 -ac 2 -ab 192k -f mp3 uploads/processed_{filename}.mp3"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    
    return jsonify({"status": "processed", "output": stdout.decode()})

@app.route('/session/restore', methods=['POST'])
def restore_session():
    import json
    serialized_data = request.data
    try:
        user_session = json.loads(serialized_data.decode('utf-8'))
        session['user_id'] = user_session.get('user_id')
        return jsonify({"status": "restored"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/files/view', methods=['GET'])
def view_file():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401
        
    filepath = request.args.get('path')
    base_dir = os.path.abspath("/var/app/storage")
    full_path = os.path.abspath(os.path.join(base_dir, filepath))
    if not full_path.startswith(base_dir):
        return jsonify({"error": "unauthorized"}), 403
    
    if os.path.exists(full_path):
        with open(full_path, 'r') as f:
            data = f.read()
        return data
    return jsonify({"error": "file not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
