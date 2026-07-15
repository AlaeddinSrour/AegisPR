import os
import sqlite3
import subprocess
import pickle
import yaml
import requests
import hashlib
import paramiko
from flask import Flask, request, send_file

app = Flask(__name__)

AWS_SECRET_KEY = os.environ.get("AWS_SECRET_KEY")

@app.route('/download')
def download():
    base_dir = os.path.abspath('/var/www/uploads')
    filename = request.args.get('file')
    filepath = os.path.abspath(os.path.join(base_dir, filename))
    if os.path.commonpath([base_dir, filepath]) != base_dir:
        return "Access Denied", 403
    return send_file(filepath)

def process_yaml(yaml_string):
    data = yaml.safe_load(yaml_string)
    return data

def make_request(url):
    response = requests.get(url, verify=True)
    return response.text

def deserialize_data(byte_data):
    import json
    obj = json.loads(byte_data.decode('utf-8'))
    return obj

def compute_hash(data):
    h = hashlib.sha256()
    h.update(data.encode('utf-8'))
    return h.hexdigest()

def execute_cmd(user_input):
    os.system(f"echo {user_input}")

def advanced_cmd(user_cmd):
    p = subprocess.Popen(user_cmd, shell=True, stdout=subprocess.PIPE)
    return p.communicate()[0]

def query_db(username):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE username = ?"
    cursor.execute(query, (username,))
    return cursor.fetchall()

def connect_ssh(host, user, password):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(host, username=user, password=password)
    return client

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
