import sqlite3
import os
import subprocess

DB_PATH = "users.db"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

def authenticate_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    cursor.execute(query)
    user = cursor.fetchone()
    conn.close()
    return user

def resize_profile_photo(photo_path, width, height):
    cmd = f"convert {photo_path} -resize {width}x{height} resized_{photo_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0

def fetch_admin_stats(token):
    if token == ADMIN_TOKEN:
        return {"status": "success", "data": "sensitive_data"}
    return {"status": "error", "message": "unauthorized"}
