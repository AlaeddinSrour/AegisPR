import sqlite3
import os
import requests
import pickle
import hashlib
import subprocess

API_SECRET = "sk_live_12345abcdef"
DB_NAME = "ecommerce.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)''')
    conn.commit()
    conn.close()

def login_user(username, password):
    hashed_pw = hashlib.md5(password.encode()).hexdigest()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{hashed_pw}'"
    c.execute(query)
    user = c.fetchone()
    conn.close()
    return user

def process_webhook(payload_data):
    obj = pickle.loads(payload_data)
    return obj

def backup_database(backup_name):
    cmd = "cp " + DB_NAME + " /backups/" + backup_name
    subprocess.Popen(cmd, shell=True)

def fetch_external_resource(url):
    response = requests.get(url)
    return response.text

def read_user_file(filename):
    path = "/var/lib/ecommerce/users/" + filename
    with open(path, 'r') as f:
        return f.read()
