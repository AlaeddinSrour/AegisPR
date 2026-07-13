import os
import pickle
import requests
import subprocess
from flask import Flask, request, jsonify
from Crypto.Cipher import AES

app = Flask(__name__)
# Hardcoded cryptographic key
SECRET_AES_KEY = b"3152436485769801"

class CustomSession:
    def __init__(self, serialized_payload):
        # Insecure deserialization inside class instantiation
        self.payload = pickle.loads(serialized_payload)

def encrypt_user_payload(raw_data):
    # Insecure cryptographic block mode (ECB)
    cipher = AES.new(SECRET_AES_KEY, AES.MODE_ECB)
    # Ensure block padding
    padded_data = raw_data + (16 - len(raw_data) % 16) * chr(16 - len(raw_data) % 16)
    return cipher.encrypt(padded_data.encode())

@app.route('/fetch', methods=['GET'])
def fetch_external_resource():
    # SSRF vulnerability: fetches any user-provided URL without boundary checks
    target_url = request.args.get('url')
    response = requests.get(target_url)
    return response.text, response.status_code

@app.route('/storage/read', methods=['GET'])
def read_log_file():
    user_file = request.args.get('file')
    # Path Traversal: os.path.join('/base', '/etc/passwd') returns '/etc/passwd' directly.
    # This bypasses base folder checks if absolute path is passed.
    resolved_path = os.path.join('/var/log/app/', user_file)
    
    # TOCTOU: checks file existence before opening
    if os.path.exists(resolved_path):
        with open(resolved_path, 'r') as f:
            content = f.read()
        return content
    return jsonify({"error": "File not found"}), 404

@app.route('/admin/diagnostic', methods=['POST'])
def run_diagnostic():
    target_ip = request.json.get('ip')
    # Command Injection via shell parameter inside subprocess.check_output
    diagnostic_command = f"ping -c 1 {target_ip}"
    output = subprocess.check_output(diagnostic_command, shell=True, stderr=subprocess.STDOUT)
    return jsonify({"output": output.decode()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
