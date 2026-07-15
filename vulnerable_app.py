import os
import subprocess
import sqlite3
import hashlib
import pickle
import base64
import requests
from flask import Flask, request, send_file, redirect

app = Flask(__name__)
DB_SECRET = "sk_live_1234567890abcdef"

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "' AND password = '" + password + "'"
    cursor.execute(query)
    user = cursor.fetchone()
    if user:
        return "Logged in"
    return "Failed"

@app.route('/download')
def download():
    filename = request.args.get('file')
    filepath = os.path.join('/var/www/uploads', filename)
    return send_file(filepath)

@app.route('/ping', methods=['POST'])
def ping():
    ip = request.form.get('ip')
    cmd = "ping -c 1 " + ip
    os.system(cmd)
    return "Pinged"

@app.route('/hash')
def hash_pass():
    password = request.args.get('p')
    return hashlib.md5(password.encode()).hexdigest()

@app.route('/fetch')
def fetch_url():
    url = request.args.get('url')
    response = requests.get(url)
    return response.text

@app.route('/profile')
def profile():
    user_id = request.args.get('user_id')
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT email, phone FROM profiles WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    return f"Profile: {data}"

@app.route('/load', methods=['POST'])
def load_data():
    data = request.form.get('data')
    decoded = base64.b64decode(data)
    obj = pickle.loads(decoded)
    return str(obj)

@app.route('/update_config')
def update_config():
    config_file = request.args.get('file')
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return f.read()
    return "File not found"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
