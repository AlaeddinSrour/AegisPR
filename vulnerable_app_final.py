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

AWS_SECRET_KEY = "AKIAIOSFODNN7EXAMPLE_SECRET_KEY"

@app.route('/download')
def download():
    filename = request.args.get('file')
    filepath = os.path.join('/var/www/uploads', filename)
    return send_file(filepath)

def process_yaml(yaml_string):
    data = yaml.load(yaml_string, Loader=yaml.Loader)
    return data

def make_request(url):
    response = requests.get(url, verify=False)
    return response.text

def deserialize_data(byte_data):
    obj = pickle.loads(byte_data)
    return obj

def compute_hash(data):
    h = hashlib.md5()
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
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchall()

def connect_ssh(host, user, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password)
    return client

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
