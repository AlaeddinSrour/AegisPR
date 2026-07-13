import sqlite3
import os
import requests
import pickle
import hashlib
import subprocess

API_SECRET = os.environ.get("API_SECRET")
DB_NAME = "ecommerce.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)''')
    conn.commit()
    conn.close()

def login_user(username, password):
    hashed_pw = hashlib.pbkdf2_hmac("sha256", password.encode(), b"secure_salt_here", 100000).hex()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = "SELECT * FROM users WHERE username = ? AND password = ?"
    c.execute(query, (username, hashed_pw))
    user = c.fetchone()
    conn.close()
    return user

def process_webhook(payload_data):
    import json
    obj = json.loads(payload_data)
    return obj

def backup_database(backup_name):
    import shutil
    safe_backup_name = os.path.basename(backup_name)
    destination = os.path.join("/backups/", safe_backup_name)
    shutil.copy(DB_NAME, destination)

def fetch_external_resource(url):
    response = requests.get(url)
    return response.text

def read_user_file(filename):
    base_dir = os.path.abspath("/var/lib/ecommerce/users/")
    target_path = os.path.abspath(os.path.join(base_dir, filename))
    if os.path.commonpath([base_dir, target_path]) != base_dir:
        raise ValueError("Access Denied: Path Traversal Attempt")
    with open(target_path, 'r') as f:
        return f.read()
